"""API do agente. As 3 rotas são obrigatórias; o miolo é seu.

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI

from app.llm import carregar_env
from app.schemas import ChatRequest, ChatResponse

# Lê o `.env` no start. O que já vem do ambiente vence — é assim que a banca
# injeta as credenciais dela no `docker run`.
carregar_env()

app = FastAPI(title="Agente de Reembolso")


@app.get("/health")
def health() -> dict:
    """Precisa responder 200 em até 60 segundos do start do container.

    Não construa índice aqui: o `storage/` já vem pronto na imagem.
    """
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Um turno de conversa.

    O avaliador NÃO reenvia o histórico: recupere o estado da conversa pelo
    `session_id`, com o checkpointer do seu grafo.
    """
    raise NotImplementedError("implemente o supervisor em app/agents/supervisor/")


@app.post("/reset")
def reset() -> dict:
    """Limpa estado e sessões. Chamado entre conversas."""
    raise NotImplementedError("implemente a limpeza de estado")
