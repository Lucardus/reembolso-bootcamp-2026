# Comece por aqui

O enunciado completo está em **`instrucoes_da_prova.pdf`**. Leia antes de
codificar — ele define o que é avaliado, e há regra sobre como usar IA nele.

Isto aqui é só para você começar a rodar em cinco minutos.

## 1. A chave já está aqui

**Não há nada para configurar.** O `.env` deste pacote já vem com o endpoint e a
chave preenchidos. Nenhuma chave de nuvem, nenhum provedor, nenhuma região —
abra e use.

A chave é **compartilhada pela turma**, com um crédito comum de 100 milhões de
tokens de entrada e 100 milhões de saída. O que você gasta sai do bolo de todo
mundo, e não há recarga.

O arquivo está no `.gitignore`, então `git add -A` não o leva para o seu
repositório. **Não publique a chave**: exposta, ela é revogada — e aí ninguém
da turma trabalha até sair outra.

## 2. Confira que está de pé

**Python 3.11** — a mesma do Dockerfile.

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.llm
```

Saída esperada:

```
chat      : pronto.
embeddings: 1536 dimensões
saldo     : {'candidato': '...', 'entrada': {...}, 'saida': {...}}
```

## 3. O modelo

**Gemini 2.5 Flash Lite**, servido por um gateway da banca. Você não escolhe
modelo — é o mesmo para todos os candidatos.

`app/llm.py` já traz tudo montado. Use e siga; ninguém é avaliado por acertar
`base_url`.

```python
from app.llm import criar_llm, criar_embeddings

llm = criar_llm()                    # ChatGoogleGenerativeAI, pronto para bind_tools
emb = criar_embeddings()             # gemini-embedding-2, 1536 dimensões
```

Com LlamaIndex:

```python
from llama_index.core import Settings
from app.llm import criar_llm_llamaindex, criar_embeddings_llamaindex

Settings.llm = criar_llm_llamaindex()
Settings.embed_model = criar_embeddings_llamaindex()
```

E um agente com ferramentas, que é o que a prova pede:

```python
from langgraph.prebuilt import create_react_agent
from app.llm import criar_llm

agente = create_react_agent(criar_llm(), [suas_ferramentas_mcp])
```

## 4. As bibliotecas são sugestão

O `requirements.txt` traz um conjunto **sugerido**, com as versões fixadas — são
as que a prova usou e que resolvem juntas no Python 3.11. Instalar e sair
codificando funciona.

| | Versão |
|---|---|
| `langchain-google-genai` | 4.3.2 |
| `langgraph` · `langchain-core` | 1.2.10 · 1.5.3 |
| `llama-index-core` | 0.14.23 |
| `llama-index-llms-google-genai` · `-embeddings-` | 0.9.6 · 0.5.1 |
| `llama-index-retrievers-bm25` | 0.7.1 |
| `fastapi` · `uvicorn` · `pydantic` · `httpx` | 0.141.1 · 0.52.1 · 2.13.4 · 0.28.1 |
| `pymupdf` · `pytesseract` · `pillow` · `python-docx` | 1.28.2 · 0.3.13 · 12.3.0 · 1.2.0 |
| `mcp` | 1.29.0 — **não** 2.0: a série 2.0 removeu o `fastmcp` que o servidor usa |

**Pode trocar.** Outra biblioteca, outra versão, outro framework de API. O que
não muda são as exigências do item 4 do enunciado (grafo, LlamaIndex na
indexação, vector store embarcado, busca híbrida, Pydantic na saída) e o
contrato do item 6.

Se trocar, **fixe a versão que usou**. Build que resolve dependência na hora
quebra sozinho entre o seu teste e a correção — e aí quem perde é você.

> Nota sobre o LangGraph 1.x: `langgraph.prebuilt.create_react_agent` ainda
> funciona, mas avisa que mudou para `langchain.agents.create_agent`. Vale
> lembrar que o item 4 pede supervisor com handoff explícito — um ReAct pronto
> resolve o "chamar ferramenta", não a arquitetura que a prova cobra.

## 5. O crédito é da turma

**100 milhões de tokens de entrada e 100 milhões de saída, compartilhados.**
Não há recarga.

```bash
.venv/bin/python -c "from app.llm import saldo; print(saldo())"
```

Esgotou, as chamadas passam a devolver `429` — para todo mundo. Duas
consequências práticas:

- **Teto de 50 mil tokens de entrada por chamada.** Acima disso vem `413`. Um
  agente que recupera os trechos certos manda alguns milhares por turno e nunca
  encosta nesse limite; quem tenta enviar a base inteira no prompt bate nele no
  primeiro turno. A base tem ~89 mil tokens.
- **Não deixe laço rodando.** Um `while True` esquecido de madrugada é crédito
  que faltou para o colega no dia seguinte.

## 6. Suba o servidor MCP

Ele **vem no pacote**, em `mcp/` — nada para baixar. Duas formas:

```bash
docker compose up mcp                            # porta 9000
```

```bash
cd mcp && MCP_OPERADORA_DADOS=../casos_treino MCP_OPERADORA_TOKEN=treino \
  ../.venv/bin/python -m mcp_operadora.server    # sem Docker
