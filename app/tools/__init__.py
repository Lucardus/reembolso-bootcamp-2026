"""Ferramentas — cliente do servidor MCP.

Três ferramentas, por HTTP streamable, em `MCP_OPERADORA_URL`:

    consultar_beneficiario(carteirinha)   plano, adesão, sessões, situação
    consultar_historico(carteirinha)      pedidos de reembolso anteriores
    abrir_protocolo(carteirinha, payload) número de protocolo

O token de `MCP_OPERADORA_TOKEN` vai no header `Authorization`; sem ele o
servidor responde 401.

Dois detalhes que costumam derrubar cliente:

  * erro de ferramenta no MCP volta como `isError` no resultado, e **não** como
    exceção de transporte. Quem não olha esse campo trata "beneficiário não
    localizado" como se fosse resposta válida;
  * o formato do retorno pode mudar durante a prova. Escreva de forma que um
    campo com outra forma não derrube o fluxo inteiro.
"""
