# Empório da Música

Agente de atendimento de uma loja de instrumentos em Campo Grande/MS. Responde preço, estoque, promoção, pedido e política da loja. Recusa acessório, assunto fora da loja e pedido de lista de clientes.

O ciclo é o ReAct do LangGraph, com `deepseek-flash`. Os dados ficam num Postgres 16 com pgvector. O histórico da CLI fica no schema `memory`. O tracing e a avaliação ficam no LangSmith.

## Pré-requisitos

- Docker, com `docker compose`
- Python 3.12
- Chaves em `.env` (não commitar): `DEEPSEEK_API_KEY` e `GOOGLE_API_KEY`. `LANGSMITH_API_KEY` entra para o Studio, o tracing e a avaliação

```bash
cp .env.example .env
```

## Subir

Na raiz do repositório:

```bash
docker compose up -d
docker compose ps
```

O serviço `db` fica healthy quando o `pg_isready` passa. A porta do host é `5433`, para não bater com um Postgres local.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m emporio_agent.load_data
.venv/bin/python -m emporio_agent.rag index
```

`load_data` recria o schema `shop`, carrega os CSVs e cria o role `agent_ro`. `rag index` gera os embeddings do manual e grava no schema `rag`.

## Conversar

```bash
.venv/bin/python -m emporio_agent
```

A conversa continua depois de fechar o programa. `--nova` ou `/nova` abre outra. `sair` encerra. O id ativo fica em `.emporio_thread`, fora do git.

## Studio e tracing

O Studio é a conversa ao vivo com o grafo. O LangSmith é o registro.

```bash
.venv/bin/pip install "langgraph-cli[inmem]==0.4.40"
.venv/bin/langgraph dev
```

O comando imprime o link do Studio e sobe em `http://127.0.0.1:2024`. Com `LANGSMITH_TRACING=true`, a mesma conversa aparece em Tracing, no projeto `emporio-agent`. O histórico do Studio não vai para o schema `memory`. Quem retoma a conversa no dia seguinte usa a CLI.

## Avaliação

A prova repetível do atendimento fica no LangSmith, no dataset `emporio-atendimento`. As 14 perguntas estão em `emporio_agent/eval.py`: preço, catálogo, endereço, arrependimento, pedido com e sem telefone, promoção ativa e vencida, estoque, produto descontinuado, horário, acessório, assunto fora da loja e uma tentativa de listar e-mails de clientes.

Cada exemplo guarda a pergunta e a regra do que a resposta precisa mostrar. A função `avaliar` dá nota 1 ou 0. Ela confere a tool chamada, o valor (só os dígitos, então `2.199,00` e `2199` contam igual), um trecho obrigatório ou um trecho proibido. O comentário da nota diz a regra que falhou, por exemplo `faltou o valor 2199`. Não há juiz por LLM: a nota cabe numa frase e uma rodada se compara com a seguinte. O detalhe está no [ADR-007](docs/adr/007-avaliacao-langsmith.md).

```bash
.venv/bin/python -m emporio_agent.eval
```

O comando pede `DEEPSEEK_API_KEY` e `LANGSMITH_API_KEY`. Na primeira vez ele cria o dataset. Nas seguintes, só regrava os exemplos quando a regra local mudou. Cada pergunta roda numa thread nova, sem o histórico da CLI. O `langsmith.evaluate` grava um experimento com o prefixo `emporio-regras` no projeto `emporio-agent`.

No LangSmith, a tabela do experimento mostra a nota `acerto`, a latência e os tokens de cada pergunta. Abrir uma linha abre o trace: qual tool rodou, quanto tempo levou e, no passo `ChatDeepSeek`, o hit do cache de contexto. A CLI também manda trace para o mesmo projeto quando `LANGSMITH_TRACING=true`. O experimento é o registro que dá para comparar depois de mudar o prompt.

O script fica fora do `pytest`. Ele gasta chamada de modelo, e a frase pode mudar de uma rodada para outra. Os testes automatizados cobrem as tools e a função `avaliar`, sem chamar o LLM.

Rodada usada nos prints, `emporio-regras-e66dbe31`, em 2026-11-04: **14/14**, média de **2,86 s**, **76.597** tokens. O caso mais lento foi o produto sem estoque, porque o agente consulta o catálogo e ainda busca alternativa.

![As 14 perguntas, todas com nota 1](docs/img/langsmith-avaliacao.png)

O cache de contexto da DeepSeek já vem ligado. Não há Redis. No passo `ChatDeepSeek` desta rodada o hit ficou em **94%**: **2.176** tokens em `cache read` (o prompt e as tools, que se repetem) e o restante em miss. O tempo do modelo continua na casa de 1 a 2,5 s, porque a frase é gerada de novo. A busca no manual, no mesmo trace, levou 0,55 s.

![Hit de 94% no passo do modelo, ao lado da busca de política](docs/img/langsmith-cache.png)

## Exemplos

Cinco atendimentos registrados na avaliação, em [`examples/`](examples/):

- [Produto sem estoque](examples/01-sem-estoque.md)
- [Promoção vencida](examples/02-promocao-vencida.md)
- [Acessório e fora de escopo](examples/03-acessorio-e-fora-de-escopo.md)
- [Pedido com e sem identidade](examples/04-privacidade-do-pedido.md)
- [Direito de arrependimento](examples/05-politica-de-arrependimento.md)

## Decisões

