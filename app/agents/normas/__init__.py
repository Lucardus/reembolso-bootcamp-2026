"""Normas — recuperação, vigência e cálculo.

Encontra a regra que vale para a categoria e o plano, resolve qual redação está
em vigor e apura o valor.

Cuidado com três coisas que a base cobra:
  * a regra e a condição que a limita nem sempre estão no mesmo artigo;
  * o texto impresso num documento pode ter sido alterado por outro;
  * a ordem das operações do cálculo é parte da própria norma.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.agents import AgentState
from app.rag import MotorRAG
from app.llm import criar_llm
from app.guardrails import aplicar_guardrails
from app.tools import abrir_protocolo
from app.calculo import apurar_reembolso


motor_rag = MotorRAG()
llm = criar_llm()

import re as _re

_PADRAO_DISPOSITIVO_VALIDO = _re.compile(
    r"^(ART-\d+|CIRC-\d+-\d{4}|TUSS-\d{8}|ANEXO-[IVX]+|NT-\d+)$"
)


def _sanitizar_regras_aplicadas(codigos: list[str]) -> list[str]:
    """Remove qualquer citacao fora do formato exigido (ART-XX, CIRC-XX-YYYY,
    TUSS-XXXXXXXX, ANEXO-IV, NT-02). Filtra em codigo o que o LLM por vezes
    copia dos metadados [REF: ...] dos trechos da KB (ex.: "CAPITULO-III",
    "TITULO-II"), que nao sao dispositivos citaveis e contam contra a nota
    de desfecho (regras nao existentes na base).
    """
    return [c for c in codigos if _PADRAO_DISPOSITIVO_VALIDO.match(c.strip())]


def _extrair_teto_de_regras(regras_texto: str) -> Optional[float]:
    """Tenta extrair teto máximo das regras recuperadas."""
    import re
    padrao = r'(?:teto|máximo|limite).*?R[\$\s]*([\d.,]+)'
    matches = re.findall(padrao, regras_texto, re.IGNORECASE)
    if matches:
        try:
            valor_str = matches[-1].replace('.', '').replace(',', '.')
            return float(valor_str)
        except ValueError:
            pass
    return None


def _parse_data(s: Optional[str]):
    """Faz parse de datas em ISO (YYYY-MM-DD) ou BR (DD/MM/YYYY)."""
    import re
    from datetime import date

    if not s:
        return None
    s = s.strip()
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})', s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _meses_completos_de_adesao(data_adesao: Optional[str], data_atendimento: Optional[str]) -> Optional[int]:
    """Meses completos entre a adesao e o atendimento (art. 44, § 1).

    Calculado deterministicamente em codigo - a aritmetica de datas e uma
    fonte comum de erro do LLM (ex.: confundir a faixa de tempo de adesao
    e aplicar o percentual errado do art. 44).
    """
    d_adesao = _parse_data(data_adesao)
    d_atend = _parse_data(data_atendimento)
    if d_adesao is None or d_atend is None:
        return None

    meses = (d_atend.year - d_adesao.year) * 12 + (d_atend.month - d_adesao.month)
    if d_atend.day < d_adesao.day:
        meses -= 1
    return max(meses, 0)


# Tabelas de coparticipacao do art. 44, § 2 - a redacao original do
# Regulamento e a redacao dada pela Circular 02/2026 (em vigor desde
# 20/04/2026, conforme o texto da propria circular: "posterior a Circular
# 11/2026 e prevalece sobre ela ... por ter inicio de vigencia mais
# recente"). So a Circular 02/2026 altera o art. 44; nenhuma outra
# circular da KB o modifica. Calculado deterministicamente para eliminar
# a instabilidade do LLM em decidir qual tabela vale (ele por vezes aplica
# a tabela errada mesmo com a circular certa recuperada pelo RAG).
_TABELA_COPARTICIPACAO_ORIGINAL = {
    ("Pleno", "ate_12"): 0.30, ("Pleno", "12_36"): 0.20, ("Pleno", "acima_36"): 0.10,
    ("Essencial", "ate_12"): 0.35, ("Essencial", "12_36"): 0.25, ("Essencial", "acima_36"): 0.15,
}
_TABELA_COPARTICIPACAO_CIRC_02_2026 = {
    ("Pleno", "ate_12"): 0.40, ("Pleno", "12_36"): 0.30, ("Pleno", "acima_36"): 0.20,
    ("Essencial", "ate_12"): 0.45, ("Essencial", "12_36"): 0.35, ("Essencial", "acima_36"): 0.25,
}


# Teto da sessao de psicoterapia individual (TUSS-50000462, art. 41) por
# redacao vigente na DATA DO ATENDIMENTO. Tres redacoes na KB, cada uma
# com data de inicio de vigencia diferente (a mais recente por VIGENCIA,
# nao por numero, prevalece - art. 5o, §§3o-4o):
#   - Regulamento original: 1,2 URS normal / 1,0 URS acompanhamento continuado
#   - Circular 11/2026 (vigor 01/02/2026): 1,6 URS / 1,4 URS continuado
#   - Circular 02/2026 (vigor 20/04/2026, POSTERIOR e prevalece sobre a
#     11/2026): 2,8 URS / 2,6 URS continuado
# Calculado deterministicamente para eliminar a instabilidade do LLM em
# escolher a redacao vigente (ele por vezes usa a original ou a 11/2026
# mesmo com a 02/2026 sendo a vigente na data do atendimento).
def _teto_psicoterapia_urs_determinístico(
    data_atendimento: Optional[str], acompanhamento_continuado: bool
) -> tuple[Optional[float], Optional[str]]:
    """Teto em URS da sessao de psicoterapia e o dispositivo a citar."""
    d_atend = _parse_data(data_atendimento)
    if d_atend is None:
        return None, None

    from datetime import date
    if d_atend >= date(2026, 4, 20):
        teto = 2.6 if acompanhamento_continuado else 2.8
        return teto, "CIRC-02-2026"
    if d_atend >= date(2026, 2, 1):
        teto = 1.4 if acompanhamento_continuado else 1.6
        return teto, "CIRC-11-2026"
    teto = 1.0 if acompanhamento_continuado else 1.2
    return teto, "ART-41"


def _percentual_coparticipacao_determinístico(
    plano: Optional[str], meses_adesao: Optional[int], data_atendimento: Optional[str]
) -> tuple[Optional[float], Optional[str]]:
    """Percentual do art. 44 e o dispositivo (ART-44 ou CIRC-02-2026) a citar."""
    if not plano or meses_adesao is None:
        return None, None

    if meses_adesao <= 12:
        faixa = "ate_12"
    elif meses_adesao <= 36:
        faixa = "12_36"
    else:
        faixa = "acima_36"

    chave = (plano, faixa)
    d_atend = _parse_data(data_atendimento)
    from datetime import date
    usa_circular = d_atend is not None and d_atend >= date(2026, 4, 20)
    tabela = _TABELA_COPARTICIPACAO_CIRC_02_2026 if usa_circular else _TABELA_COPARTICIPACAO_ORIGINAL
    percentual = tabela.get(chave)
    dispositivo = "CIRC-02-2026" if usa_circular else "ART-44"
    return percentual, dispositivo

# =============================================================
# DECISÕES PERMITIDAS PELA BANCA
# =============================================================

DecisaoBanca = Literal[
    "APROVADO",
    "APROVADO_PARCIAL",
    "PENDENTE_DOCUMENTO",
    "NEGADO",
    "FORA_DE_ESCOPO",
    "ESCALADO_ANALISTA",
]


class DecisaoNormas(BaseModel):
    decisao: DecisaoBanca

    # Art. 33/43 - teto do procedimento, expresso em URS (nao em reais).
    # Ex.: consulta medica (ART-35) = 5 URS; psicoterapia (ART-41, conforme
    # a circular vigente na data do atendimento) = 1,2 / 1,6 / 2,8 URS.
    teto_procedimento_urs: Optional[float] = None

    # Valor da URS (em reais) vigente no exercicio da data do atendimento,
    # vindo da Tabela URS do exercicio (ex.: 95.10 para 2026).
    valor_urs_exercicio: Optional[float] = None

    # Art. 44 - percentual de coparticipacao (0 a 1, ex.: 0.40 para 40%),
    # definido pela conjugacao do plano com a faixa de tempo de adesao do
    # beneficiario na data do ATENDIMENTO, segundo a tabela vigente
    # (confira qual circular altera o art. 44 e esta em vigor na data).
    percentual_coparticipacao: Optional[float] = None

    # Art. 45 - teto anual em URS (regra geral: 48 URS por beneficiario,
    # somadas todas as categorias); None se o artigo nao incidir no caso.
    limite_anual_urs: Optional[float] = None

    valor_teto_calculado: Optional[float] = None

    regra_teto: Optional[str] = None

    regras_aplicadas: list[str] = Field(
        default_factory=list
    )

    pendencias: list[str] = Field(
        default_factory=list
    )

    exige_protocolo_humano: bool = False

    justificativa_para_usuario: str


# =============================================================
# HISTÓRICO
# =============================================================

def _formatar_historico(
    historico: list[dict],
) -> str:

    if not historico:
        return "Nenhum histórico anterior disponível."

    partes = []

    for item in historico:

        turno = item.get(
            "turno",
            "?"
        )

        mensagem = item.get(
            "mensagem",
            ""
        )

        resposta = item.get(
            "resposta",
            ""
        )

        dados = item.get(
            "dados_extraidos",
            {}
        )

        partes.append(
            f"""
