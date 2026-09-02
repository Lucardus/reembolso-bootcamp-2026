from langgraph.graph import StateGraph, END

from app.agents import AgentState
from app.agents.triagem import ag_triagem
from app.agents.documento import ag_documento
from app.agents.normas import ag_normas


def rotear_proximo_no(state: AgentState) -> str:
    """
    Decide qual agente deve processar o estado atual.
    """

    if not state.get("carteirinha"):
        return END  

    # ag_triagem ja respondeu completamente este turno (ex.: recusa de
    # dados de terceiro, confirmacao de carteirinha, resposta a pergunta
    # especifica) - nao chame ag_normas, que sobrescreveria essa resposta
    # certa com a decisao generica do caso (causa de ECO em turnos onde o
    # assunto do turno nao e mais a decisao principal).
    if state.get("_turno_finalizado"):
        return END

    existe_anexo = (
        state.get("anexo_atual")
    )

    if existe_anexo and not state.get("anexo_processado", False):
        return "ag_documento"

    return "ag_normas"


def criar_grafo_agente():
    workflow = StateGraph(AgentState)

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

    workflow.set_entry_point("ag_triagem")

    workflow.add_conditional_edges(
        "ag_triagem",
        rotear_proximo_no,
        {
            "ag_documento": "ag_documento",
            "ag_normas": "ag_normas",
            END: END,
        },
    )

    workflow.add_edge(
        "ag_documento",
        "ag_normas"
    )

    workflow.add_edge(
        "ag_normas",
        END
    )

    return workflow.compile()
