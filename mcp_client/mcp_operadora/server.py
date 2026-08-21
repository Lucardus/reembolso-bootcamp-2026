"""Servidor MCP da operadora — as três ferramentas do desafio.

    python -m mcp_operadora.server

Transporte streamable HTTP, o mesmo da avaliação oficial: o cliente que o
candidato escreve contra este servidor é o mesmo que roda na bateria.

Configuração, toda por ambiente:

    MCP_OPERADORA_DADOS      pasta `casos_treino/` ou arquivo JSON de cadastro
    MCP_OPERADORA_TOKEN      se definido, exigido no header Authorization
    MCP_OPERADORA_ESQUEMA    v1 (padrão) ou v2 — ver esquema.py
    MCP_OPERADORA_HOST       padrão 127.0.0.1
    MCP_OPERADORA_PORT       padrão 9000

O estado dos protocolos vive em memória e some quando o processo cai. É de
propósito: cada execução da avaliação começa limpa.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .dados import Cadastro
from .esquema import beneficiario as montar_beneficiario

PADRAO_DADOS = "./casos_treino"


def _config() -> dict[str, Any]:
    return {
        "dados": os.getenv("MCP_OPERADORA_DADOS", PADRAO_DADOS),
        "token": os.getenv("MCP_OPERADORA_TOKEN", ""),
        "esquema": os.getenv("MCP_OPERADORA_ESQUEMA", "v1").lower(),
        "host": os.getenv("MCP_OPERADORA_HOST", "127.0.0.1"),
        "port": int(os.getenv("MCP_OPERADORA_PORT", "9000")),
    }


class Operadora:
    """Estado do servidor: cadastro carregado e protocolos abertos na execução."""

    def __init__(self, cadastro: Cadastro, esquema: str):
        self.cadastro = cadastro
        self.esquema = "v2" if esquema == "v2" else "v1"
        self._protocolos: dict[str, dict] = {}
        self._sequencia = 0

    def novo_protocolo(self, carteirinha: str, payload: dict) -> dict:
        self._sequencia += 1
        numero = f"2026{self._sequencia:07d}"
        registro = {
            "protocolo": numero,
            "carteirinha": carteirinha,
            "aberto_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "EM_ANALISE",
            "payload": payload,
        }
        self._protocolos[numero] = registro
        return {k: v for k, v in registro.items() if k != "payload"}


def construir(cfg: dict[str, Any] | None = None) -> tuple[FastMCP, Operadora]:
    cfg = cfg or _config()
    cadastro = Cadastro.carregar(cfg["dados"])
    estado = Operadora(cadastro, cfg["esquema"])

    mcp = FastMCP(
        "operadora-saudemais",
        instructions=(
            "Cadastro de beneficiários da operadora. Use `consultar_beneficiario` para "
            "plano, adesão e sessões de terapia; `consultar_historico` para os pedidos "
            "anteriores; e `abrir_protocolo` quando o caso precisar de análise humana."
        ),
        host=cfg["host"],
        port=cfg["port"],
        stateless_http=True,
    )

    @mcp.tool()
    def consultar_beneficiario(carteirinha: str) -> dict:
        """Dados cadastrais do beneficiário: plano, adesão, sessões e situação.

        O CPF sai sempre mascarado — o cadastro nunca devolve o número inteiro.
        """
        b = estado.cadastro.buscar(carteirinha)
        if b is None:
            raise ValueError(f"beneficiário não localizado para a carteirinha {carteirinha}")
        return montar_beneficiario(b, estado.esquema)

    @mcp.tool()
    def consultar_historico(carteirinha: str) -> dict:
        """Últimos pedidos de reembolso do beneficiário, do mais antigo ao mais recente."""
        b = estado.cadastro.buscar(carteirinha)
        if b is None:
            raise ValueError(f"beneficiário não localizado para a carteirinha {carteirinha}")
        return {"carteirinha": b.carteirinha, "pedidos": b.historico}

    @mcp.tool()
    def abrir_protocolo(carteirinha: str, payload: dict) -> dict:
        """Abre protocolo para análise humana e devolve o número gerado.

        Use quando o caso não puder ser decidido de forma automatizada. O
        `payload` é livre: registre nele o que o analista precisa saber.
        """
        b = estado.cadastro.buscar(carteirinha)
        if b is None:
            raise ValueError(f"beneficiário não localizado para a carteirinha {carteirinha}")
        return estado.novo_protocolo(b.carteirinha, payload)

    if cfg["token"]:
        _exigir_token(mcp, cfg["token"])

    return mcp, estado


def _exigir_token(mcp: FastMCP, token: str) -> None:
    """Checagem simples de portador no header Authorization.

    Não é OAuth: é o suficiente para o candidato exercitar o envio do token que
    está no `.env`, que é o que a avaliação oficial vai cobrar.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    esperado = {f"Bearer {token}", token}

    class Portador(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path.rstrip("/").endswith("/saude"):
                return await call_next(request)
            if request.headers.get("authorization", "") not in esperado:
                return JSONResponse({"erro": "token ausente ou inválido"}, status_code=401)
            return await call_next(request)

    mcp.settings.__dict__.setdefault("_middleware", None)
    original = mcp.streamable_http_app

    def app_com_token():
        app = original()
        app.add_middleware(Portador)
        return app

    mcp.streamable_http_app = app_com_token  # type: ignore[method-assign]


def main() -> int:
    cfg = _config()
    try:
        mcp, estado = construir(cfg)
    except (FileNotFoundError, ValueError) as erro:
        print(f"erro ao carregar o cadastro: {erro}", file=sys.stderr)
        print(f"aponte MCP_OPERADORA_DADOS para uma pasta casos_treino/ ou um JSON.",
              file=sys.stderr)
        return 2

    origem = Path(cfg["dados"]).expanduser().resolve()
    print(f"cadastro: {len(estado.cadastro)} beneficiário(s) de {origem}")
    print(f"esquema:  {estado.esquema}")
    print(f"token:    {'exigido' if cfg['token'] else 'não exigido'}")
    print(f"ouvindo:  http://{cfg['host']}:{cfg['port']}/mcp")
    mcp.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
