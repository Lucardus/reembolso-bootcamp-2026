"""Triagem — intenção, carteirinha e elegibilidade.

Extrai o que o beneficiário quer e o número da carteirinha de uma mensagem em
linguagem corrente, consulta o MCP e aplica o guardrail de terceiros.
"""
import re
from app.agents import AgentState
from app.tools import consultar_beneficiario
from app.llm import criar_llm

llm = criar_llm()

def ag_triagem(state: AgentState) -> AgentState:
    msg = state.get("mensagem_atual", "")
    
    # Persiste o anexo no estado global para não perder caso venha no turno 1
    if state.get("anexo_atual"):
        state["anexo_salvo"] = state["anexo_atual"]
    
    # Extração de carteirinha do titular
    if not state.get("carteirinha"):
        match = re.search(r'\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{2,4}\b', msg)
        if match:
            carteirinha_limpa = re.sub(r'\D', '', match.group(0))
            if len(carteirinha_limpa) >= 10:
                state["carteirinha"] = carteirinha_limpa

    # Guardrail de Terceiros: se já tem carteirinha do titular e o usuário enviou outra
    if state.get("carteirinha"):
        outras_carteirinhas = re.findall(r'\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{2,4}\b', msg)
        for c in outras_carteirinhas:
            c_limpa = re.sub(r'\D', '', c)
            if c_limpa != state["carteirinha"] and len(c_limpa) >= 10:
                # Recusa o atendimento de terceiros de forma fluida sem interromper a sessão
                state["resposta_texto"] = (
                    "Consigo consultar dados apenas do titular desta sessão. "
                    "Seguiremos com a análise da sua solicitação."
                )
                return state

    # Consulta ao MCP
    if state.get("carteirinha") and not state.get("dados_beneficiario"):
        dados = consultar_beneficiario(state["carteirinha"])
        if isinstance(dados, dict) and not dados.get("erro") and not dados.get("isError"):
            state["dados_beneficiario"] = dados
        else:
            state["pendencias"] = state.get("pendencias", []) + ["Beneficiário não localizado no sistema."]

    # Se ainda falta a carteirinha, gera a solicitação via LLM (evita eco/template zerado)
    if not state.get("carteirinha"):
        prompt = f"""O beneficiário disse: "{msg}".
        Gere uma resposta amigável e natural pedindo o número da carteirinha do plano de saúde.
        NÃO use frases padrão pré-prontas. Altere a forma de falar."""
        resposta_llm = llm.invoke(prompt)
        state["resposta_texto"] = resposta_llm.content if hasattr(resposta_llm, "content") else str(resposta_llm)

    return state