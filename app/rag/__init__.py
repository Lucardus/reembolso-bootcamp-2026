"""Recuperação — carga do índice e busca híbrida.

Carrega o que `ingest/build.py` gravou em `storage/` e monta a busca: BM25 e
denso, com fusão e reranker.

Atenção ao persistir: o índice vetorial não é a única coisa que precisa
sobreviver ao build. Se o BM25 for reconstruído a partir de nós em memória,
dentro do container ele não existe — e a busca deixa de ser híbrida sem
levantar erro nenhum.
"""