O agente é um ReAct do LangGraph (`create_react_agent`). Há quatro tools, e uma pergunta pode pedir mais de uma consulta: produto sem estoque, por exemplo, segue com uma busca por alternativas. Esse ciclo já faz a volta de raciocinar, chamar a tool e responder. Um roteador à parte acrescentaria uma chamada só para classificar a mensagem. O detalhe está no [ADR-001](docs/adr/001-stack-e-infraestrutura.md) e no [ADR-005](docs/adr/005-agente-langgraph-persona-e-prompt.md).

O modelo de conversa é o `deepseek-flash`, pela `langchain-deepseek`. Ele aceita tool calling, tem contexto de 1M tokens e custa pouco para um protótipo. O cliente sobe com o modelo e a chave. O thinking fica no padrão do provedor, e a biblioteca carrega o `reasoning_content` entre as tools. Os embeddings do manual são do Gemini (`gemini-embedding-001`): esse modelo de chat não tem API de embedding.

O manual vira Markdown, com um chunk por seção numerada (25 trechos). Cada trecho vira um vetor de 768 dimensões no schema `rag`, via `PGVector`. A busca é por cosseno e devolve os 3 trechos mais próximos, percorrendo a tabela inteira. Com 25 linhas, um índice aproximado não muda o resultado. A tool devolve o texto com o número e o título da seção. O detalhe está no [ADR-003](docs/adr/003-rag-das-politicas.md).

O system prompt está dividido por responsabilidade: persona (informal, como um amigo que entende de música), fluxo de atendimento, regras de preço e estoque, escopo da loja e privacidade do pedido. Preço, estoque e prazo saem de uma tool. Endereço, telefone (67) 3341-4444 e e-mail ficam no prompt, porque não mudam de uma mensagem para outra.

Promoção ativa, preço no PIX e disponibilidade já vêm calculados na view `shop.v_catalog`. O role `agent_ro` tem `SELECT` nessa view e nas tabelas do RAG. Pedido só volta com o número e um telefone ou e-mail que bata com o dono. O detalhe está no [ADR-002](docs/adr/002-camada-de-dados-postgres.md) e no [ADR-004](docs/adr/004-tools-sql-e-privacidade.md).

A interface de entrega é a CLI (`python -m emporio_agent`). O histórico fica no schema `memory`, com `PostgresSaver`: fechar o programa continua a mesma conversa. O Studio (`langgraph dev`) mostra o grafo ao vivo, e o histórico dele fica na memória do processo. O detalhe está no [ADR-006](docs/adr/006-memoria-e-interface.md).

| ADR | O que ficou |
| --- | --- |
| [001](docs/adr/001-stack-e-infraestrutura.md) | LangGraph, DeepSeek Flash, Gemini para embedding, um Postgres com pgvector. |
| [002](docs/adr/002-camada-de-dados-postgres.md) | Preço, PIX e disponibilidade na view `shop.v_catalog`. O role `agent_ro` lê a view. |
| [003](docs/adr/003-rag-das-politicas.md) | Um chunk por seção, embedding Gemini, cosseno no pgvector, top 3. |
| [004](docs/adr/004-tools-sql-e-privacidade.md) | Catálogo em SQL somente leitura. Pedido só com número e telefone ou e-mail. |
| [005](docs/adr/005-agente-langgraph-persona-e-prompt.md) | ReAct com as quatro tools. Persona e regras no system prompt. |
| [006](docs/adr/006-memoria-e-interface.md) | Histórico no schema `memory`. CLI é a interface de entrega. Studio é para depurar. |
| [007](docs/adr/007-avaliacao-langsmith.md) | 14 casos, nota por regra, experimento no LangSmith. |
| [008](docs/adr/008-suposicoes-e-limitacoes.md) | O que foi assumido quando o manual ou o CSV não fechava. |

## Suposições

O detalhe está no [ADR-008](docs/adr/008-suposicoes-e-limitacoes.md). Em resumo:

- O telefone falado pelo agente é (67) 3341-4444. O manual também cita 3321-4500.
- O prazo de 7 dias conta da entrega. O pedido só tem a data prevista, então o agente explica a regra e não decreta se um pedido específico ainda está no prazo.
- Promoção que não aparece na view está encerrada.
- O total do pedido é o valor cobrado, mesmo quando não bate com o preço de hoje.

## Limitações

- Saber o número do pedido e o telefone do cliente basta para ver o pedido. Não há senha nem segundo fator.
- A avaliação não confere se a alternativa sugerida para um item sem estoque existe de verdade no catálogo.
- Uma rodada nova pode zerar um caso só porque a frase mudou. O horário segue o status da tool, para "ainda não" às 08:57 contar como fechada.
- A primeira resposta não fica instantânea com o cache da DeepSeek. O cache abaixa o preço do prompt repetido.

## Com mais tempo

- Uma consulta SQL só, quando o produto não tem estoque, trazendo o item e as alternativas da mesma categoria. Isso tira uma ida ao modelo. É o que reduz os 7 s desse caso, não um Redis.
- Um juiz por LLM só nos casos em que a regra não alcança, como a qualidade da alternativa sugerida.
- Data real de entrega, para o prazo de arrependimento deixar de ser só a regra e passar a ser uma conta.

## Uso do Cursor

Usei o Cursor em linguagem natural, etapa por etapa, do banco até a avaliação. O plano e as decisões de arquitetura saíram dessa conversa: stack, schemas, RAG, tools, prompt, memória e a avaliação. O agente implementava a etapa. Eu lia o código, testava na CLI e no LangSmith e só então aceitava. A decisão aceita ia para um ADR antes da etapa seguinte.

Os commits ficaram manuais, um por etapa. O `.env` não entra no git. Latência, tokens e o hit de cache foram lidos nos traces do LangSmith e nos prints desta página.
