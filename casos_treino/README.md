# Casos de treino

Três conversas mockadas com o resultado esperado já calculado. **Não valem nota** —
servem para você conferir se o seu fluxo está de pé antes da bateria oficial.

As 10 situações da bateria são **outras**. Passar aqui não garante nota; errar
aqui garante que alguma coisa está errada.

## Como rodar

1. Suba o container e confirme o `GET /health`.
2. Para cada caso, envie os turnos de `turnos.jsonl` em ordem, via `POST /chat`,
   sempre com o **mesmo `session_id`** — o Juiz não reenvia histórico, quem
   guarda o estado é você.
3. Compare a resposta do último turno com o `esperado.json`.

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' -d '{
  "session_id": "treino-01",
  "mensagem": "oi boa tarde, fui numa dermatologista particular esse mês..."
}'
```

Quando o turno tiver `anexo`, o arquivo está no `path` indicado, relativo à pasta
do caso. Mande o conteúdo em base64 no campo `anexo.base64`, como na bateria
oficial.

## O que comparar

| Campo | Tolerância |
|-------|------------|
| `decisao` | exata |
| `valor_reembolso_brl` | ± R$ 0,01 |
| `valor_solicitado_brl` | ± R$ 0,01 |
| `categoria_documento` | exata |
| `regras_aplicadas` | os dispositivos têm de existir na `kb/` e se aplicar ao caso |
| `pendencias` | o conteúdo pode variar; o que importa é pedir a coisa certa |
| `protocolo` | o número vem do MCP e não dá para prever — compara-se se foi aberto ou não |

## A porta de entrada

O script roda a mesma verificação que abre a correção: **resposta repetida
palavra por palavra em turnos diferentes**. Se ele acusar isso, a conversa
correspondente vale zero na avaliação — não perde ponto, vale zero.

Um atendimento real nunca devolve a mesma frase duas vezes para mensagens
diferentes.

## O que este script não mede

Ele confere os campos estruturados, a porta de entrada e as violações de CPF,
CID e dado de terceiro. **Não julga o conteúdo de cada turno** — se você
respondeu o que foi perguntado.

Na correção, todo turno é avaliado, e **um único turno não atendido derruba a
conversa inteira**, ainda que a decisão e o valor no fim estejam corretos.

Alguns turnos trazem perguntas cuja resposta está na `kb/` e não cabe em texto
pronto — "meu plano cobre acupuntura?", "se eu perder o prazo dá pra recorrer?".
O script mostra em quais turnos elas estão.

## Aqui o roteiro é fixo; lá, não

Estes três casos usam as mensagens literais do `turnos.jsonl`, para você poder
depurar. Na avaliação oficial o beneficiário é **simulado por um modelo**: tem um
roteiro de intenções, mas escreve com as palavras dele e reage ao que você
respondeu.

Se o seu agente depende do texto exato destas mensagens, ele passa aqui e
reprova lá.

Os campos com `_` no começo (`_titulo`, `_dica`, `_data_da_conversa`) são
contexto para você e não fazem parte do contrato do `/chat`. A `_dica` só faz
sentido quando o caso falha — leia depois de comparar, não antes.

## Os três casos

| Pasta | Situação | Decisão final |
|-------|----------|---------------|
| `01_fora_de_ordem` | O anexo chega antes de qualquer contexto; no meio, o beneficiário pergunta pelo plano da esposa e depois confunde uma data | `APROVADO` |
| `02_sessao_pelo_historico` | Psicoterapia. O recibo não traz o número da sessão e o beneficiário não sabe qual é. Dá pendência, e o relatório chega num turno seguinte | `APROVADO_PARCIAL` |
| `03_invalido_e_alcada` | O primeiro anexo não é documento fiscal; o segundo é uma prótese cara | `ESCALADO_ANALISTA` |

Cada caso é composto de propósito: exercita várias etapas do fluxo, e não uma só.
Os três juntos cobrem as três ferramentas do MCP, dois anexos numa mesma conversa,
guardrail que não pode encerrar o atendimento, e três decisões diferentes.

## O que cada um cobra

**O grafo aceita entrar por qualquer nó.** No caso 1 o anexo chega no turno 1,
sem carteirinha e sem pedido. Se o seu fluxo exige a ordem "intenção →
carteirinha → documento", ele trava logo na primeira mensagem.

**Guardrail não encerra atendimento.** Ainda no caso 1, o beneficiário pede o
caso da esposa no meio da conversa. Recusar é obrigatório; parar de atender o
pedido dele, não.

**O beneficiário nem sempre sabe.** No caso 2 ele chuta o número de sessões e
erra. O recibo não traz esse campo, e a Nota Técnica 02 diz onde buscá-lo — só
o `consultar_historico` responde.

**Pendência não é fim.** Ainda no caso 2, o documento que faltava chega num turno
seguinte. O protocolo tinha de continuar aberto, com o resto do estado
preservado.

**Coparticipação não torna o reembolso parcial.** No caso 1 o beneficiário recebe
menos do que pagou e a decisão é `APROVADO`. `APROVADO_PARCIAL` é quando o
**teto** corta o valor.

**O teto que vale pode não estar onde você olhou.** No caso 2, o artigo do teto
foi alterado por circular — e depois por outra, de número menor e vigência mais
recente.

**Inválido, não coberto e incompleto são coisas diferentes.** No caso 3 o
primeiro anexo não é documento fiscal: não vira pendência de campo nem despesa
não coberta, e o protocolo segue aberto.

**Nem tudo é você quem decide.** O segundo anexo do caso 3 vai para análise
humana. Abrir o protocolo faz parte da resposta certa; informar valor de
reembolso, não.

## A conversa importa

O gabarito olha a resposta do **último turno**, mas os turnos intermediários
existem por um motivo: no caso 2 o beneficiário pergunta se precisa de relatório,
e no caso 1 ele pergunta por que não voltam os R$ 240 inteiros. Um agente que
responde bem o número e mal a pergunta passa aqui e sofre na bateria — a
avaliação oficial conduz a conversa turno a turno.
