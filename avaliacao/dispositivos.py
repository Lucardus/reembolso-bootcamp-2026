"""O que pode ser legitimamente citado em `regras_aplicadas`.

Sai da própria `kb/` — nada de lista fixa. Assim o mesmo código serve à banca e
ao candidato, cada um apontando para a base que tem em mãos.
"""

from __future__ import annotations

import re
from pathlib import Path

PADROES = (
    (re.compile(r"\bArt\. (\d+)"), "ART-{}"),
    (re.compile(r"\bCIRCULAR NORMATIVA (\d+)/(\d+)"), "CIRC-{}-{}"),
    (re.compile(r"\b(\d{8})\b"), "TUSS-{}"),
)


def _texto(caminho: Path) -> str:
    if caminho.suffix == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(str(caminho)).paragraphs)
    import fitz
    return "".join(p.get_text() for p in fitz.open(str(caminho)))


def existentes(dir_kb: Path) -> set[str]:
    """Todo dispositivo que aparece na base, no formato de citação do art. 6º."""
    achados = {"ANEXO-IV", "NT-02"}
    for arquivo in sorted(Path(dir_kb).glob("*")):
        if arquivo.suffix not in (".pdf", ".docx"):
            continue
        try:
            texto = _texto(arquivo)
        except Exception:  # noqa: BLE001 — arquivo ilegível não invalida os outros
            continue
        for padrao, molde in PADROES:
            for m in padrao.finditer(texto):
                achados.add(molde.format(*m.groups()))
    return achados
