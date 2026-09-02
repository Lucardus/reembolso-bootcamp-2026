"""Cálculo — a apuração do valor a reembolsar.

Implementa, nesta ordem — que é a ordem do próprio Regulamento (arts. 43, 44,
45 e 47) — a apuração do valor:

  1. art. 43 — apura-se o menor valor entre o pago (documento fiscal) e o
     teto do procedimento (art. 33: quantidade de URS × valor da URS vigente
     na data do atendimento);
  2. art. 44 — sobre o valor apurado incide a coparticipação do
     beneficiário, sempre deduzida, nunca acrescida;
  3. art. 45 — o valor pós-coparticipação é limitado ao saldo do teto anual
     de 48 URS por beneficiário (48 URS − o que já foi reembolsado a ele no
     ano civil); esgotado o saldo, o pedido é indeferido; menor que o
     apurado, o pedido é deferido parcialmente pelo valor do saldo;
  4. art. 47 — o arredondamento (duas casas, meio para cima) é aplicado uma
     única vez, ao final de toda a apuração — nunca em etapas
     intermediárias.

O teto em URS, o valor da URS do exercício e o percentual de coparticipação
variam por plano, por procedimento e por circular normativa vigente na data
do atendimento — por isso são fornecidos pelo Agente de Normas, que os
extrai da KB para o caso concreto. Este módulo apenas aplica a fórmula, na
ordem correta, sobre os números que ele fornece.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def calcular_valor_reembolso(valor_recibo: float, teto_plano: float) -> float:
    """Art. 43 isolado: o menor valor entre o pago e o teto, com 2 casas decimais.

    Mantido por compatibilidade; para a apuração completa (com
    coparticipação e limite anual) use `apurar_reembolso`.
    """
    recibo = Decimal(str(valor_recibo))
    teto = Decimal(str(teto_plano))
    resultado = min(recibo, teto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(resultado)


def converter_urs_para_reais(qtd_urs: float, valor_urs: float) -> float:
    """Converte a quantidade de URS para Reais com arredondamento correto."""
    return float((Decimal(str(qtd_urs)) * Decimal(str(valor_urs))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def apurar_reembolso(
    valor_solicitado: Optional[float],
    teto_urs: Optional[float],
    valor_urs: Optional[float],
    percentual_coparticipacao: Optional[float],
    valor_reembolsado_no_ano: float = 0.0,
    limite_anual_urs: Optional[float] = 48.0,
    decisao_atual: str = "APROVADO",
) -> tuple[Optional[float], str, bool]:
    """Apuração completa do valor de reembolso, arts. 43, 44, 45 e 47.

    `decisao_atual` é a decisão que o agente de normas propôs (ex.:
    "APROVADO"); esta função só a ajusta quando o limite anual (art. 45)
    efetivamente reduz ou zera o valor apurado — a redução por teto (art. 43)
    ou por coparticipação (art. 44) é normal e NÃO torna a decisão parcial
    por si só.

    Devolve (valor_final, decisao_ajustada, foi_limitado_pelo_teto_anual).
    """
    if valor_solicitado is None:
        return None, decisao_atual, False

    # Art. 43 — menor valor entre o pago e o teto do procedimento.
    teto_rs = None
    if teto_urs is not None and valor_urs is not None:
        teto_rs = teto_urs * valor_urs
    valor_apurado = min(valor_solicitado, teto_rs) if teto_rs is not None else valor_solicitado

    # Art. 44 — coparticipação, sempre deduzida do valor apurado.
    percentual = percentual_coparticipacao or 0.0
    valor_pos_coparticipacao = valor_apurado * (1 - percentual)

    decisao = decisao_atual
    limitado_pelo_anual = False

    # Art. 45 — saldo do teto anual de 48 URS por beneficiário.
    if valor_urs is not None and limite_anual_urs is not None:
        limite_anual_rs = limite_anual_urs * valor_urs
        saldo = limite_anual_rs - (valor_reembolsado_no_ano or 0.0)
        if saldo <= 0:
            return 0.0, "NEGADO", True
        if valor_pos_coparticipacao > saldo:
            valor_pos_coparticipacao = saldo
            limitado_pelo_anual = True
            if decisao == "APROVADO":
                decisao = "APROVADO_PARCIAL"

    # Art. 47 — arredondamento único, ao final de toda a apuração.
    valor_final = Decimal(str(valor_pos_coparticipacao)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return float(valor_final), decisao, limitado_pelo_anual
