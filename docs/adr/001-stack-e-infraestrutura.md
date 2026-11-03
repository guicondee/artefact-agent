# ADR-001: Stack e infraestrutura do agente

- **Status:** Aceito
- **Data:** 2026-11-03
- **Etapa:** 0

## Contexto

O desafio pede um agente de atendimento em Python que consulte dados (produtos, pedidos, promoções) e políticas (PDF), com persona, tratamento de fora de escopo e, opcionalmente, histórico de conversa. Os critérios são raciocínio e clareza das decisões, não uma solução perfeita. O prazo é curto (2 dias) e o projeto precisa ser fácil de rodar e de revisar.

## Decisão

- **Linguagem e ambiente:** Python 3.12, `venv` e `requirements.txt` com versões fixadas (`==`) nas dependências diretas, resolvidas em conjunto em 2026-11-03. As transitivas ficam limitadas por elas.
- **Framework do agente:** LangGraph (agente com tools, ciclo ReAct). LangSmith para tracing, avaliação e interação via LangGraph Studio.
- **LLM:** `deepseek-flash` (DeepSeek V4.1 Flash) via `langchain-deepseek`. Suporta tool calls e JSON output, contexto de 1M tokens e custo baixo.
- **Modo thinking do DeepSeek: desligado** (`DEEPSEEK_THINKING=disabled`). A documentação do DeepSeek diz que, com `tools` na requisição, o `reasoning_content` de todos os turnos anteriores precisa ser reenviado. Desligar o thinking evita essa dependência, reduz latência e custo, e o atendimento é majoritariamente consulta + resposta curta.
- **Embeddings:** Gemini (`gemini-embedding-001`), porque o DeepSeek não oferece API de embeddings.
- **Banco:** um único Postgres 16 com a extensão `pgvector`, via `docker compose`. Separação lógica por schemas: `shop` (dados da loja), `rag` (embeddings das políticas) e `memory` (checkpoints do LangGraph).

## Alternativas consideradas

- **SQLite + Chroma local:** menos infraestrutura, mas sem roles e permissões reais (o que enfraquece a proteção do text-to-SQL, ver ADR-004) e sem separar dados, vetores e memória em um único serviço.
- **Banco vetorial dedicado (Qdrant, Weaviate):** o volume é de cerca de 25 chunks, então um segundo serviço só somaria complexidade. Revisitar se o volume ou a necessidade de filtros e latência crescerem.
- **SDK direto, sem framework:** mais controle, porém reimplementa o loop de tools, o estado e a persistência de threads que o LangGraph já entrega, além de não aproveitar o LangSmith.
- **OpenAI / Anthropic / modelo local:** descartados pelo custo e pela preferência por um provedor com tool calling e preço baixo.
- **`uv` ou `pyproject.toml`:** funcionam bem, porém `venv` + `requirements.txt` é o formato mais universal para quem for avaliar.

## Consequências

- **Positivas:** ambiente reproduzível (`docker compose up -d` + `pip install -r requirements.txt`); permissões reais no banco; um único serviço para dados, vetores e memória.
- **Negativas / riscos:**
  - Exige Docker instalado para rodar.
  - A escolha de thinking desligado foi feita pela documentação e pela simplicidade, sem benchmark próprio. Se a escolha de tools ou a qualidade das respostas ficar fraca, ligar o thinking é a primeira hipótese. Nesse caso é preciso confirmar que o `langchain-deepseek` reenvia o `reasoning_content`.
  - `langchain-google-genai` e o tier gratuito do Gemini podem ter limites de requisição.
- **Quando revisitar:** se o volume de documentos crescer, se a qualidade do tool calling for insuficiente ou se o ambiente de execução do avaliador não tiver Docker.