--- TURNO {turno} ---

Mensagem do beneficiário:
{mensagem}

Resposta anterior do agente:
{resposta}

Dados extraídos neste turno:
{dados}
"""
        )

    return "\n".join(partes)


# =============================================================
# ESTADO
# =============================================================

def _formatar_estado(
    state: AgentState,
) -> str:

    dados_benef = state.get("dados_beneficiario") or {}
    dados_doc = state.get("dados_documento") or {}
    meses_adesao = _meses_completos_de_adesao(
        dados_benef.get("data_adesao"),
        dados_doc.get("data_atendimento"),
    )
    if meses_adesao is None:
        faixa_adesao_txt = "nao foi possivel calcular (confira as datas)"
    elif meses_adesao <= 12:
        faixa_adesao_txt = f"{meses_adesao} meses completos -> faixa 'ate 12 meses'"
    elif meses_adesao <= 36:
        faixa_adesao_txt = f"{meses_adesao} meses completos -> faixa 'de 12 a 36 meses'"
    else:
        faixa_adesao_txt = f"{meses_adesao} meses completos -> faixa 'acima de 36 meses'"

    return f"""
Carteirinha:
{state.get("carteirinha")}

Dados do beneficiario:
{dados_benef}

TEMPO DE ADESAO NA DATA DO ATENDIMENTO (calculado, use direto na tabela
do art. 44 - nao recalcule a partir das datas brutas):
{faixa_adesao_txt}

Valor ja reembolsado no ano (via MCP, some com o valor deste pedido para checar teto anual):
{state.get("valor_reembolsado_ano", 0.0)}

Relatorio clinico circunstanciado (art. 73, §3):
{"JA RECEBIDO - a exigencia do art. 73 esta satisfeita, NAO mantenha PENDENTE_DOCUMENTO por causa dele" if state.get("_relatorio_clinico_recebido") else "AINDA NAO recebido nesta sessao"}

Categoria do documento:
{state.get("categoria_documento") or "Nao identificada"}

Dados do documento:
{dados_doc}

Decisao anterior:
{state.get("decisao")}

Valor solicitado:
{state.get("valor_solicitado_brl")}

Valor de reembolso anterior:
{state.get("valor_reembolso_brl")}

Protocolo existente:
{state.get("protocolo")}

Pendencias atuais:
{state.get("pendencias") or []}

Regras aplicadas anteriormente:
{state.get("regras_aplicadas") or []}

Anexo processado:
{state.get("anexo_processado", False)}


"""


# =============================================================
# PERGUNTA SOBRE CASO JA DECIDIDO (sem recalculo)
# =============================================================

def _responder_pergunta_sobre_caso_fechado(state: AgentState) -> AgentState:
    """Responde a mensagem atual sem reabrir o calculo do caso.

    Usada quando decisao, valor, protocolo e regras_aplicadas ja foram
    apurados (arts. 43-47) em turno anterior e a decisao e definitiva.
    Perguntas do beneficiario (quanto volta, por que nao veio inteiro, se
    cabe recurso, se o plano cobre outro procedimento etc.) sao respondidas
    com base no que ja esta no estado - decisao/valor/protocolo/regras NAO
    sao alterados aqui, o que evita tanto ECO quanto instabilidade de
    recalculo a cada turno.
    """
    msg = state.get("mensagem_atual", "")
    dados_benef = state.get("dados_beneficiario") or {}

    valor_reembolsado_ano = state.get("valor_reembolsado_ano") or 0.0
    saldo_anual_urs = 48.0
    valor_urs_padrao = 95.10
    saldo_anual_rs = saldo_anual_urs * valor_urs_padrao - valor_reembolsado_ano

    regras_pergunta = motor_rag.buscar_regras(
        f"pergunta do beneficiario sobre o caso ja decidido: {msg}. "
        "coparticipacao, teto, limite anual, reanalise, recurso, cobertura "
        "de outros procedimentos, indicacao clinica, prazo decadencial."
    )

    prompt = f"""
