"""Construção do índice."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import docx
import fitz  # PyMuPDF


@dataclass
class Chunk:
    texto: str
    documento_origem: str  # ex: "regulamento.pdf"
    identificador: str  # ex: "ART-35"
    tipo_documento: str  # ex: "regulamento", "circular"
    data_vigencia: Optional[str] = None
    revogado_por: Optional[str] = None
    status: str = "vigente"  # "vigente" | "revogado"


def parse_pdf(path: str) -> str:
    doc = fitz.open(path)
    paginas = []
    for page in doc:
        txt = page.get_text()
        if txt.strip():
            paginas.append(txt)
    return "\n".join(paginas)


def parse_docx(path: str) -> str:
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_document(path: str) -> str:
    path_str = str(path)
    if path_str.endswith(".pdf"):
        return parse_pdf(path_str)
    elif path_str.endswith(".docx"):
        return parse_docx(path_str)
    elif path_str.endswith((".txt", ".md")):
        return Path(path).read_text(encoding="utf-8")
    raise ValueError(f"Formato não suportado: {path}")


def processar_arquivo(caminho: Path) -> List[Chunk]:
    """Lê um arquivo usando o parser e realiza a divisão em Chunks enriquecidos."""
    nome_arquivo = caminho.name
    texto = parse_document(str(caminho))

    tipo_doc = "circular" if "circular" in nome_arquivo.lower() else "regulamento"

    # Regex ampliado para capturar divisões por Artigo, Seção, Capítulo, Cláusula e Anexo
    padrao = r"(Art(?:igo|\.)?\s*\d+[-–—\w]*|Seção\s+[IVXLCDM\d]+|Capítulo\s+[IVXLCDM\d]+|Cláusula\s+\d+|Anexo\s+[\w\d]+)"
    partes = re.split(padrao, texto, flags=re.IGNORECASE)

    chunks: List[Chunk] = []

    if len(partes) > 1:
        if partes[0].strip():
            chunks.append(
                Chunk(
                    texto=partes[0].strip(),
                    documento_origem=nome_arquivo,
                    identificador="PREAMBULO",
                    tipo_documento=tipo_doc,
                )
            )

        for i in range(1, len(partes), 2):
            header = partes[i].strip()
            corpo = partes[i + 1].strip() if i + 1 < len(partes) else ""

            num_match = re.search(r"\d+", header)
            if "art" in header.lower():
                identificador = f"ART-{num_match.group()}" if num_match else header.upper().replace(" ", "-")
            else:
                identificador = header.upper().replace(" ", "-")

            status = "revogado" if "revogado" in corpo[:120].lower() else "vigente"

            chunks.append(
                Chunk(
                    texto=f"{header}\n{corpo}",
                    documento_origem=nome_arquivo,
                    identificador=identificador,
                    tipo_documento=tipo_doc,
                    status=status,
                )
            )
    else:
        # Fallback para documentos sem marcação formal: divide em blocos menores para não gerar chunks gigantes incompatíveis com o BM25
        paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
        if not paragrafos:
            paragrafos = [texto.strip()]

        bloco_atual = []
        tam_atual = 0
        idx_chunk = 1

        for p in paragrafos:
            bloco_atual.append(p)
            tam_atual += len(p)
            if tam_atual >= 800:
                texto_chunk = "\n\n".join(bloco_atual)
                chunks.append(
                    Chunk(
                        texto=texto_chunk,
                        documento_origem=nome_arquivo,
                        identificador=f"BLOCO-{idx_chunk}",
                        tipo_documento=tipo_doc,
                        status="revogado" if "revogado" in texto_chunk[:120].lower() else "vigente",
                    )
                )
                bloco_atual = []
                tam_atual = 0
                idx_chunk += 1

        if bloco_atual:
            texto_chunk = "\n\n".join(bloco_atual)
            chunks.append(
                Chunk(
                    texto=texto_chunk,
                    documento_origem=nome_arquivo,
                    identificador=f"BLOCO-{idx_chunk}" if idx_chunk > 1 else "GERAL",
                    tipo_documento=tipo_doc,
                    status="revogado" if "revogado" in texto_chunk[:120].lower() else "vigente",
                )
            )

    return chunks