```

Confira que respondeu:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9000/mcp   # 401 = de pé
```

`401` é o esperado sem token — significa que o servidor está no ar e exigindo o
`Authorization: Bearer treino`, que já está no seu `.env`.

Três ferramentas: `consultar_beneficiario`, `consultar_historico` e
`abrir_protocolo`. O detalhe de cada uma está em `mcp/README.md` — vale ler o
trecho sobre o histórico, porque há caso na avaliação que depende de somá-lo.

**O cadastro da avaliação é outro.** Localmente o servidor lê as personas do seu
`casos_treino/`; na correção a banca sobe o mesmo servidor com outro arquivo,
com outras pessoas. Não decore carteirinha — o que tem de funcionar é o cliente.

## 7. Rodar os casos de treino

Precisa estar de pé: o **MCP na 9000** e o **seu container na 8000**. O script
não sobe nada por você.

```bash
.venv/bin/python rodar_treino.py          # as três conversas
.venv/bin/python rodar_treino.py -v       # mostra cada turno
.venv/bin/python rodar_treino.py --caso 02
```

Não é uma bateria de asserções sobre uma resposta pronta. Por turno:

1. um modelo faz o papel do beneficiário e escreve a mensagem, reagindo à sua
   resposta anterior;
2. ela vai para o seu `POST /chat`, mesmo `session_id`, anexo em base64;
3. o **juiz** — outro modelo — decide se aquele turno foi atendido;
4. no último turno o juiz também recebe o gabarito e confere se você não o
   contradiz;
5. sem modelo nenhum: porta de entrada (resposta repetida) e violações de CPF,
   CID e dado de terceiro.

**As duas pontas usam o mesmo endpoint e a mesma chave do seu `.env`** — o
mesmo proxy e o mesmo modelo que respondem ao seu agente. É o mesmo código da
correção, em `avaliacao/`; abra e leia, não existe rubrica oculta.

Uma rodada completa custa uns 13 mil tokens de entrada, fora o que o seu agente
gasta. Pouco — mas o bolo é dividido, então não deixe em laço.

A nota de cada conversa vem **70% dos turnos atendidos e o restante do
desfecho correto**; a nota final é a média das conversas. Estas três **não valem nota** — as da
avaliação oficial são outras, e lá a conta é a mesma.

## Onde fica o quê

```
app/llm.py          o modelo, já configurado — comece por ele
mcp/                o servidor MCP da operadora, pronto — só subir
app/main.py         o contrato HTTP: /health, /chat, /reset
app/agents/         supervisor e subagentes: é aqui que está a prova
app/rag/            recuperação sobre a kb/
ingest/build.py     constrói o índice em storage/ (rode antes do Docker)
kb/                 os 10 documentos normativos da sua prova
casos_treino/       as três conversas de treino
avaliacao/          o motor de correção — leia, não precisa alterar
```
