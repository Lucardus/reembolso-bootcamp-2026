"""Onde a chave entra e como falar com o modelo. Já pronto — use e siga.

O modelo da prova é o **Gemini 2.5 Flash Lite**, servido por um gateway da
banca. Você não configura provedor, não escolhe modelo e não passa chave de
nuvem nenhuma: as duas linhas do seu `.env` bastam.

    BOOTCAMP_LLM_ENDPOINT=https://...        # a URL que você recebeu
    BOOTCAMP_API_KEY=bc26_...                # a sua chave, individual

Este arquivo é encanamento, não é a prova. Está pronto de propósito: ninguém é
avaliado por acertar `base_url`. O que se avalia é o agente que você constrói em
cima disto.

    from app.llm import criar_llm, criar_embeddings

    llm = criar_llm()                        # LangChain / LangGraph
    emb = criar_embeddings()

    from app.llm import criar_llm_llamaindex, criar_embeddings_llamaindex

    Settings.llm = criar_llm_llamaindex()    # LlamaIndex
    Settings.embed_model = criar_embeddings_llamaindex()

A sua chave tem crédito de 1 milhão de tokens de entrada e 1 milhão de saída.
`GET {endpoint}/saldo`, com a mesma chave, mostra quanto sobrou. Esgotou, as
chamadas passam a devolver 429 — e não há recarga. Reenviar a base de
conhecimento inteira a cada turno queima o crédito antes do fim da prova.
"""

from __future__ import annotations
import os
import re
from pathlib import Path

MODELO = "gemini-2.5-flash-lite"
MODELO_EMBEDDING = "gemini-embedding-2"
DIMENSOES = 1536

RAIZ = Path(__file__).resolve().parents[1]

class FaltaConfiguracao(RuntimeError):
    pass

def carregar_env() -> None:
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))

def _ambiente() -> tuple[str, str]:
    carregar_env()
    endpoint = os.getenv("BOOTCAMP_LLM_ENDPOINT", "").strip().rstrip("/")
    chave = os.getenv("BOOTCAMP_API_KEY", "").strip()
    if not endpoint or not chave:
        raise FaltaConfiguracao("preencha BOOTCAMP_LLM_ENDPOINT e BOOTCAMP_API_KEY no .env")
    return re.sub(r"/v1(beta)?$", "", endpoint), chave

def criar_llm(**extra):
    from langchain_google_genai import ChatGoogleGenerativeAI
    endpoint, chave = _ambiente()
    return ChatGoogleGenerativeAI(
        model=MODELO, google_api_key=chave, base_url=endpoint,
        temperature=extra.pop("temperature", 0), **extra)

def criar_embeddings(**extra):
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    endpoint, chave = _ambiente()
    return GoogleGenerativeAIEmbeddings(
        model=f"models/{MODELO_EMBEDDING}", google_api_key=chave,
        base_url=endpoint, **extra)

def criar_llm_llamaindex(**extra):
    from llama_index.llms.google_genai import GoogleGenAI
    endpoint, chave = _ambiente()
    return GoogleGenAI(model=MODELO, api_key=chave,
                       http_options={"base_url": endpoint}, **extra)

def criar_embeddings_llamaindex(**extra):
    from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
    endpoint, chave = _ambiente()
    return GoogleGenAIEmbedding(model_name=MODELO_EMBEDDING, api_key=chave,
                                http_options={"base_url": endpoint}, **extra)

def saldo() -> dict:
    import httpx
    endpoint, chave = _ambiente()
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{endpoint}/saldo", headers={"Authorization": f"Bearer {chave}"})
        r.raise_for_status()
        return r.json()
