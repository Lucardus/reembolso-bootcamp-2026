"""Cálculo — a apuração do valor a reembolsar.

Tudo o que este módulo precisa fazer está escrito, em português, na `kb/`.
Nenhuma fórmula é entregue aqui de propósito: reconstruí-la lendo o regulamento
é a prova.

O que você vai precisar responder:
  * qual é o teto do procedimento e de onde ele vem;
  * o que se compara com o quê, e em que ordem;
  * o que diferencia um plano do outro;
  * como se arredonda.
"""

from decimal import Decimal, ROUND_HALF_UP

def calcular_valor_reembolso(valor_recibo: float, teto_plano: float) -> float:
    """Calcula o menor valor entre recibo e teto garantindo precisão de 2 casas decimais."""
    recibo = Decimal(str(valor_recibo))
    teto = Decimal(str(teto_plano))
    resultado = min(recibo, teto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(resultado)

def converter_urs_para_reais(qtd_urs: float, valor_urs: float) -> float:
    """Converte a quantidade de URS para Reais com arredondamento correto."""
    return float((Decimal(str(qtd_urs)) * Decimal(str(valor_urs))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
