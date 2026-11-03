# ADR-004: Tools do agente, text-to-SQL com guardrails e privacidade de pedidos

- **Status:** Aceito
- **Data:** 2026-11-03
- **Etapa:** 3

## Contexto

O agente precisa de quatro capacidades: consultar o catálogo (preço, estoque, promoções), consultar o status de um pedido, buscar regras no manual e saber se a loja está aberta. Cada uma vira uma tool que o LLM pode invocar.

A consulta ao catálogo usa text-to-SQL: o LLM escreve o SELECT e a tool executa. Isso traz riscos de injeção (DROP, UPDATE), vazamento de dados (tabelas base com dados pessoais) e alucinação de colunas. A consulta de pedidos envolve dados pessoais (LGPD) e não pode ser feita por SQL livre.

## Decisão

### 1. `consultar_catalogo(sql)` — text-to-SQL com defesa em profundidade

Duas camadas de proteção:

**Camada do banco (role `agent_ro`):**
- Só tem `SELECT` na view `shop.v_catalog`. As tabelas base (`customers`, `orders`...) são inacessíveis.
- `statement_timeout` de 5 segundos na conexão.

**Camada do código:**
- Aceita apenas um único `SELECT`, sem ponto-e-vírgula extra.
- Palavras proibidas: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `REVOKE`, `COPY`, `EXECUTE`, `SET`, `RESET`.
- Injeta `LIMIT 20` quando o LLM não incluir.

A descrição da tool inclui o schema completo da view (nomes e tipos de todas as colunas) e 4 exemplos de SQL válidos no dialeto PostgreSQL (`ILIKE`, `COALESCE`, `jsonb`). Isso funciona como few-shot para o LLM.

### 2. `consultar_pedido(order_id, phone, email)` — verificação de identidade

Tool separada, sem SQL livre. O LLM não escreve query nenhuma: ele passa o número do pedido e pelo menos um dado de contato (telefone ou e-mail). A tool faz o JOIN internamente e só retorna dados se o contato bater com o cadastro do cliente dono do pedido.

A conexão usa o **dono do banco** (não o `agent_ro`), porque precisa ler `customers`, `orders` e `order_items`. A proteção está na lógica da tool (validação obrigatória do contato), e não no role.

### 3. `buscar_politicas(pergunta)` — RAG (ADR-003)

Wrapper da função `search_policies`. Conecta como `agent_ro`, retorna os 3 trechos mais relevantes com a seção de origem.

### 4. `consultar_horario()` — data e hora atual

Retorna data/hora em `America/Campo_Grande` e se a loja está aberta, baseado no horário do manual (seção 2). Não consulta o banco.

## Alternativas consideradas

- **View de pedidos exposta ao `agent_ro` com SQL livre:** permitiria consultar qualquer pedido sem validar identidade. Descartada por risco de privacidade.
- **Verificação de identidade no prompt:** frágil; o LLM pode ser enganado por prompt injection.
- **Text-to-SQL sem guardrails no código:** o `agent_ro` já bloqueia escrita e tabelas base, mas a validação no código adiciona uma segunda barreira e dá mensagens de erro claras para o LLM corrigir a query.
- **Schema no system prompt em vez de na descrição da tool:** polui o prompt em mensagens que não precisam de SQL. Na descrição da tool, o LLM só vê o schema quando decide usar a tool.
- **Uma única tool genérica para tudo:** o LLM teria que decidir qual JOIN fazer e quando validar identidade; mais frágil e difícil de testar.

## Consequências

- **Positivas:** o agente pode consultar qualquer combinação de produto/preço/promoção com SQL livre, sem risco de escrita ou vazamento; pedidos só são acessíveis com verificação de identidade; cada tool é testável isoladamente (15 testes de integração).
- **Negativas / riscos:**
  - A `consultar_pedido` conecta como dono do banco. Se o LLM conseguisse passar SQL na variável `phone` ou `email`, haveria risco. Como os parâmetros são tipados e usados com placeholders (`%s`), não há injeção de SQL.
  - A validação por telefone ou e-mail não é autenticação real. Se alguém souber o número do pedido e o telefone do cliente, consegue ver os dados. Documentar como limitação.
  - A regex de palavras proibidas pode ter falsos positivos (por exemplo, uma coluna chamada `set_name`). Com o schema atual isso não acontece.
- **Quando revisitar:** se as tabelas crescerem e o `LIMIT 20` for restritivo demais; se for necessário paginação; se a verificação de identidade precisar de um fator mais forte (ex.: CPF ou código enviado por SMS).
