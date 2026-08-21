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
    # Evita reprocessar o mesmo anexo em turnos subsequentes
    if state.get("anexo_processado"):
        return state

    anexo = state.get("anexo_atual") or state.get("anexo_salvo")
    if not anexo:
        return state

    texto_extraido = _extrair_texto_anexo(anexo)
    if not texto_extraido.strip():
        state["categoria_documento"] = "INVALIDO"
        state["pendencias"] = state.get("pendencias", []) + ["Não foi possível ler o conteúdo do anexo."]
        state["anexo_processado"] = True
        return state

    prompt = f"""Extraia dados do documento médico abaixo:
---
{texto_extraido}
---
Categorias válidas: CONSULTA_MEDICA, SESSAO_TERAPIA, EXAME_DIAGNOSTICO, RELATORIO_CLINICO, MATERIAL_OPME, DESPESA_NAO_COBERTA, INVALIDO.
Se faltar campos obrigatórios (Prestador, Data, Valor), marque em campos_faltando."""

    resultado: ExtracaoDocumento = llm.with_structured_output(ExtracaoDocumento).invoke(prompt)

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

    state["anexo_processado"] = True
    return state