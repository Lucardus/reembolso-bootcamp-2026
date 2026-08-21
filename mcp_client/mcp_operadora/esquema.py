"""As duas formas possíveis do retorno de `consultar_beneficiario`.

A escolha é da banca, por `MCP_OPERADORA_ESQUEMA`, e vale para todos os
candidatos daquela rodada — o padrão é v1.

    v1   sessoes_terapia_ano: 4                       campo escalar
    v2   sessoes_terapia: {ano_corrente, acumulado}   objeto

A v2 existe porque o acumulado histórico é informação que uma operadora de
verdade tem e o ano corrente sozinho não expressa. Se a banca quiser exercitar
cliente tolerante a formato, é só rodar as duas rodadas com esquemas
diferentes; não há mudança no meio de uma execução.
"""

from __future__ import annotations

from typing import Literal

from .dados import Beneficiario

Versao = Literal["v1", "v2"]


def sessoes(b: Beneficiario, versao: Versao) -> dict:
    if versao == "v1":
        return {"sessoes_terapia_ano": b.sessoes_terapia_ano}
    return {
        "sessoes_terapia": {
            "ano_corrente": b.sessoes_terapia_ano,
            "acumulado": b.acumulado_terapia,
        }
    }


def beneficiario(b: Beneficiario, versao: Versao) -> dict:
    return {**b.publico(), **sessoes(b, versao)}