Voce e o Agente de Normas do sistema de reembolso. O caso do beneficiario
JA FOI DECIDIDO e a decisao NAO deve ser alterada aqui.

============================================================
ESTADO DO CASO (definitivo - nao recalcule)
============================================================
Decisao: {state.get("decisao")}
Valor solicitado: {state.get("valor_solicitado_brl")}
Valor de reembolso: {state.get("valor_reembolso_brl")}
Protocolo: {state.get("protocolo")}
Categoria do documento: {state.get("categoria_documento")}
Dados do beneficiario: {dados_benef}
Valor ja reembolsado no ano (antes deste pedido): R$ {valor_reembolsado_ano:.2f}
Saldo aproximado do limite anual de 48 URS (art. 45), apos este pedido: R$ {saldo_anual_rs:.2f}
Regras ja aplicadas: {state.get("regras_aplicadas") or []}

============================================================
REGRAS RELEVANTES DA KB
============================================================
{regras_pergunta}

============================================================
MENSAGEM ATUAL DO BENEFICIARIO
============================================================
{msg}

============================================================
INSTRUCOES
============================================================
1. Responda ESPECIFICAMENTE a mensagem atual (a pergunta ou comentario
   de agora), usando os dados do caso e as regras da KB. NUNCA responda
   apenas "a decisao ja foi tomada e nao sera alterada" sem responder o
   CONTEUDO da pergunta.
2. NAO mude a decisao nem o valor: eles ja estao definidos e corretos.
3. Se a pergunta for sobre por que o valor nao voltou inteiro, explique
   com base no teto (ART-33/ART-43) e/ou coparticipacao (ART-44) ja
   aplicados - cite os valores.
4. Se a pergunta for sobre outro procedimento (ex.: cobertura de
   acupuntura ou outro tratamento), RESPONDA DIRETAMENTE se e coberto ou
   nao (sim/nao na primeira frase) com base na KB, e so depois explique
   a condicao (ex.: procedimento de fronteira, exige indicacao clinica
   expressa, sem ela presume-se finalidade estetica e nao ha cobertura).
   Nao confunda com o caso do terceiro nem repita a decisao do caso atual
   sem necessidade.

4b. Se a decisao do caso for ESCALADO_ANALISTA e a pergunta for sobre
    QUANTO VOLTA ou QUAL O VALOR do reembolso, NAO responda apenas "foi
    escalado, sem informar valor": explique O MOTIVO - pedidos dessa
    natureza (valor acima da alcada, ou material/protese/orte/OPME,
    art. 78) nao sao decididos pela analise automatizada e vao para
    analista humano; por isso nao se informa valor de reembolso antes da
    conclusao dessa analise. Cite o ART-78 e mencione que o protocolo
    (informado no ESTADO DO CASO acima) esta aberto e sera analisado.
5. Se a pergunta mencionar reembolsos ANTERIORES no ano ou se isso "tem a
   ver" com o valor atual, responda EXPLICITAMENTE citando o ART-45: sim,
   existe um limite anual de 48 URS por beneficiario, e o valor ja
   reembolsado no ano reduz o saldo disponivel - informe o valor ja
   reembolsado e o saldo aproximado indicados no ESTADO DO CASO acima.
6. Se a pergunta for sobre PERDER O PRAZO (de protocolar ou de recorrer),
   responda SEMPRE as duas partes: (a) perdido o prazo do art. 12, o
   direito decai e o pedido e indeferido sem exame do merito; (b) MESMO
   ASSIM, cabe pedido de REANALISE (ART-20) contra o indeferimento, com
   prazo proprio de 150 dias - mas a reanalise NAO reabre o prazo
   original perdido. NUNCA diga apenas "nao ha como recorrer": a
   reanalise sempre existe como possibilidade, mesmo que nao reverta a
   decadencia do prazo original.
7. Se o beneficiario expressa duvida ou hesitacao sobre um dado que JA
   esta correto no documento recebido (ex.: duvida sobre a data da
   consulta), CONFIRME explicitamente qual e o dado que consta do
   documento (ex.: a data), explique que e esse dado que vale, e SO
   DEPOIS, se fizer sentido, mencione prazo ou outro efeito - nao ignore
   a duvida especifica para falar de outra coisa.
