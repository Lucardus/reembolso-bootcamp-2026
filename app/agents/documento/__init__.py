"""Documento — categorização e extração.

Recebe o anexo em base64, extrai o texto (PDF ou OCR na foto), classifica numa
das 7 categorias e extrai os campos que a análise precisa.

Três situações parecem iguais e não são: documento fiscal com campo faltando,
documento fiscal de despesa não coberta e arquivo que não é documento fiscal.
A base de conhecimento diz o tratamento de cada uma.
"""

import base64
import io
from typing import Literal, Optional
import fitz
import pytesseract
from PIL import Image
from pydantic import BaseModel
from app.agents import AgentState
from app.llm import criar_llm

llm = criar_llm()

CategoriaDocumento = Literal[
    "CONSULTA_MEDICA", "SESSAO_TERAPIA", "EXAME_DIAGNOSTICO",
    "RELATORIO_CLINICO", "MATERIAL_OPME", "DESPESA_NAO_COBERTA", "INVALIDO",
]

class ExtracaoDocumento(BaseModel):
    categoria_documento: CategoriaDocumento
    valor_pago: Optional[float] = None
    data_atendimento: Optional[str] = None
    codigo_procedimento: Optional[str] = None
    finalidade: Optional[str] = None
    campos_obrigatorios_presentes: bool
    campos_faltando: list[str] = []

def _extrair_texto_anexo(anexo: dict) -> str:
    conteudo_bytes = base64.b64decode(anexo["base64"])
    mime_type = anexo.get("mime_type", "")

    if mime_type == "application/pdf":
        doc = fitz.open(stream=conteudo_bytes, filetype="pdf")
        texto = "\n".join(page.get_text() for page in doc)
        if not texto.strip():
            texto_ocr = [pytesseract.image_to_string(Image.open(io.BytesIO(page.get_pixmap().tobytes("png"))), lang="por") for page in doc]
            texto = "\n".join(texto_ocr)
        return texto
    elif mime_type.startswith("image/"):
        return pytesseract.image_to_string(Image.open(io.BytesIO(conteudo_bytes)), lang="por")
    return ""

