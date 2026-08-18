"""Supervisor — máquina de estados, roteamento e handoff.

Aqui vive o grafo. Sugestão de estado: session_id, carteirinha, plano, data de
adesão, categoria do documento, valores extraídos, decisão, pendências.

Exigências:
  * orquestração com framework de agente — `if/elif` puro zera o bloco;
  * checkpointer por `session_id`;
  * a conversa não chega em ordem. O beneficiário pode mandar o anexo no
    primeiro turno, corrigir uma data depois ou perguntar outra coisa no meio.
"""