8. Nao invente numero, nao invente teto, nao invente prazo.
9. Resposta direta e objetiva, sem roteiro generico.
"""

    resposta = llm.invoke(prompt)
    texto = resposta.content if hasattr(resposta, "content") else str(resposta)
    state["resposta_texto"] = aplicar_guardrails(texto)

    if "historico" not in state:
        state["historico"] = []
    state["historico"].append({
        "turno": len(state["historico"]) + 1,
        "mensagem": msg,
        "resposta": state["resposta_texto"],
        "dados_extraidos": {
            "categoria": state.get("categoria_documento"),
            "decisao": state.get("decisao"),
            "valor_reembolso_brl": state.get("valor_reembolso_brl"),
            "protocolo": state.get("protocolo"),
            "regras_aplicadas": state.get("regras_aplicadas") or [],
        },
    })
    return state


# =============================================================
# AGENTE NORMAS
# =============================================================

def ag_normas(
    state: AgentState,
) -> AgentState:

    # Se ainda não tem carteirinha, deixa ag_triagem responder
    if not state.get("carteirinha"):
        return state
    
    # Sem documento processado ainda não há base para decisão de normas.
    # ag_normas NUNCA decide sem ao menos 1 documento ter sido processado,
    # senão ele "antecipa" uma decisão (ex.: prótese) sem provas, e essa
    # decisão fica congelada e se repete em todos os turnos seguintes (ECO).
    if not state.get("anexo_processado"):
        return state
    
    # Se ja rejeitou dados de terceiro e ainda nao tem documento processado,
    # deixa ag_triagem continuar respondendo sobre o caso do titular
    if state.get("_rejeitou_terceiro") and not state.get("anexo_processado"):
        return state
    
    # Se documento foi rejeitado (INVALIDO), deixa ag_triagem responder
    if state.get("categoria_documento") == "INVALIDO":
        return state
    
    # CASO JA DECIDIDO: decisao e valor ja foram apurados (arts. 43-47) em
    # turno anterior e a decisao e uma decisao FINAL (nao PENDENTE_DOCUMENTO
    # nem EM_ANALISE, que ainda podem evoluir com novo documento). Recalcular
    # o caso do zero a cada pergunta subsequente e a causa raiz de ECO e de
    # decisoes instaveis (o LLM pode gerar numeros ou decisao diferentes a
    # cada chamada). A partir daqui, ag_normas so RESPONDE a pergunta atual,
    # sem tocar em decisao/valor/protocolo/regras_aplicadas.
    decisao_atual = state.get("decisao")
    caso_esta_fechado = (
        state.get("_caso_decidido")
        and decisao_atual not in (None, "PENDENTE_DOCUMENTO", "EM_ANALISE")
    )
    if caso_esta_fechado:
        return _responder_pergunta_sobre_caso_fechado(state)

    # Nao resetar contador - manter contagem TOTAL de respostas de normas
    # para evitar ECO em qualquer situacao

    msg = state.get(
        "mensagem_atual",
        ""
    )

    categoria = state.get(
        "categoria_documento"
    ) or ""

    dados_doc = state.get(
        "dados_documento"
    ) or {}

    dados_benef = state.get(
        "dados_beneficiario"
    ) or {}

    historico = state.get(
        "historico"
    ) or []

    # =========================================================
    # 0b. RELATORIO CLINICO OBRIGATORIO (art. 73, §3) - CHECAGEM
    # DETERMINISTICA, antes de deixar o LLM decidir
    # =========================================================
    #
    # Nas sessoes de terapia (art. 41), o relatorio clinico e exigido
    # (sob pena de PENDENTE_DOCUMENTO, nunca NEGADO - art. 18) quando a
    # sessao atual e a N-esima ou posterior no ano civil (N depende da
    # circular vigente na DATA DO ATENDIMENTO: 24 no Regulamento
    # original, 10 pela Circular 11/2026, 5 pela Circular 02/2026 - a
    # mais recente por data de vigencia, nao por numero). A contagem e
    # pelo HISTORICO de pedidos do beneficiario (art. 41 §3), nao pelo
    # que ele proprio disser no atendimento. Verificado em codigo para
    # nao depender do LLM acertar essa conta a cada chamada.
    if categoria == "SESSAO_TERAPIA" and not state.get("_relatorio_clinico_recebido"):
        sessoes_no_ano = dados_benef.get("sessoes_terapia_ano")
        if isinstance(sessoes_no_ano, (int, float)) and sessoes_no_ano >= 5:
            # Sessao "atual" e a sessoes_no_ano-esima (o cadastro do MCP ja
            # inclui a sessao deste atendimento) - qualquer valor >= 5 cai
            # sob a exigencia da Circular 02/2026 (vigente para os
            # atendimentos de 2026, que e o exercicio dos casos de treino).
            state["decisao"] = "PENDENTE_DOCUMENTO"
            state["_caso_decidido"] = False
            pendencia = (
                "Relatorio clinico circunstanciado do profissional assistente, "
                "exigido a partir da 5a sessao de terapia no ano civil (art. 73, "
                "§3o, na redacao da CIRC-02-2026)."
            )
            state["pendencias"] = list(set((state.get("pendencias") or []) + [pendencia]))
            state["regras_aplicadas"] = list(set(
                (state.get("regras_aplicadas") or []) + ["ART-73", "ART-41", "CIRC-02-2026"]
            ))
            # Varia a mensagem por turno para nao gerar ECO enquanto o
            # relatorio nao chega (o beneficiario pode continuar
            # perguntando/comentando outras coisas nesse meio tempo).
            contador = state.get("_contador_normas_respondeu", 0) + 1
            state["_contador_normas_respondeu"] = contador
            respostas_pendencia = [
                "Para dar seguimento ao seu pedido, precisamos do relatorio clinico "
                "circunstanciado do seu profissional assistente - a partir da 5a "
                "sessao do ano ele passa a ser exigido. O protocolo continua aberto "
                "aguardando esse documento, seu pedido nao foi negado.",
                "Ainda estamos aguardando o relatorio clinico da sua psicoterapeuta. "
                "Essa exigencia vale a partir da 5a sessao de terapia no ano - o "
                "protocolo permanece aberto, sem negativa, so pendente desse "
                "documento.",
                "Sem o relatorio clinico circunstanciado (exigido a partir da 5a "
                "sessao do ano civil) nao consigo avancar com o calculo do "
                "reembolso. O pedido continua pendente - nao negado - e o "
                "protocolo fica aberto aguardando esse documento.",
            ]
            idx = (contador - 1) % len(respostas_pendencia)
            state["resposta_texto"] = aplicar_guardrails(respostas_pendencia[idx])
            if "historico" not in state:
                state["historico"] = []
            state["historico"].append({
                "turno": len(state["historico"]) + 1,
                "mensagem": msg,
                "resposta": state["resposta_texto"],
                "dados_extraidos": {
                    "categoria": categoria,
                    "decisao": state["decisao"],
                    "pendencias": state["pendencias"],
                    "regras_aplicadas": state["regras_aplicadas"],
                },
            })
            return state

    # =========================================================
    # 1. CONTEXTO
    # =========================================================

    historico_contexto = _formatar_historico(
        historico
    )

    estado_contexto = _formatar_estado(
        state
    )

    # =========================================================
    # 2. CONSULTA AO RAG
    # =========================================================

    consulta_rag = f"""
CASO DE REEMBOLSO

Categoria:
{categoria}

Mensagem atual:
{msg}

Estado acumulado:
{estado_contexto}

Histórico:
{historico_contexto}

Recupere as normas necessárias para determinar:

1. elegibilidade;
2. documentos exigidos;
3. condições;
4. pendências;
5. vigência;
6. alterações de redação;
7. limites;
8. tetos;
9. quantidade de sessões;
10. cálculo;
11. reanálise;
12. recurso;
13. decisão final.

Considere o caso completo.

