"""Servidor MCP mock da operadora SaúdeMais — cadastro, histórico e protocolo."""

from .dados import Beneficiario, Cadastro  # noqa: F401
from .server import Operadora, construir  # noqa: F401
