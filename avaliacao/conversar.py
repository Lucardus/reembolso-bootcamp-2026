"""Conduz uma conversa contra o container do candidato e devolve a transcrição.

Turno a turno, com o mesmo `session_id`, anexo em base64. O que volta de cada
turno é guardado inteiro — texto e campos estruturados —, porque a nota da
conversa olha a transcrição toda, e não só o desfecho.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

TIMEOUT_TURNO = 180.0
TIMEOUT_HEALTH = 60.0


class ContainerNaoSubiu(RuntimeError):
    pass


def esperar_saude(url: str, segundos: float = TIMEOUT_HEALTH) -> None:
    """O enunciado dá 60 segundos do start até o /health responder 200."""
    import time
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            with httpx.Client(timeout=5.0) as c:
                if c.get(f"{url}/health").status_code == 200:
                    return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise ContainerNaoSubiu(f"{url}/health não respondeu 200 em {segundos:.0f}s")


def _anexo(pasta: Path, anexo: dict) -> dict:
    caminho = (pasta / anexo["path"]).resolve()
    if not caminho.exists():
        raise FileNotFoundError(f"anexo não encontrado: {caminho}")
    return {
        "filename": anexo["filename"],
        "mime_type": anexo["mime_type"],
        "base64": base64.b64encode(caminho.read_bytes()).decode("ascii"),
    }


def conduzir(pasta_caso: Path, url: str, sessao: str,
             dinamico: bool = True) -> list[dict]:
    """Devolve [{turno, mensagem, anexo, resposta, estruturado}].

    Com `dinamico`, quem fala do outro lado é o beneficiário simulado: o roteiro
    vira intenção e a frase é escrita na hora, reagindo ao que o agente
    respondeu. Sem ele, o roteiro é usado literalmente — bom para depurar, ruim
    para corrigir, porque um roteiro fixo testa reconhecimento de frase.
    """
    from .persona import falar

    linhas = (pasta_caso / "turnos.jsonl").read_text(encoding="utf-8").splitlines()
    turnos = [json.loads(l) for l in linhas if l.strip()]
    persona = json.loads((pasta_caso / "persona.json").read_text(encoding="utf-8"))
    transcricao: list[dict] = []

    with httpx.Client(timeout=TIMEOUT_TURNO) as cliente:
        cliente.post(f"{url}/reset", json={})
        for t in turnos:
            mensagem = t["mensagem"]
            if dinamico and mensagem.strip():
                mensagem = falar(t["mensagem"], transcricao, persona,
                                 literal=t["mensagem"])

            corpo: dict = {"session_id": sessao, "mensagem": mensagem}
            if "anexo" in t:
                corpo["anexo"] = _anexo(pasta_caso, t["anexo"])

            registro = {"turno": t["turno"], "mensagem": mensagem,
                        "roteiro": t["mensagem"],
                        "anexo": t.get("anexo", {}).get("filename")}
            try:
                r = cliente.post(f"{url}/chat", json=corpo)
                r.raise_for_status()
                devolvido = r.json()
            except Exception as erro:  # noqa: BLE001 — falha de turno vira registro
                registro |= {"resposta": "", "estruturado": {},
                             "erro": f"{type(erro).__name__}: {erro}"}
                transcricao.append(registro)
                continue

            registro |= {
                "resposta": devolvido.get("resposta", ""),
                "estruturado": {k: v for k, v in devolvido.items() if k != "resposta"},
            }
            transcricao.append(registro)
    return transcricao
