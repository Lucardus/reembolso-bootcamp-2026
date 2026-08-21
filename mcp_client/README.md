# Servidor MCP da operadora

Não é seu para implementar — é a dependência externa do seu agente, e vem
pronta. Três ferramentas, por HTTP streamable:

| Ferramenta | Devolve |
|---|---|
| `consultar_beneficiario(carteirinha)` | plano, data de adesão, sessões de terapia no ano, situação do contrato. O CPF sai **mascarado** |
| `consultar_historico(carteirinha)` | os pedidos de reembolso anteriores, do mais antigo ao mais recente |
| `abrir_protocolo(carteirinha, payload)` | o número do protocolo gerado |

## Subir

Pelo compose, junto com o seu agente:

```bash
docker compose up mcp          # só o MCP, na porta 9000
docker compose up              # o MCP e o seu agente
```

Ou direto, sem Docker — a mesma `.venv` do projeto serve:

```bash
MCP_OPERADORA_DADOS=./casos_treino MCP_OPERADORA_TOKEN=treino \
  python -m mcp_operadora.server
```

Rodando de dentro desta pasta (`mcp/`), com `PYTHONPATH=.` se preciso. O
endereço é `http://localhost:9000/mcp`, e o token vai no header
`Authorization: Bearer treino` — os dois já estão no seu `.env`.

## De onde vêm os beneficiários

`MCP_OPERADORA_DADOS` aceita duas coisas:

- **uma pasta `casos_treino/`** — cada `*/persona.json` vira um beneficiário. É
  o seu modo: aponte para a sua pasta e o servidor fica em dia com os casos que
  você recebeu, sem duplicar arquivo nenhum;
- **um arquivo JSON** com uma lista de beneficiários. É o modo da banca na
  correção, com as personas que não estão no seu pacote.

Por isso não decore carteirinha: na avaliação o cadastro é outro, com outras
pessoas, outros planos e outro histórico. O que tem de funcionar é o seu cliente.

## O histórico não vem de graça

Quando o cadastro não traz `historico` explícito, o servidor deriva pedidos
anteriores coerentes com o que ele informa — um beneficiário com 4 sessões no
ano tem 3 pedidos anteriores, e os valores somam exatamente o total do ano.

É de lá que sai o saldo do teto anual. Somar esse histórico é trabalho do seu
agente, e há caso na avaliação que depende disso.

## Variáveis

| | Padrão |
|---|---|
| `MCP_OPERADORA_DADOS` | `/dados` |
| `MCP_OPERADORA_TOKEN` | vazio — sem token, não exige autenticação |
| `MCP_OPERADORA_HOST` · `PORT` | `127.0.0.1` · `9000` |
| `MCP_OPERADORA_ESQUEMA` | `v1` |
