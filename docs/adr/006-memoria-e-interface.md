# ADR-006: Memória da conversa e interface

- **Status:** Aceito
- **Data:** 2026-11-03
- **Etapa:** 5

## Contexto

O agente da Etapa 4 respondia a uma mensagem por vez. O `thread_id` já ia na config da CLI, mas sem checkpointer o LangGraph não guarda estado: ao fechar o processo, e até entre uma frase e a seguinte, o histórico sumia. O plano separa esse histórico no schema `memory`, ao lado de `shop` e `rag`.

Uma conversa de atendimento também precisa de um jeito simples de continuar depois de reiniciar o programa, e de um jeito de abrir o mesmo grafo no LangGraph Studio para depurar.

## Decisão

1. **Persistência:** `PostgresSaver` (`langgraph-checkpoint-postgres==3.2.0`), no mesmo Postgres do projeto. O saver cria as tabelas com nomes sem schema (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`). A conexão da CLI usa `search_path=memory,public`, o mesmo recurso já usado no RAG (ADR-003), porque o saver não tem parâmetro de schema. `db/memory.sql` só cria o schema e tira o acesso do `PUBLIC`. Não há `DROP`: reindexar as políticas não pode apagar conversas.

2. **Quem escreve:** só o role dono do banco (`emporio`). O `agent_ro` não recebe `USAGE` em `memory`. O histórico pode ter telefone, e-mail e número de pedido (LGPD), e a tool de catálogo não precisa ler isso.

3. **Thread:** uma conversa = um `thread_id` (UUID). A CLI grava o id ativo em `.emporio_thread` (gitignored). Na próxima execução, o mesmo id é reaberto e o histórico volta do banco. `--nova` e o comando `/nova` geram outro id sem apagar o anterior. `--thread ID` retoma uma conversa específica.

4. **O que entra no contexto do modelo:** a thread inteira. O checkpointer guarda tudo; o `create_react_agent` reenvia as mensagens dessa thread a cada turno. Não há corte nem resumo nesta etapa. Uma conversa de loja é curta e o `deepseek-flash` tem contexto de 1M tokens. Cortar agora esconderia falhas (o modelo "esquecer" um dado que o cliente já deu) sem benefício medido.

5. **Interface:** a CLI continua sendo o caminho para atender e para gerar os exemplos. `langgraph.json` aponta para `emporio_agent.agent:make_graph`, sem checkpointer próprio: o `langgraph dev` injeta um checkpointer em memória, de propósito, e não usa o Postgres. A prova de que a conversa sobrevive a um reinício é a CLI.

## Alternativas consideradas

- **`InMemorySaver`:** zero infraestrutura, mas o histórico morre com o processo. Não cumpre o checkpoint desta etapa.
- **Arquivo JSON local:** simples de inspecionar, porém outro lugar para guardar dado pessoal, sem o backup e as permissões que o Postgres já tem.
- **Tabela nossa, fora do LangGraph:** dá para gravar só o texto das falas, mas o ciclo ReAct também precisa das tool calls e dos ids de checkpoint. Reimplementar isso duplica o que o `PostgresSaver` já faz.
- **Cortar o histórico agora (`trim_messages`):** reduz tokens em conversas longas. O corte vale só na entrada do modelo (`llm_input_messages`); o banco continuaria com a thread completa. Fica para quando uma conversa real passar de um tamanho que doa. Resumir com uma chamada extra de LLM custa latência e pode distorcer preço e prazo, que são exatamente o que o agente não pode inventar.
- **Studio como interface principal:** bom para depurar o grafo, ruim para o avaliador reproduzir uma conversa sem conta LangSmith. A CLI permanece a interface de entrega.

## Consequências

- **Positivas:** fechar e abrir a CLI continua a mesma conversa; o histórico fica no schema previsto, fora do alcance do text-to-SQL; o Studio abre o mesmo grafo via `langgraph dev`.
- **Negativas / riscos:**
  - O `search_path` é uma convenção, não uma trava do código do saver. Se alguém conectar o `PostgresSaver` sem essa opção, as tabelas nascem em `public`. A CLI e o teste passam sempre por `open_checkpointer()`.
  - A thread inteira vai para o modelo a cada turno. Se um atendimento ficar muito longo, o custo sobe. O sinal para rever é uma conversa que passe de algumas dezenas de turnos.
  - No Studio (`langgraph dev`) o histórico não vai para o schema `memory`. Quem for avaliar a persistência deve usar a CLI.
- **Quando revisitar:** conversas longas (passar a cortar só a entrada do modelo, sem apagar o checkpoint) ou várias instâncias da CLI ao mesmo tempo (aí o arquivo `.emporio_thread` deixa de bastar e a escolha da thread passa a ser só `--thread`).
