from pathlib import Path
from llama_index.core import VectorStoreIndex, Document, Settings

from app.llm import criar_llm_llamaindex, criar_embeddings_llamaindex
from ingest import Chunk, processar_arquivo

RAIZ = Path(__file__).resolve().parents[1]
DIR_KB = RAIZ / "kb"
DIR_STORAGE = RAIZ / "storage"

def build_index(chunks: list[Chunk], persist_dir: Path) -> VectorStoreIndex:
    Settings.llm = criar_llm_llamaindex()
    Settings.embed_model = criar_embeddings_llamaindex()

    documents = [
        Document(
            text=c.texto,
            metadata={
                "documento_origem": c.documento_origem,
                "identificador": c.identificador,
                "tipo_documento": c.tipo_documento,
                "status": c.status,
                "revogado_por": c.revogado_por or "",
            },
        )
        for c in chunks
    ]

    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=str(persist_dir))
    return index

def main() -> int:
    if not DIR_KB.exists():
        print(f"[ERRO] Pasta {DIR_KB} não encontrada.")
        return 1

    arquivos = [f for f in DIR_KB.glob("*") if f.suffix.lower() in [".pdf", ".txt", ".docx", ".md"]]
    
    todos_os_chunks: list[Chunk] = []
    for arq in arquivos:
        print(f"Lendo: {arq.name}")
        todos_os_chunks.extend(processar_arquivo(arq))

    print(f"Criando embeddings para {len(todos_os_chunks)} chunks...")
    DIR_STORAGE.mkdir(parents=True, exist_ok=True)
    build_index(todos_os_chunks, DIR_STORAGE)
    
    print("Índice construído com sucesso em storage/!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())