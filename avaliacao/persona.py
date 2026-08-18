"""O beneficiário simulado — quem conduz a conversa do outro lado.

Um roteiro fixo de mensagens não testa conversa: testa se o agente reconhece as
frases que já viu. Aqui o beneficiário é um modelo com um roteiro de **intenções**
— o que ele precisa dizer ou perguntar, em ordem — que ele verbaliza com as
palavras dele, reagindo ao que o agente acabou de responder.

O mesmo caso gera conversas diferentes a cada execução, com os mesmos fatos. O
gabarito não muda porque os fatos não mudam; o que muda é a redação, e é
exatamente isso que quebra quem casou regex com as frases do treino.

Sem endpoint de modelo configurado, cai para o roteiro literal — serve para
depurar, não para corrigir.
"""

from __future__ import annotations

from .llm import disponivel, perguntar_json

SISTEMA = """Você faz o papel de um beneficiário de plano de saúde falando com o
atendimento pelo chat. Você não trabalha com saúde, não conhece o vocabulário da
operadora e escreve como gente escreve em aplicativo: frases curtas, minúsculas,
sem formalidade, às vezes com um "ah" ou um "então".

Você recebe UMA intenção — o que precisa dizer ou perguntar agora — e o que já
foi conversado. Verbalize essa intenção com as suas palavras, reagindo ao que o
atendente acabou de dizer.

Regras:
- diga só o que a intenção manda; não invente fatos novos sobre o seu caso
- não use termos técnicos que um leigo não usaria (nada de "coparticipação",
  "TUSS", "alçada", "protocolo" — a não ser que o atendente tenha usado antes)
- uma ou duas frases, no máximo
- se a intenção for uma pergunta, pergunte de verdade
- não repita palavra por palavra o que você já disse antes

Responda só com JSON: {"mensagem": "..."}"""


def _historico(transcricao: list[dict], limite: int = 6) -> str:
    linhas = []
    for t in transcricao[-limite:]:
        if msg := (t.get("mensagem") or "").strip():
            linhas.append(f"você: {msg}")
        if resp := (t.get("resposta") or "").strip():
            linhas.append(f"atendente: {resp}")
    return "\n".join(linhas) or "(a conversa ainda não começou)"


def falar(intencao: str, transcricao: list[dict], persona: dict,
          literal: str | None = None) -> str:
    """Transforma uma intenção do roteiro na fala do beneficiário."""
    if not disponivel():
        return literal if literal is not None else intencao

    usuario = f"""Sobre você: {persona.get('nome', 'você')}, beneficiário do plano
{persona.get('plano', '')}. Carteirinha {persona.get('carteirinha', '')}.

Conversa até agora:
{_historico(transcricao)}

A sua intenção neste turno:
{intencao}

Escreva a sua mensagem."""
    try:
        return str(perguntar_json(SISTEMA, usuario).get("mensagem", "")).strip() or (
            literal or intencao)
    except Exception:  # noqa: BLE001 — persona é meio, não fim: cai para o literal
        return literal if literal is not None else intencao
