"""Constrói o índice a partir de kb/ e grava em storage/.

    python -m ingest.build

Roda FORA do container, na sua máquina. Depois você commita `storage/` e o
Dockerfile só copia — o build da imagem precisa ser offline e determinístico, e
o `/health` tem 60 segundos para responder.

Você vai rodar isto de novo quando a base de conhecimento mudar. Deixe rápido.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIR_KB = RAIZ / "kb"
DIR_STORAGE = RAIZ / "storage"


def main() -> int:
    raise NotImplementedError(
        "implemente: carregar kb/, chunkar, embedar e persistir em storage/"
    )


if __name__ == "__main__":
    raise SystemExit(main())