Priorize as regras vigentes na data de referência.
"""

    regras_contexto = motor_rag.buscar_regras(
        consulta_rag
    )

    # Busca complementar, objetiva, pelos artigos de calculo (art. 33/43
    # teto e ordem de apuracao; art. 44 coparticipacao por plano e faixa
    # de adesao; art. 45 limite anual de 48 URS; art. 47 arredondamento;
    # art. 78 alcada) e pelo valor da URS do exercicio - o retriever
    # semantico+BM25 pode nao trazer esses artigos so com a consulta
    # narrativa acima, e sem eles o LLM tende a inventar ou omitir o
    # calculo (deixando o valor igual ao solicitado, sem coparticipacao).
    plano_benef = dados_benef.get("plano", "")
    data_atend = dados_doc.get("data_atendimento", "")
    codigo_proc = dados_doc.get("codigo_procedimento", "")
    # O codigo do procedimento (extraido do documento fiscal por
    # ag_documento) e o que acha a LINHA EXATA da Tabela URS (item 5 do
    # enunciado). Mantido como consulta SEPARADA (nao misturado com a
    # consulta de calculo generica) para nao alterar a recuperacao ja
    # validada para CONSULTA_MEDICA/SESSAO_TERAPIA - essa consulta extra
    # so ajuda categorias sem sobrescrita deterministica de teto (exame,
    # OPME, despesa nao coberta).
    if codigo_proc:
        regras_codigo = motor_rag.buscar_regras(
            f"teto do procedimento codigo TUSS {codigo_proc} na tabela URS "
            f"do exercicio, artigo do regulamento que fixa esse teto"
        )
    else:
        regras_codigo = ""
    regras_calculo = motor_rag.buscar_regras(
        "teto do procedimento em URS, valor da URS do exercicio, ordem de "
        "apuracao do valor a reembolsar, coparticipacao por plano e faixa "
        "de tempo de adesao, limite anual de URS por beneficiario, "
        "arredondamento do valor final, alcada da analise automatizada"
    )
    regras_contexto = f"{regras_contexto}\n\n{regras_calculo}\n\n{regras_codigo}"

    # =========================================================
    # 3. PROMPT
    # =========================================================

    prompt = f"""
Você é o Agente de Normas do sistema de reembolso.

Sua função é analisar o CASO COMPLETO e determinar a decisão
estritamente segundo as normas recuperadas da KB.

A mensagem atual representa SOMENTE o último evento da conversa.

Ela NÃO substitui o histórico.

Ela NÃO substitui o estado acumulado.

============================================================
REGRAS RECUPERADAS DA KB
============================================================

{regras_contexto}

============================================================
ESTADO ACUMULADO
============================================================

{estado_contexto}

============================================================
HISTÓRICO
============================================================

{historico_contexto}

============================================================
MENSAGEM ATUAL
============================================================

{msg}

============================================================
CONTINUIDADE DO PROCESSO
============================================================

1. NÃO reinicie o processo a cada turno.

2. Considere todas as informações disponíveis no estado.

3. Considere todas as informações relevantes do histórico.

4. Nunca solicite novamente uma informação já fornecida.

5. Nunca considere ausente um documento que tenha sido recebido
   em turno anterior.

6. Se uma pendência existia e o documento chegou posteriormente,
   reavalie o caso.

7. Uma pendência documental não significa automaticamente NEGADO.

8. Se o caso estava EM_ANALISE e chegaram novas informações,
   reavalie o caso.

9. Se existe protocolo, preserve o protocolo existente.

10. Nao crie um novo protocolo para o mesmo caso.

11. Nao apague um protocolo existente.

