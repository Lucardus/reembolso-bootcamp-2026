"""Agente de reembolso — implementação do candidato."""

from app.agents import AgentState
from app.guardrails import aplicar_guardrails

def ag_reembolso(state: AgentState) -> AgentState:
    """
    Nó de finalização: Consolida pendências e formata a resposta final sem sobrescrever
    justificativas detalhadas já geradas pelo nó de normas.
    """
    if state.get("resposta_texto"):
        state["resposta_texto"] = aplicar_guardrails(state["resposta_texto"])
        return state

    pendencias = state.get("pendencias", [])
    if pendencias:
         state["resposta_texto"] = aplicar_guardrails(
            "Identifiquei alguns pontos que precisam de atenção para prosseguirmos com seu reembolso:\n\n" +
            "\n".join([f"- {p}" for p in pendencias])
        )
         return state

    decisao = state.get("decisao")
    valor = state.get("valor_reembolso_brl")

    if decisao in ["APROVADO", "APROVADO_PARCIAL"] and valor is not None:
        texto = (
            f"Seu pedido de reembolso foi {decisao.replace('_', ' ')}! "
            f"O valor a ser reembolsado é de R$ {valor:.2f}. "
            "O pagamento será processado conforme os prazos do plano."
        )
    elif decisao == "NEGADO":
        texto = "Infelizmente, seu pedido de reembolso não atende às normas vigentes do plano."
    elif decisao == "PENDENTE_DOCUMENTO":
        texto = "Por favor, envie o documento/recibo correspondente para podermos dar prosseguimento à análise."
    else:
        texto = "O seu pedido está sob análise humana. Entraremos em contato em breve."

    state["resposta_texto"] = aplicar_guardrails(texto)
    return state