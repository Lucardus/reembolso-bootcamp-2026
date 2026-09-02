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
    valor_reembolsado_ano: Optional[float]

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
    _rejeitou_terceiro: bool  # Flag para rastrear se já mencionou dados de terceiro
    _confirmado_carteirinha: bool  # Flag para confirmar carteirinha apenas uma vez
    _contador_respostas_apos_terceiro: int  # Incrementa a cada resposta após rejeitar terceiro
    _contador_documentos_rejeitados: int  # Conta documentos rejeitados para variar resposta
    anexo_processado: bool  # Flag indicando se anexo foi processado
    _normas_respondeu_categoria: Optional[str]  # Rastreia qual categoria normas respondeu - evita ECO
    _contador_normas_respondeu: int  # Conta vezes que normas respondeu - varia mensagem para evitar ECO
    _caso_decidido: bool  # Decisao e valor ja apurados (art. 43-47) e travados - nao recalcula mais
    _relatorio_clinico_recebido: bool  # Um documento RELATORIO_CLINICO ja chegou nesta sessao (art. 73, §3)

    # Resposta final
    resposta_texto: str
    _turno_finalizado: bool  # ag_triagem ja deu a resposta deste turno; supervisor nao deve chamar ag_normas de novo

