"""Recuperação — carga do índice e busca híbrida.

Carrega o que `ingest/build.py` gravou em `storage/` e monta a busca: BM25 e
denso, com fusão e reranker.

Atenção ao persistir: o índice vetorial não é a única coisa que precisa
sobreviver ao build. Se o BM25 for reconstruído a partir de nós em memória,
dentro do container ele não existe — e a busca deixa de ser híbrida sem
levantar erro nenhum.
"""
from pathlib import Path
from llama_index.core import StorageContext, load_index_from_storage, Settings
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.retrievers import QueryFusionRetriever
from app.llm import criar_llm_llamaindex, criar_embeddings_llamaindex

DIR_STORAGE = Path("/srv/storage")

class MotorRAG:
    def __init__(self):
        Settings.llm = criar_llm_llamaindex()
        Settings.embed_model = criar_embeddings_llamaindex()

        if not DIR_STORAGE.exists():
            raise FileNotFoundError(
                f"Storage não encontrado em: {DIR_STORAGE}"
            )

        storage_context = StorageContext.from_defaults(
            persist_dir=str(DIR_STORAGE)
        )

        self.index = load_index_from_storage(storage_context)

        retriever_vetorial = self.index.as_retriever(
            similarity_top_k=5
        )

        nos_salvos = list(storage_context.docstore.docs.values())

        retriever_bm25 = BM25Retriever.from_defaults(
            nodes=nos_salvos,
            similarity_top_k=5
        )

        self.retriever = QueryFusionRetriever(
            [retriever_vetorial, retriever_bm25],
            similarity_top_k=5,
            num_queries=1,
            mode="reciprocal_rerank"
        )

        print(
            f"[RAG] Índice carregado com sucesso. "
            f"Nós disponíveis: {len(nos_salvos)}"
        )

    def buscar_regras(self, consulta: str) -> str:
        nos_recuperados = self.retriever.retrieve(consulta)

        contextos = []

        for no in nos_recuperados:
            meta = no.node.metadata

            trecho = (
                f"[REF: {meta.get('identificador', 'N/A')} | "
                f"DOC: {meta.get('documento_origem', 'N/A')} | "
                f"STATUS: {meta.get('status', 'vigente')}]\n"
                f"{no.node.text}\n"
            )

            contextos.append(trecho)

        return "\n-------------------\n".join(contextos)