def ag_documento(state: AgentState) -> AgentState:
    if state.get("anexo_processado"):
        return state
    anexo = state.get("anexo_atual")
    if not anexo:
        return state

    texto_extraido = _extrair_texto_anexo(anexo)
    if not texto_extraido.strip():
        state["categoria_documento"] = "INVALIDO"
        state["dados_documento"] = None
        state["pendencias"] = state.get("pendencias", []) + ["Não foi possível ler o conteúdo do anexo."]
        state["anexo_processado"] = True
        state["anexo_atual"] = None
        state["_caso_decidido"] = False
        state["_contador_documentos_rejeitados"] = state.get("_contador_documentos_rejeitados", 0) + 1
        contador = state["_contador_documentos_rejeitados"]
        respostas_ilegivel = [
            "Não consegui ler o conteúdo desse arquivo. Pode reenviar em outro "
            "formato ou com melhor qualidade?",
            "O arquivo continua ilegível para mim. Pode tentar enviar de novo, "
            "talvez em PDF ou com uma foto mais nítida?",
            "Ainda não consegui extrair o conteúdo desse documento. O protocolo "
            "continua aberto aguardando um arquivo legível.",
        ]
        idx = (contador - 1) % len(respostas_ilegivel)
        state["resposta_texto"] = respostas_ilegivel[idx]
        if "historico" not in state:
            state["historico"] = []
        state["historico"].append({
            "turno": len(state["historico"]) + 1,
            "mensagem": state.get("mensagem_atual", ""),
            "resposta": state["resposta_texto"],
            "dados_extraidos": {"categoria": "INVALIDO"},
        })
        return state

    prompt = f"""Extraia dados do documento médico abaixo:
---
{texto_extraido}
---
Categorias válidas: CONSULTA_MEDICA, SESSAO_TERAPIA, EXAME_DIAGNOSTICO, RELATORIO_CLINICO, MATERIAL_OPME, DESPESA_NAO_COBERTA, INVALIDO.
Se faltar campos obrigatórios (Prestador, Data, Valor), marque em campos_faltando."""

    resultado: ExtracaoDocumento = llm.with_structured_output(ExtracaoDocumento).invoke(prompt)

    if resultado.categoria_documento == "INVALIDO":
        state["_contador_documentos_rejeitados"] = state.get("_contador_documentos_rejeitados", 0) + 1
        # Documento ilegivel ou que nao e documento fiscal (art. 76): NAO
        # gera pendencia sanavel, e o beneficiario deve ser orientado a
        # enviar o documento correto, com o protocolo (se existir)
        # permanecendo aberto (art. 76, paragrafo unico). ag_normas tem
        # um retorno antecipado para categoria INVALIDO (para nao decidir
        # o caso com base num documento invalido) e NAO define resposta -
        # por isso a resposta desta rejeicao PRECISA ser definida aqui,
        # senao o turno cai no fallback generico do main.py.
        contador = state["_contador_documentos_rejeitados"]
        respostas_rejeicao = [
            "O arquivo enviado nao e um documento fiscal de despesa assistencial "
            "(recibo ou nota fiscal do atendimento) - por isso nao pode ser "
            "processado. Pode enviar o documento correto? O protocolo continua "
            "aberto aguardando esse envio.",
            "Esse arquivo ainda nao e o que precisamos: buscamos o recibo ou nota "
            "fiscal do atendimento. Pode conferir e enviar o documento certo?",
            "Esse arquivo nao corresponde a um documento fiscal de despesa "
            "assistencial. Assim que tiver o recibo ou nota fiscal correto, pode "
            "enviar por aqui.",
        ]
        idx = (contador - 1) % len(respostas_rejeicao)
        state["categoria_documento"] = "INVALIDO"
        state["dados_documento"] = None
        state["anexo_processado"] = True
        state["_caso_decidido"] = False
        state["resposta_texto"] = respostas_rejeicao[idx]
        if "historico" not in state:
            state["historico"] = []
        state["historico"].append({
            "turno": len(state["historico"]) + 1,
            "mensagem": state.get("mensagem_atual", ""),
            "resposta": state["resposta_texto"],
            "dados_extraidos": {"categoria": "INVALIDO"},
        })
        return state

    if resultado.categoria_documento == "RELATORIO_CLINICO":
        # O relatorio clinico e um documento COMPLEMENTAR: ele nao
        # substitui o documento fiscal (recibo/nota) que originou o
        # pedido. Se ja havia uma categoria de despesa assistencial
        # (CONSULTA_MEDICA, SESSAO_TERAPIA etc.) com valor/dados
        # extraidos, preserva-a - so marca que o relatorio foi recebido
        # e libera a pendencia por falta dele.
        categoria_anterior = state.get("categoria_documento")
        if categoria_anterior and categoria_anterior not in ("INVALIDO", "RELATORIO_CLINICO", None):
            state["_relatorio_clinico_recebido"] = True
            # Remove a pendencia especifica de relatorio clinico, se existia,
            # mas preserva outras pendencias (ex.: campo faltando no recibo).
            state["pendencias"] = [
                p for p in (state.get("pendencias") or [])
                if "relatorio" not in p.lower() and "relatório" not in p.lower()
            ]
            state["_caso_decidido"] = False
            state["anexo_processado"] = True
            return state

    state["categoria_documento"] = resultado.categoria_documento
    state["valor_solicitado_brl"] = resultado.valor_pago
    state["dados_documento"] = {
        "data_atendimento": resultado.data_atendimento,
        "codigo_procedimento": resultado.codigo_procedimento,
        "finalidade": resultado.finalidade,
        "campos_obrigatorios_presentes": resultado.campos_obrigatorios_presentes,
    }
    if not resultado.campos_obrigatorios_presentes:
        state["pendencias"] = state.get("pendencias", []) + resultado.campos_faltando

    if resultado.categoria_documento == "RELATORIO_CLINICO":
        state["_relatorio_clinico_recebido"] = True

    # Documento novo valido chegou - o caso precisa ser (re)avaliado por
    # ag_normas; libera o "trava" de decisao ja tomada, se existia.
    state["_caso_decidido"] = False

    state["anexo_processado"] = True
    return state