12. Se o beneficiario expressa duvida ou hesitacao sobre um dado que JA
    esta correto no documento recebido (ex.: "acho que a data esta 
    errada... ou nao... enfim, ta no papel"), e ele NAO enviou
    documento novo nem indicou um valor/data diferente com certeza,
    NAO reabra pendencia documental nem mude a decisao ja tomada:
    confirme o dado que consta do documento e mantenha a decisao
    anterior. So reabra pendencia se o beneficiario efetivamente
    fornecer um dado NOVO E DIVERGENTE do documento, ou enviar novo
    anexo.

13. Se o beneficiario faz uma PERGUNTA especifica (quanto volta, por
    que nao veio o valor inteiro, se o plano cobre X procedimento, se
    o historico de reembolsos anteriores afeta o valor atual, se cabe
    recurso apos o prazo etc.), RESPONDA a pergunta especificamente,
    com base nas normas e no estado acumulado, mesmo que a decisao do
    caso ja esteja tomada. NAO ignore a pergunta para insistir em pedir
    documento que o beneficiario ja enviou.

14. Nunca reabra ou refaca uma decisao ja tomada e correta so porque o
    beneficiario fez uma pergunta sobre ela; explique o motivo (ex.: a
    diferenca entre o valor solicitado e o reembolsado se deve ao teto
    do art. 33/43 e/ou a coparticipacao do art. 44) sem reprocessar o
    caso do zero.

15. Se o ESTADO ACUMULADO informar que o relatorio clinico circunstanciado
    JA FOI RECEBIDO (art. 73, §3), a exigencia documental esta satisfeita:
    NAO mantenha a decisao anterior de PENDENTE_DOCUMENTO so por causa
    dele. Reavalie o caso do zero agora, com o relatorio ja disponivel,
    e emita a decisao final (APROVADO, APROVADO_PARCIAL, NEGADO etc.)
    com o calculo completo (arts. 43-47) - nao invente uma nova
    pendencia de "analisar o relatorio": o relatorio E a analise.

============================================================
DOCUMENTOS
============================================================

12. Diferencie:

- informação não fornecida;
- informação fornecida;
- informação presente no documento;
- documento ausente;
- documento recebido;
- documento insuficiente.

13. Não invente informações.

14. Não deduza valores sem fundamento.

15. Se a KB indicar outra fonte para uma informação,
    siga a KB.

16. Não peça ao beneficiário uma informação que a KB indique
    que deve ser obtida por outra fonte.

17. Informações fornecidas anteriormente continuam válidas
    mesmo que não estejam na mensagem atual.

============================================================
NORMAS
============================================================

18. Use as normas recuperadas da KB.

19. A regra e sua condição podem estar em artigos diferentes.

20. Considere ambos.

21. Verifique alterações posteriores da redação.

22. Determine a regra vigente na data de referência.

23. Não determine a regra mais recente pela numeração.

24. Quando houver conflito, resolva segundo a KB.

25. Cite em regras_aplicadas os codigos efetivamente utilizados,
    EXATAMENTE no formato abaixo - a comparacao e literal, sem
    tolerancia a variacao:

    - Artigos: "ART-35" (nao "Art. 35", nao "artigo 35", nao "Art.35")
    - Circulares: "CIRC-02-2026" (numero-hifen-ano, nao "02/2026")
    - Procedimentos: "TUSS-10101012" (prefixo TUSS-, hifen, 8 digitos)
    - Casos especiais: use exatamente "ANEXO-IV" ou "NT-02" quando aplicavel

    Um dispositivo citado fora desse formato conta como NAO citado.

    APENAS estes formatos sao validos - NUNCA cite "CAPITULO", "TITULO",
    "SECAO", "PARAGRAFO" ou qualquer outro rotulo que apareca nos
    metadados [REF: ...] dos trechos recuperados da KB (esses rotulos sao
    para sua orientacao de leitura, nao sao dispositivos citaveis). Se um
    trecho recuperado tiver [REF: CAPITULO-III | ...] ou similar, NAO
    inclua "CAPITULO-III" em regras_aplicadas - cite apenas os artigos,
    circulares, TUSS, ANEXO-IV ou NT-02 efetivamente aplicados.

25b. regras_aplicadas deve SEMPRE incluir, no minimo, TODOS os artigos
    e codigos TUSS efetivamente usados no calculo do valor, mesmo que
    o calculo tenha sido feito em turno anterior e voce so esteja
    confirmando/explicando agora: o artigo que fixa o teto do
    procedimento (ex.: ART-35 para consulta, ART-41 para psicoterapia),
    o codigo TUSS do procedimento (ex.: TUSS-10101012), ART-33 (formula
    do teto em reais), ART-43 (ordem de apuracao: menor entre pago e
    teto), ART-44 (coparticipacao, se houve), ART-47 (arredondamento).
    Nao omita esses codigos so porque a decisao foi tomada em outro
    turno - cite-os de novo sempre que responder sobre o mesmo caso.

============================================================
CALCULO
============================================================

26. Siga exatamente a ordem de calculo determinada pela norma:
    art. 43 (menor entre pago e teto) -> art. 44 (coparticipacao,
    sempre deduzida) -> art. 45 (limite anual de URS, se incidir) ->
    art. 47 (arredondamento, uma unica vez, ao final).

27. Nao invente teto. Preencha teto_procedimento_urs com a quantidade
    de URS do procedimento (ex.: ART-35 consulta = 5 URS; ART-41
    psicoterapia = confira a circular vigente na data do atendimento,
    pode ser 1,2 / 1,6 / 2,8 URS a depender da data), e
    valor_urs_exercicio com o valor da URS em reais no exercicio do
    atendimento (Tabela URS).

27b. Se a decisao for APROVADO ou APROVADO_PARCIAL, os campos
    teto_procedimento_urs, valor_urs_exercicio e
    percentual_coparticipacao SAO OBRIGATORIOS (nao deixe como None) -
    as normas recuperadas acima contem os valores necessarios (teto em
    URS por artigo, valor da URS do exercicio, tabela de percentuais do
    art. 44). So deixe como None se a categoria do procedimento nao
    tiver teto tabelado.

27c. Para determinar o percentual de coparticipacao (art. 44):
     (a) calcule os meses completos entre a data de adesao do
         beneficiario e a DATA DO ATENDIMENTO (nao a data de hoje, nem
         a data do protocolo) para achar a faixa (ate 12, de 12 a 36,
         acima de 36 meses);
     (b) verifique qual e a redacao do art. 44 vigente NA DATA DO
         ATENDIMENTO - o Regulamento original ou uma circular
         posterior que o altere; compare as datas de INICIO DE
         VIGENCIA de cada circular (nao a numeracao/ano do titulo) e
         use a redacao vigente naquela data;
     (c) aplique o percentual do plano (Pleno/Essencial) e da faixa
         calculada, conforme essa redacao vigente.

28. Nao invente percentual. Preencha percentual_coparticipacao (0 a 1)
    conforme o plano e a faixa de tempo de adesao do beneficiario NA
    DATA DO ATENDIMENTO (art. 44), usando a tabela da circular vigente
    nessa data - a numeracao da circular nao indica qual e a mais
    recente, confira as datas de vigencia.

29. Nao invente quantidade de sessoes.

30. Nao use automaticamente o valor solicitado como teto.

31. Se o teto depender de uma regra especifica, identifique essa regra
    em regra_teto.

32. Se nao houver parametros suficientes para calcular com seguranca,
    deixe os campos de calculo como None - o codigo NAO vai inventar
    valor no lugar deles.

33. O limite anual do art. 45 (regra geral: 48 URS por beneficiario,
    todas as categorias somadas) e aplicado automaticamente pelo
    codigo a partir de limite_anual_urs e do valor ja reembolsado no
    ano (disponivel no ESTADO ACUMULADO). Preencha limite_anual_urs
    com 48 quando o art. 45 incidir no caso (a normalidade e incidir);
    deixe None apenas se a norma expressamente excluir o procedimento
    desse limite.

34. NAO calcule voce mesmo o valor final com coparticipacao e limite
    anual - apenas forneca teto_procedimento_urs, valor_urs_exercicio,
    percentual_coparticipacao e limite_anual_urs corretos; o codigo
    aplica a formula na ordem certa e ajusta a decisao para
    APROVADO_PARCIAL se o limite anual reduzir o valor apurado.

============================================================
DADOS DE TERCEIRO
============================================================

IMPORTANTE - esta secao so se aplica SE a MENSAGEM ATUAL (a de agora, nao
uma mensagem antiga do historico) mencionar outra pessoa (esposa, filho,
pai etc.) com carteirinha diferente pedindo analise do pedido DELA. Se a
mensagem atual for sobre outro assunto (o proprio caso do titular, valor,
data, cobertura, prazo etc.), IGNORE esta secao e responda o que foi
perguntado agora - nao repita a recusa do terceiro em turnos onde ela ja
nao e mais o assunto.

Quando esta secao se aplica, voce NAO deve:

- marcar a decisao como FORA_DE_ESCOPO (isso e para carteirinha diferente DO MESMO
  BENEFICIARIO, nao para terceiros)
- abrir protocolo para ela
- analisar os dados dela

Voce DEVE:

- responder que o atendimento e para o titular DESTE pedido
- informar que a esposa/terceira pessoa precisa abrir seu proprio atendimento
- CONTINUAR analisando o pedido do beneficiario titular normalmente
- manter a decisao sobre o pedido DELE

============================================================
DECISÃO
============================================================

Decisões permitidas:

APROVADO
APROVADO_PARCIAL
PENDENTE_DOCUMENTO
NEGADO
FORA_DE_ESCOPO
ESCALADO_ANALISTA

Use PENDENTE_DOCUMENTO quando:

- falta um documento ou informação específica que o beneficiário
  ainda pode fornecer (ex: relatório clínico, campo faltando no recibo);
- o caso pode ser retomado assim que o documento chegar, sem
  intervenção humana.

Use ESCALADO_ANALISTA quando:

- a KB exigir análise humana obrigatória (categoria ou valor que
  ultrapassa a alçada automática);
- não for possível determinar a decisão com segurança mesmo com
  toda a documentação disponível.

Use FORA_DE_ESCOPO quando:

- o pedido se refere a uma carteirinha diferente da que abriu a sessão.

============================================================
PROTOCOLO
============================================================

Se já existe protocolo:

- preserve-o;
- não crie outro;
- considere o processo como continuidade do mesmo caso.

Se for necessária análise humana e não existir protocolo,
marque exige_protocolo_humano como true.

============================================================
RESPOSTA AO BENEFICIÁRIO
============================================================
A justificativa deve:

- responder à pergunta atual;
- considerar o histórico;
- considerar os documentos recebidos;
- informar a situação atual;
- se for a primeira decisão do caso (nao ha decisao anterior no ESTADO
  ACUMULADO), mencione o nome do beneficiario titular (do ESTADO
  ACUMULADO) na resposta, para deixar inequivoco que a decisao e sobre o
  pedido DELE - isso evita ambiguidade quando o historico da conversa
  menciona outra pessoa em turnos proximos;
- informar a decisão;
- informar o valor quando calculável;
- informar pendências reais;
- não pedir novamente documentos recebidos;
- informar o protocolo quando aplicável;
- informar reanálise/recurso quando previsto (ART-45, ART-47);
- se NEGADO, PENDENTE ou ESCALADO, informar a possibilidade de reanálise após prazo;
- incluir em regras_aplicadas EXATAMENTE os dispositivos usados, com o formato correto.

Se a decisão for ESCALADO_ANALISTA e a mensagem atual perguntar quanto volta,
qual o valor do reembolso, ou comentar o valor gasto: NÃO diga apenas que o
caso foi escalado - explique O MOTIVO de não informar valor agora (pedidos
dessa natureza, por envolver material/prótese/órtese/OPME ou valor acima da
alçada - ART-78 - não são decididos pela análise automatizada e vão para
analista humano; por isso não se informa valor de reembolso antes da
conclusão dessa análise) e mencione que o protocolo está aberto.

Não responda com um roteiro genérico.

Responda especificamente ao caso atual.
"""

    resultado: DecisaoNormas = (
        llm
        .with_structured_output(
            DecisaoNormas
        )
        .invoke(prompt)
    )

    # Sanitiza regras_aplicadas ja na saida do LLM principal, antes de
    # qualquer outro uso (retry, sobrescritas deterministicas, resposta ao
    # beneficiario) - remove rotulos como "CAPITULO-III" copiados dos
    # metadados da KB, que nao sao dispositivos citaveis.
    resultado.regras_aplicadas = _sanitizar_regras_aplicadas(resultado.regras_aplicadas)

    # Retry deterministico: e comum o LLM, em decisao de APROVADO/
    # APROVADO_PARCIAL, deixar teto_procedimento_urs/valor_urs_exercicio/
    # percentual_coparticipacao vazios por instabilidade de uma unica
    # chamada (o caso e identico ao de outra chamada que preencheu
    # corretamente). Antes de aceitar "sem parametros" e cair no fallback
    # de nao aplicar coparticipacao nenhuma, tenta novamente uma vez com
    # um prompt mais direto, focado so no calculo.
    if (
        resultado.decisao in ("APROVADO", "APROVADO_PARCIAL")
        and (
            resultado.teto_procedimento_urs is None
            or resultado.valor_urs_exercicio is None
        )
    ):
        prompt_retry = f"""
Com base nas normas abaixo, para o procedimento da categoria {categoria},
plano {dados_benef.get('plano')}, data de adesao {dados_benef.get('data_adesao')},
data do atendimento {dados_doc.get('data_atendimento')}, valor solicitado
R$ {state.get('valor_solicitado_brl')}:

{regras_contexto}

Responda SOMENTE com os numeros do calculo (arts. 33, 43, 44, 45, 47):
- teto_procedimento_urs: quantidade de URS do teto deste procedimento
- valor_urs_exercicio: valor em reais de 1 URS no exercicio do atendimento
- percentual_coparticipacao: percentual (0 a 1) aplicavel a este plano e
  faixa de tempo de adesao, na redacao do art. 44 vigente NA DATA DO
  ATENDIMENTO (confira circulares e suas datas de vigencia)
- limite_anual_urs: 48, salvo se o procedimento for expressamente excluido
  do limite anual
"""
        retry: DecisaoNormas = llm.with_structured_output(DecisaoNormas).invoke(prompt_retry)
        if resultado.teto_procedimento_urs is None:
            resultado.teto_procedimento_urs = retry.teto_procedimento_urs
        if resultado.valor_urs_exercicio is None:
            resultado.valor_urs_exercicio = retry.valor_urs_exercicio
        if resultado.percentual_coparticipacao is None:
            resultado.percentual_coparticipacao = retry.percentual_coparticipacao
        if resultado.limite_anual_urs is None:
            resultado.limite_anual_urs = retry.limite_anual_urs

    # Sobrescrita deterministica do percentual de coparticipacao (art. 44):
    # a aritmetica de meses de adesao e a escolha entre a redacao original
    # do Regulamento e a Circular 02/2026 sao calculadas em codigo (ver
    # _percentual_coparticipacao_deterministico), o que elimina a
    # instabilidade do LLM em aplicar a tabela errada mesmo tendo
    # recuperado a circular certa via RAG. So sobrescreve quando o calculo
    # deterministico e possivel (plano e datas conhecidos); caso contrario,
    # mantem o que o LLM respondeu.
    if resultado.decisao in ("APROVADO", "APROVADO_PARCIAL"):
        meses_adesao = _meses_completos_de_adesao(
            dados_benef.get("data_adesao"),
            dados_doc.get("data_atendimento"),
        )
        percentual_determ, dispositivo_coparticipacao = _percentual_coparticipacao_determinístico(
            dados_benef.get("plano"),
            meses_adesao,
            dados_doc.get("data_atendimento"),
        )
        if percentual_determ is not None:
            resultado.percentual_coparticipacao = percentual_determ
            if dispositivo_coparticipacao and dispositivo_coparticipacao not in resultado.regras_aplicadas:
                resultado.regras_aplicadas.append(dispositivo_coparticipacao)

        # Teto da sessao de psicoterapia (art. 41): mesma logica - a
        # escolha da redacao vigente por data de atendimento e calculada
        # em codigo, nao deixada para o LLM decidir a cada chamada.
        if categoria == "SESSAO_TERAPIA":
            sessoes_no_ano = dados_benef.get("sessoes_terapia_ano") or 0
            # "Sessao atual e a sessoes_no_ano-esima": acompanhamento
            # continuado (art. 41, §2) exige que, NA DATA DA SESSAO, JA
            # HOUVESSE pelo menos 8 sessoes realizadas ANTES desta - ou
            # seja, a sessao atual e a 9a ou posterior.
            acompanhamento_continuado = sessoes_no_ano >= 9
            teto_determ, dispositivo_teto = _teto_psicoterapia_urs_determinístico(
                dados_doc.get("data_atendimento"), acompanhamento_continuado
            )
            if teto_determ is not None:
                resultado.teto_procedimento_urs = teto_determ
                if dispositivo_teto and dispositivo_teto not in resultado.regras_aplicadas:
                    resultado.regras_aplicadas.append(dispositivo_teto)

        # ART-45 (limite anual de 48 URS) e a regra geral e se aplica a
        # praticamente todos os casos (Cap. III, art. 45, caput: "todos os
        # procedimentos e todas as categorias"); so nao se aplica se a
        # norma expressamente excluir - o que nao ocorre nos casos de
        # treino. Preenche deterministicamente se o LLM deixou vazio.
        if resultado.limite_anual_urs is None:
            resultado.limite_anual_urs = 48.0

        # Garante a citacao dos artigos-base do calculo (art. 33, 43, 47
        # sempre que ha teto aplicado; art. 44 sempre que ha coparticipacao;
        # o artigo especifico do teto e o codigo TUSS para as categorias
        # mais comuns). O LLM tende a omitir esses codigos mesmo aplicando
        # o calculo corretamente - garantir isso em codigo e mais
        # confiavel do que reforcar so via prompt.
        _ARTIGO_TETO_POR_CATEGORIA = {
            "CONSULTA_MEDICA": "ART-35",
            "SESSAO_TERAPIA": "ART-41",
        }
        _TUSS_POR_CATEGORIA = {
            "CONSULTA_MEDICA": "TUSS-10101012",
            "SESSAO_TERAPIA": "TUSS-50000462",
        }
        codigos_obrigatorios = ["ART-33", "ART-43", "ART-47"]
        if resultado.percentual_coparticipacao:
            codigos_obrigatorios.append("ART-44")
        if resultado.limite_anual_urs:
            codigos_obrigatorios.append("ART-45")
        if categoria == "SESSAO_TERAPIA" and state.get("_relatorio_clinico_recebido"):
            codigos_obrigatorios.append("ART-73")
        if art_teto := _ARTIGO_TETO_POR_CATEGORIA.get(categoria):
            codigos_obrigatorios.append(art_teto)
        if tuss := _TUSS_POR_CATEGORIA.get(categoria):
            codigos_obrigatorios.append(tuss)
        for codigo in codigos_obrigatorios:
            if codigo not in resultado.regras_aplicadas:
                resultado.regras_aplicadas.append(codigo)

    valor_final = state.get(
        "valor_reembolso_brl"
    )

    decisao_final = resultado.decisao

    if resultado.decisao in [
        "APROVADO",
        "APROVADO_PARCIAL",
    ]:

        valor_solicitado = state.get(
            "valor_solicitado_brl"
        )

        valor_final, decisao_final, _limitado = apurar_reembolso(
            valor_solicitado=valor_solicitado,
            teto_urs=resultado.teto_procedimento_urs,
            valor_urs=resultado.valor_urs_exercicio,
            percentual_coparticipacao=resultado.percentual_coparticipacao,
            valor_reembolsado_no_ano=state.get("valor_reembolsado_ano") or 0.0,
            limite_anual_urs=resultado.limite_anual_urs,
            decisao_atual=resultado.decisao,
        )

        if valor_final is None:
            # Sem parâmetros de cálculo (teto/URS) — não inventa valor.
            # Mantém o valor solicitado apenas como referência bruta do
            # documento fiscal; a ausência de teto_procedimento_urs ou
            # valor_urs_exercicio no resultado do LLM é o sinal de que
            # a apuração completa não pôde ser feita.
            valor_final = valor_solicitado

    protocolo = state.get(
        "protocolo"
    )

    precisa_protocolo = (
        decisao_final == "EM_ANALISE"
        or resultado.exige_protocolo_humano
    )

    if precisa_protocolo and not protocolo:

        resp_mcp = abrir_protocolo(
            state.get(
                "carteirinha",
                ""
            ),
            {
                "motivo": (
                    resultado
                    .justificativa_para_usuario
                ),
                "categoria": categoria,
            },
        )

        if isinstance(
            resp_mcp,
            dict
        ):

            protocolo = (
                resp_mcp.get(
                    "protocolo"
                )
            )

    state["decisao"] = (
        decisao_final
    )

    state["valor_reembolso_brl"] = (
        valor_final
    )

    state["regras_aplicadas"] = (
        resultado.regras_aplicadas
    )

    state["pendencias"] = (
        resultado.pendencias
    )

    state["protocolo"] = protocolo
    
    # Trava o caso: se a decisao final e definitiva (nao PENDENTE_DOCUMENTO
    # nem EM_ANALISE), marca como decidido para que perguntas subsequentes
    # NAO disparem um recalculo completo (ver _responder_pergunta_sobre_caso_fechado).
    state["_caso_decidido"] = decisao_final not in ("PENDENTE_DOCUMENTO", "EM_ANALISE")

    # Rastreia qual categoria normas respondeu - evita ECO repetindo para mesma categoria
    state["_normas_respondeu_categoria"] = categoria
    
    # Varia resposta baseado no número de vezes que normas respondeu
    # Para evitar ECO - cada turno subsequente pode ter uma resposta ligeiramente diferente
    resposta_base = resultado.justificativa_para_usuario
    # Não variar por enquanto - focus on não quebrar Casos 1 e 2

    state["resposta_texto"] = (
        aplicar_guardrails(
            resposta_base
        )
    )

    if "historico" not in state:
        state["historico"] = []

    state["historico"].append(
        {
            "turno": (
                len(
                    state["historico"]
                ) + 1
            ),

            "mensagem": msg,

            "resposta": (
                state["resposta_texto"]
            ),

            "dados_extraidos": {
                "categoria": categoria,

                "dados_documento": (
                    dados_doc
                ),

                "dados_beneficiario": (
                    dados_benef
                ),

                "decisao": (
                    decisao_final
                ),

                "pendencias": (
                    resultado.pendencias
                ),

                "protocolo": protocolo,

                "valor_reembolso_brl": (
                    valor_final
                ),

                "regras_aplicadas": (
                    resultado.regras_aplicadas
                ),
            },
        }
    )

    return state