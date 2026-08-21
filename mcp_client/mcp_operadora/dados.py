"""Carga do cadastro de beneficiários e montagem do histórico.

A fonte pode ser:

  * uma pasta `casos_treino/` — cada `*/persona.json` vira um beneficiário. É o
    modo do candidato: ele aponta para a própria pasta e o servidor fica em dia
    com os casos que ele recebeu, sem duplicar arquivo nenhum;
  * um arquivo JSON com uma lista de beneficiários. É o modo da banca na
    avaliação oficial, com as personas que não podem estar no ZIP.

O histórico de pedidos, quando não vem no arquivo, é derivado do próprio
cadastro: um beneficiário com 4 sessões de terapia no ano tem 3 pedidos
anteriores de terapia, para que a conta feche com o que o cadastro informa.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


def _mascarar_cpf(cpf: str) -> str:
    """`528.417.930-11` -> `***.417.930-**`. O CPF inteiro nunca sai daqui."""
    digitos = [c for c in cpf if c.isdigit()]
    if len(digitos) != 11:
        return "***"
    meio = "".join(digitos[3:9])
    return f"***.{meio[:3]}.{meio[3:]}-**"


@dataclass
class Beneficiario:
    carteirinha: str
    nome: str
    plano: str
    data_adesao: str
    sessoes_terapia_ano: int
    status: str
    cpf: str = ""
    acumulado_terapia: int = 0
    reembolsado_no_ano: float = 0.0
    historico: list[dict] = field(default_factory=list)

    @classmethod
    def de_dict(cls, d: dict) -> "Beneficiario":
        b = cls(
            carteirinha=str(d["carteirinha"]).replace(" ", ""),
            nome=d.get("nome", ""),
            plano=d.get("plano", ""),
            data_adesao=d.get("data_adesao", ""),
            sessoes_terapia_ano=int(d.get("sessoes_terapia_ano", 0)),
            status=d.get("status", "ATIVO"),
            cpf=d.get("cpf", ""),
            acumulado_terapia=int(d.get("acumulado_terapia", 0)),
            reembolsado_no_ano=float(d.get("reembolsado_no_ano_brl", 0.0)),
            historico=list(d.get("historico", [])),
        )
        if not b.acumulado_terapia:
            # sem informação melhor, o acumulado histórico soma um ano anterior
            b.acumulado_terapia = b.sessoes_terapia_ano * 2
        if not b.historico:
            b.historico = b._historico_derivado()
        return b

    def _historico_derivado(self) -> list[dict]:
        """Pedidos anteriores coerentes com o que o cadastro informa.

        O valor reembolsado é distribuído entre os pedidos de forma a somar
        exatamente o total do ano: é dessa soma que sai o saldo do teto anual, e
        o agente precisa chegar nele somando o histórico.
        """
        n = self.sessoes_terapia_ano - 1
        if n <= 0:
            return []
        base = date(2026, 1, 12)
        centavos = round(self.reembolsado_no_ano * 100)
        parcela, resto = divmod(centavos, n)
        return [
            {
                "protocolo": f"20260{200 + i:04d}",
                "data_atendimento": (base + timedelta(days=11 * i)).isoformat(),
                "categoria": "SESSAO_TERAPIA",
                "decisao": "APROVADO_PARCIAL",
                "valor_reembolsado_brl": round((parcela + (resto if i == 0 else 0)) / 100, 2),
            }
            for i in range(n)
        ]

    def publico(self) -> dict:
        """O que sai na resposta da ferramenta — sem CPF inteiro."""
        return {
            "carteirinha": self.carteirinha,
            "nome": self.nome,
            "cpf_mascarado": _mascarar_cpf(self.cpf) if self.cpf else "",
            "plano": self.plano,
            "data_adesao": self.data_adesao,
            "status": self.status,
        }


class Cadastro:
    def __init__(self, beneficiarios: list[Beneficiario]):
        self._por_carteirinha = {b.carteirinha: b for b in beneficiarios}

    def __len__(self) -> int:
        return len(self._por_carteirinha)

    def buscar(self, carteirinha: str) -> Beneficiario | None:
        return self._por_carteirinha.get(str(carteirinha).replace(" ", "").strip())

    @classmethod
    def carregar(cls, origem: str | Path) -> "Cadastro":
        caminho = Path(origem).expanduser().resolve()
        if not caminho.exists():
            raise FileNotFoundError(f"cadastro não encontrado: {caminho}")

        if caminho.is_dir():
            arquivos = sorted(caminho.glob("*/persona.json"))
            if not arquivos:
                raise ValueError(f"nenhum persona.json em {caminho}")
            brutos = [json.loads(a.read_text(encoding="utf-8")) for a in arquivos]
        else:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            brutos = dados if isinstance(dados, list) else dados["beneficiarios"]

        return cls([Beneficiario.de_dict(d) for d in brutos])
