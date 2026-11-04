# ADR-005: Agente LangGraph com persona e prompt estruturado

- **Status:** Aceito
- **Data:** 2026-11-03
- **Etapa:** 4

## Contexto

Com as 4 tools prontas (ADR-004), o agente precisa decidir quando usar cada uma e responder ao cliente com a persona e as regras da loja. O manual (seção 7.1) define o tom como "informal mas profissional, como um amigo que entende de música", e o fluxo de atendimento (seção 7.2) tem 5 passos: saudação, entendimento, consulta, resposta e fechamento.

## Decisão

1. **Arquitetura:** `create_react_agent` do `langgraph.prebuilt`, que implementa o ciclo ReAct (raciocinar, escolher tool, executar, observar, responder). O agente roda o ciclo quantas vezes precisar até ter informação suficiente.

2. **LLM:** `deepseek-flash` via `ChatDeepSeek`. O thinking vem ligado por padrão (o modelo devolve `reasoning_content`), e isso não atrapalha o ciclo de tools: o `langchain-deepseek` gerencia o campo automaticamente.

3. **System prompt** (`emporio_agent/agent.py`), organizado por responsabilidade:
   - **Persona:** tom informal e profissional, emojis com moderação.
   - **Fluxo de atendimento:** os 5 passos do manual.
   - **Regras de ouro:** nunca informar preço sem consultar, mostrar preço de tabela e promocional juntos, PIX não vale sobre promoção, sugerir alternativas para produtos sem estoque ou descontinuados, nunca prometer promoção vencida.
   - **Escopo:** a loja só vende instrumentos; acessórios e assuntos alheios são redirecionados.
   - **Pedidos:** exige número do pedido mais telefone ou e-mail.
   - **Dados da loja:** endereço, telefone e e-mail fixos no prompt (evita uma chamada de tool para perguntas simples).

4. **Interface:** CLI simples (`python -m emporio_agent`) com streaming por nó, thread por sessão.

## Alternativas consideradas

- **Grafo explícito com roteador:** mais controle sobre o fluxo (ex.: nó de classificação que decide se é catálogo, pedido ou política antes de chamar a tool). Desnecessário neste estágio, porque o `create_react_agent` já decide bem entre 4 tools. Revisitar se o agente começar a usar a tool errada com frequência.
- **SQL agent do LangChain (`create_sql_agent`):** inclui um toolkit que descobre o schema automaticamente, mas oferece menos controle sobre quais tabelas são visíveis e sobre a formatação da resposta.
- **Duas passadas (classificação + execução):** a primeira chamada decide o tipo de pergunta e a segunda executa. Aumenta latência e custo sem ganho claro para 4 tools.
- **Dados da loja como tool em vez de fixos no prompt:** o endereço e o telefone não mudam entre mensagens, então gastar uma chamada de tool para isso é desperdício.

## Verificação

Os 4 cenários sugeridos pelo desafio funcionam corretamente:
- "Quais opções de violões disponíveis custando até R$1000?" — lista 12 violões com preço de tabela e preço PIX.
- "Qual o endereço da loja?" — responde direto do prompt, sem tool.
- "Quanto custa o Takamine GD20?" — consulta o catálogo e mostra preço de tabela e PIX.
- "Me arrependi da minha compra, posso devolver meu pedido?" — busca a política 4.1 e explica o direito de arrependimento.

Cenários extras:
- "Vocês vendem cordas de guitarra?" — redireciona educadamente.
- "Quem ganhou o jogo ontem?" — informa que só trata de assuntos da loja.

## Consequências

- **Positivas:** o agente funciona de ponta a ponta; o prompt é legível e organizado por seção; o `create_react_agent` cuida do ciclo de tools e da gestão de mensagens.
- **Negativas / riscos:**
  - O prompt é longo (~2000 tokens). Para manter o custo sob controle, o thinking desligado seria melhor, mas o DeepSeek não oferece essa opção por tool individual. O custo se mantém baixo por causa do preço do modelo.
  - O agente pode fazer chamadas de tool desnecessárias (por exemplo, buscar políticas quando a resposta já está no prompt). Monitorar via LangSmith na Etapa 6.
  - O `create_react_agent` não limita o número de iterações por padrão. Se o LLM entrar em loop, ele pode fazer muitas chamadas. Revisitar com `recursion_limit` se necessário.
- **Quando revisitar:** se a qualidade cair (migrar para grafo explícito), se o custo crescer (desligar thinking ou trocar modelo), ou se forem necessários mais de 4 tools (avaliar roteamento).
