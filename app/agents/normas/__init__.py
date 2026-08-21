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
from app.calculo import calcular_valor_reembolso


motor_rag = MotorRAG()
llm = criar_llm()


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

    return f"""
Carteirinha:
{state.get("carteirinha")}

Dados do beneficiário:
{state.get("dados_beneficiario") or {}}

Categoria do documento:
{state.get("categoria_documento") or "Não identificada"}

Dados do documento:
{state.get("dados_documento") or {}}

Decisão anterior:
{state.get("decisao")}

Valor solicitado:
{state.get("valor_solicitado_brl")}

Valor de reembolso anterior:
{state.get("valor_reembolso_brl")}

Protocolo existente:
{state.get("protocolo")}

Pendências atuais:
{state.get("pendencias") or []}

Regras aplicadas anteriormente:
{state.get("regras_aplicadas") or []}

Anexo processado:
{state.get("anexo_processado", False)}
"""


# =============================================================
# AGENTE NORMAS
# =============================================================

def ag_normas(
    state: AgentState,
) -> AgentState:

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

    # =========================================================
    # 3. PROMPT
    # =========================================================

    prompt = f"""
Você é o Agente de Normas do sistema de reembolso da SaúdeMais.

Data de referência:
2026-08-20.

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

10. Não crie um novo protocolo para o mesmo caso.

11. Não apague um protocolo existente.

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

25. Cite em regras_aplicadas os códigos efetivamente utilizados.

============================================================
CÁLCULO
============================================================

26. Siga exatamente a ordem de cálculo determinada pela norma.

27. Não invente teto.

28. Não invente percentual.

29. Não invente quantidade de sessões.

30. Não use automaticamente o valor solicitado como teto.

31. Se o teto depender de uma regra específica, identifique
    essa regra em regra_teto.

32. Se não houver parâmetros suficientes para calcular com
    segurança, não invente um valor.

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
- informar a decisão;
- informar o valor quando calculável;
- informar pendências reais;
- não pedir novamente documentos recebidos;
- informar o protocolo quando aplicável;
- informar reanálise/recurso quando previsto.

Não responda com um roteiro genérico.

Responda especificamente ao caso atual.
"""

    # =========================================================
    # 4. DECISÃO ESTRUTURADA
    # =========================================================

    resultado: DecisaoNormas = (
        llm
        .with_structured_output(
            DecisaoNormas
        )
        .invoke(prompt)
    )

    # =========================================================
    # 5. CÁLCULO
    # =========================================================

    valor_final = state.get(
        "valor_reembolso_brl"
    )

    if resultado.decisao in [
        "APROVADO",
        "APROVADO_PARCIAL",
    ]:

        valor_solicitado = state.get(
            "valor_solicitado_brl"
        )

        if valor_solicitado is not None:

            teto = (
                resultado.valor_teto_calculado
            )

            if teto is not None:

                valor_final = (
                    calcular_valor_reembolso(
                        valor_solicitado,
                        teto,
                    )
                )

    # =========================================================
    # 6. PROTOCOLO
    # =========================================================

    # IMPORTANTE:
    # Preserva o protocolo anterior.

    protocolo = state.get(
        "protocolo"
    )

    precisa_protocolo = (
        resultado.decisao == "EM_ANALISE"
        or resultado.exige_protocolo_humano
    )

    # Só cria protocolo se ainda não existir.

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

    # =========================================================
    # 7. ATUALIZA ESTADO
    # =========================================================

    state["decisao"] = (
        resultado.decisao
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

    state["resposta_texto"] = (
        aplicar_guardrails(
            resultado
            .justificativa_para_usuario
        )
    )

    # =========================================================
    # 8. HISTÓRICO
    # =========================================================

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
                    resultado.decisao
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