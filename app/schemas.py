"""Contrato do POST /chat. Este arquivo já vem pronto — não altere os nomes."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class Categoria(str, Enum):
    """As 7 classes em que todo documento é classificado."""

    CONSULTA_MEDICA = "CONSULTA_MEDICA"
    SESSAO_TERAPIA = "SESSAO_TERAPIA"
    EXAME_DIAGNOSTICO = "EXAME_DIAGNOSTICO"
    RELATORIO_CLINICO = "RELATORIO_CLINICO"
    MATERIAL_OPME = "MATERIAL_OPME"
    DESPESA_NAO_COBERTA = "DESPESA_NAO_COBERTA"
    INVALIDO = "INVALIDO"


class Decisao(str, Enum):
    APROVADO = "APROVADO"
    APROVADO_PARCIAL = "APROVADO_PARCIAL"
    PENDENTE_DOCUMENTO = "PENDENTE_DOCUMENTO"
    NEGADO = "NEGADO"
    FORA_DE_ESCOPO = "FORA_DE_ESCOPO"
    ESCALADO_ANALISTA = "ESCALADO_ANALISTA"


class Anexo(BaseModel):
    filename: str
    mime_type: str
    base64: str


class ChatRequest(BaseModel):
    session_id: str
    mensagem: str
    anexo: Anexo | None = None


class ChatResponse(BaseModel):
    """Campos de decisão ficam `null` enquanto a conversa não chegou lá."""

    resposta: str
    categoria_documento: Categoria | None = None
    decisao: Decisao | None = None
    valor_solicitado_brl: Decimal | None = None
    valor_reembolso_brl: Decimal | None = None
    regras_aplicadas: list[str] = Field(default_factory=list)
    protocolo: str | None = None
    pendencias: list[str] = Field(default_factory=list)
