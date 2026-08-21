from langgraph.graph import StateGraph, END

from app.agents import AgentState
from app.agents.triagem import ag_triagem
from app.agents.documento import ag_documento
from app.agents.normas import ag_normas


def rotear_proximo_no(state: AgentState) -> str:
    """
    Decide qual agente deve processar o estado atual.
    """

    # =========================================================
    # 1. Ainda não temos carteirinha
    # =========================================================
    #
    # A triagem deve responder ao beneficiário e encerrar
    # este turno até que a carteirinha seja informada.
    #

    if not state.get("carteirinha"):
        return END

    # =========================================================
    # 2. Existe anexo novo ainda não processado
    # =========================================================
    #
    # NÃO usamos mais:
    #
    #     not state.get("categoria_documento")
    #
    # porque a categoria pode pertencer a um documento anterior.
    #
    # Exemplo:
    #
    # Turno 5:
    #     categoria_documento = "recibo"
    #
    # Turno 6:
    #     chega relatório clínico
    #
    # O relatório precisa passar novamente pelo Documento.
    #

    existe_anexo = (
        state.get("anexo_atual")
        or state.get("anexo_salvo")
    )

    if existe_anexo and not state.get("anexo_processado", False):
        return "ag_documento"

    # =========================================================
    # 3. Caso pronto para análise normativa
    # =========================================================

    return "ag_normas"


def criar_grafo_agente():
    workflow = StateGraph(AgentState)

    # =========================================================
    # NÓS
    # =========================================================

    workflow.add_node(
        "ag_triagem",
        ag_triagem
    )

    workflow.add_node(
        "ag_documento",
        ag_documento
    )

    workflow.add_node(
        "ag_normas",
        ag_normas
    )

    # =========================================================
    # ENTRADA
    # =========================================================

    workflow.set_entry_point("ag_triagem")

    # =========================================================
    # TRIAGEM → PRÓXIMO AGENTE
    # =========================================================

    workflow.add_conditional_edges(
        "ag_triagem",
        rotear_proximo_no,
        {
            "ag_documento": "ag_documento",
            "ag_normas": "ag_normas",
            END: END,
        },
    )

    # =========================================================
    # DOCUMENTO → NORMAS
    # =========================================================

    workflow.add_edge(
        "ag_documento",
        "ag_normas"
    )

    # =========================================================
    # NORMAS → FIM DO TURNO
    # =========================================================

    workflow.add_edge(
        "ag_normas",
        END
    )

    return workflow.compile()