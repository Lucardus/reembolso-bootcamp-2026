"""Supervisor e os três subagentes."""

from typing import TypedDict, Optional, List, Dict, Any

class AgentState(TypedDict):
    # Identificação da sessão
    session_id: str

    # Conversação
    mensagem_atual: str
    historico: List[Dict[str, Any]]

    # Anexos
    anexo_atual: Optional[Dict[str, Any]]
    anexo_salvo: Optional[Dict[str, Any]]

    # Dados do beneficiário
    carteirinha: Optional[str]
    dados_beneficiario: Optional[Dict[str, Any]]

    # Dados do documento
    categoria_documento: Optional[str]
    dados_documento: Optional[Dict[str, Any]]

    # Resultado da análise
    decisao: Optional[str]
    valor_solicitado_brl: Optional[float]
    valor_reembolso_brl: Optional[float]
    regras_aplicadas: List[str]

    # Controle do processo
    protocolo: Optional[str]
    pendencias: List[str]

    # Resposta final
    resposta_texto: str

