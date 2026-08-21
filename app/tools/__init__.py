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
import asyncio
import json
import os
from typing import Any, Dict
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = os.getenv("MCP_OPERADORA_URL", "http://127.0.0.1:9000/mcp")
MCP_TOKEN = os.getenv("MCP_OPERADORA_TOKEN", "")

async def _executar_ferramenta_mcp(nome: str, args: Dict[str, Any]) -> Dict[str, Any]:
    headers = {}
    if MCP_TOKEN:
        headers["Authorization"] = f"Bearer {MCP_TOKEN}"

    try:
        async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool(nome, args)

                if getattr(res, "isError", False):
                    erro_msg = res.content[0].text if res.content else "Erro MCP"
                    return {"erro": erro_msg, "isError": True}

                if res.content and hasattr(res.content[0], "text"):
                    texto = res.content[0].text
                    try:
                        return json.loads(texto)
                    except json.JSONDecodeError:
                        return {"resultado": texto}
                return {}
    except Exception as e:
        return {"erro": f"Falha HTTP/MCP: {str(e)}", "isError": True}

def chamar_mcp(nome: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return asyncio.run(_executar_ferramenta_mcp(nome, args))

def consultar_beneficiario(carteirinha: str) -> Dict[str, Any]:
    dados = chamar_mcp("consultar_beneficiario", {"carteirinha": carteirinha})
    if dados.get("erro"):
        return dados

    sessoes_ano = 0
    if "sessoes_terapia_ano" in dados:
        sessoes_ano = dados.get("sessoes_terapia_ano", 0)
    elif "sessoes_terapia" in dados and isinstance(dados["sessoes_terapia"], dict):
        sessoes_ano = dados["sessoes_terapia"].get("ano_corrente", 0)

    return {
        "carteirinha": dados.get("carteirinha"),
        "nome": dados.get("nome"),
        "plano": dados.get("plano"),
        "data_adesao": dados.get("data_adesao"),
        "status": dados.get("status"),
        "sessoes_terapia_ano": sessoes_ano,
    }

def consultar_historico(carteirinha: str) -> Dict[str, Any]:
    dados = chamar_mcp("consultar_historico", {"carteirinha": carteirinha})
    if dados.get("erro"):
        return dados
    return {"carteirinha": dados.get("carteirinha"), "pedidos": dados.get("pedidos", [])}

def abrir_protocolo(carteirinha: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return chamar_mcp("abrir_protocolo", {"carteirinha": carteirinha, "payload": payload})