"""Roda os 3 casos de treino contra o seu container. É o mesmo teste da correção.

    python rodar_treino.py                    # as três conversas
    python rodar_treino.py --caso 02          # só uma
    python rodar_treino.py -v                 # mostra cada turno
    python rodar_treino.py --roteiro-fixo     # sem o beneficiário simulado

Não é uma versão simplificada da avaliação: é o mesmo motor, em `avaliacao/`,
com os mesmos critérios, o mesmo beneficiário simulado e o mesmo juiz. O que
muda são as conversas — as da avaliação oficial são outras.

Por isso ele precisa de `BOOTCAMP_LLM_ENDPOINT` e `BOOTCAMP_API_KEY` no `.env`:
o beneficiário do outro lado é um modelo, e quem decide se cada turno foi
atendido também.

A nota de cada conversa vem 70% dos turnos atendidos e o restante do desfecho —
decisão, valor, protocolo e dispositivos do `esperado.json`. A nota final é a
média das conversas, cada uma valendo o mesmo.

Duas coisas zeram em vez de descontar: resposta repetida palavra por palavra
entre turnos (é tabela de templates, não atendimento) e violação de CPF, CID ou
dado de terceiro, no turno em que ocorre.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from avaliacao.avaliar import avaliar, nota_final  # noqa: E402
from avaliacao.conversar import ContainerNaoSubiu, conduzir, esperar_saude  # noqa: E402
from avaliacao.dispositivos import existentes  # noqa: E402
from avaliacao.llm import disponivel  # noqa: E402

VERDE, VERMELHO, CINZA, FIM = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def _carregar_env() -> None:
    """Lê o .env sem depender de biblioteca — só o que interessa ao teste."""
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


def main() -> int:
    _carregar_env()
    ap = argparse.ArgumentParser(description="Roda os casos de treino.")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--caso", help="prefixo da pasta, ex.: 02")
    ap.add_argument("--roteiro-fixo", action="store_true",
                    help="usar as mensagens literais em vez do beneficiário simulado")
    ap.add_argument("-v", "--verboso", action="store_true")
    args = ap.parse_args()

    if not disponivel():
        print(f"{VERMELHO}faltam BOOTCAMP_LLM_ENDPOINT e BOOTCAMP_API_KEY{FIM}")
        print("Este teste conversa com o seu agente e julga cada turno — as duas")
        print("pontas usam modelo. Preencha o .env e rode de novo.")
        return 2

    try:
        esperar_saude(args.url, segundos=20)
    except ContainerNaoSubiu:
        print(f"{VERMELHO}o container não respondeu em {args.url}/health{FIM}")
        print("suba o container antes de rodar este script.")
        return 2

    pastas = sorted(p for p in (RAIZ / "casos_treino").iterdir()
                    if p.is_dir() and (p / "esperado.json").exists())
    if args.caso:
        pastas = [p for p in pastas if p.name.startswith(args.caso)]
    if not pastas:
        print("nenhum caso encontrado.")
        return 2

    validos = existentes(RAIZ / "kb")
    vereditos = []

    for pasta in pastas:
        gabarito = json.loads((pasta / "esperado.json").read_text(encoding="utf-8"))
        print(f"\n{pasta.name}")
        if titulo := gabarito.get("_titulo"):
            print(f"  {CINZA}{titulo}{FIM}")

        try:
            transcricao = conduzir(pasta, args.url, sessao=f"treino-{pasta.name}",
                                   dinamico=not args.roteiro_fixo)
        except Exception as erro:  # noqa: BLE001 — falha vira relatório, não traceback
            print(f"  {VERMELHO}ERRO{FIM}  {type(erro).__name__}: {erro}")
            continue

        if args.verboso:
            for t in transcricao:
                anexo = "  [+anexo]" if t.get("anexo") else ""
                print(f"    {CINZA}turno {t['turno']}{anexo} · "
                      f"{(t['mensagem'] or '(só o anexo)')[:70]}{FIM}")
                print(f"    {CINZA}  -> {(t.get('resposta') or '')[:110]}{FIM}")

        v = avaliar(pasta.name, transcricao, gabarito, validos, usar_modelo=True)
        vereditos.append(v)
        cor = VERDE if v.nota >= 70 else VERMELHO
        if v.zerada:
            # Sem isto a banca vê "0/0 turnos" e não descobre que foi eco.
            print(f"  {VERMELHO}  0.0{FIM}  {v.motivo}")
        else:
            print(f"  {cor}{v.nota:5.1f}{FIM}  {v.atendidos}/{len(v.turnos)} turnos, "
                  f"desfecho {'ok' if not v.desfecho else 'divergente'}")
        for t in v.turnos_reprovados:
            print(f"    turno {t.turno}: {t.porque}")
            for viol in t.violacoes:
                print(f"      {VERMELHO}violação{FIM} {viol}")
        for d in v.desfecho:
            print(f"    desfecho: {d}")
        if dica := gabarito.get("_dica"):
            print(f"    {CINZA}{dica}{FIM}")

    nota = nota_final(vereditos)
    cor = VERDE if nota >= 70 else VERMELHO
    print(f"\n{cor}nota: {nota:.1f}{FIM}  (média das {len(vereditos)} conversas)")
    print(f"{CINZA}70% dos turnos atendidos e o restante do desfecho, por conversa. "
          f"Na avaliação a conta é a mesma — as conversas é que são outras{FIM}")
    return 0 if nota >= 70 else 1


if __name__ == "__main__":
    raise SystemExit(main())
