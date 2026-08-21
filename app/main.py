"""API do agente. As 3 rotas são obrigatórias; o miolo é seu.

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations
import traceback
from decimal import Decimal
from fastapi import FastAPI
from app.llm import carregar_env
from app.schemas import ChatRequest, ChatResponse, Decisao, Categoria
from app.agents.supervisor import criar_grafo_agente
from app.guardrails import aplicar_guardrails

carregar_env()

app = FastAPI(title="Agente de Reembolso")

SESSÕES_EM_MEMORIA = {}
grafo_agente = criar_grafo_agente()

def _converter_decisao(decisao_str: str | None) -> Decisao | None:
    if not decisao_str:
        return None
    try:
        return Decisao(decisao_str)
    except ValueError:
        if "DOCUMENTO" in decisao_str or "PENDENTE" in decisao_str:
            return Decisao.PENDENTE_DOCUMENTO
        elif "ANALISE" in decisao_str or "ESCALADO" in decisao_str:
            return Decisao.ESCALADO_ANALISTA
        return None

def _converter_categoria(cat_str: str | None) -> Categoria | None:
    if not cat_str:
        return None
    try:
        return Categoria(cat_str)
    except ValueError:
        return None

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    session_id = req.session_id

    if session_id not in SESSÕES_EM_MEMORIA:
        SESSÕES_EM_MEMORIA[session_id] = {
            "session_id": session_id,
            "mensagem_atual": "",
            "anexo_atual": None,
            "anexo_salvo": None,
            "carteirinha": None,
            "dados_beneficiario": None,
            "categoria_documento": None,
            "dados_documento": None,
            "decisao": None,
            "valor_solicitado_brl": None,
            "valor_reembolso_brl": None,
            "regras_aplicadas": [],
            "protocolo": None,
            "pendencias": [],
            "resposta_texto": "",
        }

    estado_atual = SESSÕES_EM_MEMORIA[session_id]
    estado_atual["anexo_atual"] = None
    estado_atual["mensagem_atual"] = req.mensagem or ""

    if req.anexo:
        anexo_dict = req.anexo.model_dump() if hasattr(req.anexo, "model_dump") else req.anexo.dict()
        estado_atual["anexo_atual"] = anexo_dict
        estado_atual["anexo_salvo"] = anexo_dict

    try:
        novo_estado = grafo_agente.invoke(estado_atual)
        SESSÕES_EM_MEMORIA[session_id] = novo_estado

        texto_resposta = (
            novo_estado.get("resposta_texto")
            or "Recebido. Como posso ajudar com seu pedido de reembolso?"
        )

        v_sol = novo_estado.get("valor_solicitado_brl")
        v_rec = novo_estado.get("valor_reembolso_brl")

        return ChatResponse(
            resposta=aplicar_guardrails(texto_resposta),
            categoria_documento=_converter_categoria(novo_estado.get("categoria_documento")),
            decisao=_converter_decisao(novo_estado.get("decisao")),
            valor_solicitado_brl=Decimal(str(v_sol)) if v_sol is not None else None,
            valor_reembolso_brl=Decimal(str(v_rec)) if v_rec is not None else None,
            regras_aplicadas=novo_estado.get("regras_aplicadas") or [],
            protocolo=novo_estado.get("protocolo"),
            pendencias=novo_estado.get("pendencias") or [],
        )
    
    except Exception as e:
        print(f"[ERRO NO TURNO {session_id}]: {e}")
        traceback.print_exc()

        numero_turno = len(estado_atual.get("historico", [])) + 1
        tem_carteirinha = bool(estado_atual.get("carteirinha"))

    if tem_carteirinha:
        texto_fallback = (
            f"Peço desculpas, tive uma instabilidade momentânea ao processar sua "
            f"solicitação (mensagem {numero_turno}). Pode repetir ou complementar "
            f"o que você disse?"
        )
    else:
        texto_fallback = (
            "Desculpe, tive um problema técnico agora. Para seguirmos, "
            "pode me informar novamente o número da sua carteirinha?"
        )

    return ChatResponse(
        resposta=texto_fallback,
        categoria_documento=None,
        decisao=None,
        valor_solicitado_brl=None,
        valor_reembolso_brl=None,
        regras_aplicadas=[],
        protocolo=None,
        pendencias=[],
    )

@app.post("/reset")
def reset_endpoint(payload: dict):
    session_id = payload.get("session_id")
    if session_id in SESSÕES_EM_MEMORIA:
        SESSÕES_EM_MEMORIA.pop(session_id, None)
    return {"status": "ok", "message": f"Sessão {session_id} resetada."}
