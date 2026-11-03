# ADR-002: Camada de dados no Postgres, tratamento dos CSVs e permissões

- **Status:** Aceito
- **Data:** 2026-11-03
- **Etapa:** 1

## Contexto

Os dados da loja chegam em seis CSVs (categorias, produtos, clientes, pedidos, itens de pedido e promoções). O agente precisa consultar preço, estoque, promoções e pedidos, e o manual da loja impõe regras que o LLM não deve calcular sozinho: "nunca informar preço ou estoque sem consultar o sistema", "promoções não são cumulativas" e "PIX tem 5% de desconto, exceto sobre preço promocional".

Um perfil dos CSVs, feito antes de modelar, encontrou:

- 65 produtos; `specs` é JSON válido em todos, mas com chaves diferentes por categoria.
- Categorias 6, 7 e 8 (sopros e cordas orquestrais) não têm nenhum produto, embora o manual diga que a loja trabalha com esses instrumentos.
- Apenas 4 promoções ativas (`is_active=1`), uma por produto. As demais estão vencidas.
- Estoque: 1 produto ativo sem estoque (96); 2 descontinuados (113 e 136); 1 "coming_soon" (130) que tem estoque e aparece em pedidos.
- Dois clientes compartilham o mesmo e-mail.
- Os totais dos pedidos 3 e 20 não batem com preço atual vezes quantidade (-1,4% e -5,9%).
- Sem espaços sobrando e sem cidades divergentes; as referências entre tabelas estão íntegras.

## Decisão

1. **Modelo relacional tipado** em `db/schema.sql` (schema `shop`): `numeric` para dinheiro, `date` para datas, `jsonb` para `specs`, chaves estrangeiras e `CHECK`s (status válidos, preço positivo, estoque não negativo, formato do código de rastreio).
2. **Tratamento no carregamento** (`scripts/load_data.py`): campos vazios viram `NULL`; `payment_method` (`credit_12x`) é dividido em `payment_method` (`credit`) e `installments` (`12`); e-mails em minúsculas; tudo em uma transação e idempotente (recria o schema a cada execução). `total_brl` é tratado como o valor efetivamente cobrado, não recalculado.
3. **Índice único parcial** garantindo no máximo uma promoção ativa por produto.
4. **Regras de negócio na view `shop.v_catalog`**, não no LLM: preço promocional calculado só para promoção ativa, preço PIX (5%) só quando não há promoção, e `availability` (`in_stock`, `out_of_stock`, `discontinued`, `coming_soon`).
5. **Menor privilégio:** o agente usa o role `agent_ro`, que só tem `SELECT` em `v_catalog`. Tabelas base, entre elas as de clientes e pedidos, ficam inacessíveis a ele.
6. **Pedidos não são expostos nesta etapa.** Uma view de pedidos permitiria consultar qualquer pedido só pelo número. O acesso será por uma função que exige o número do pedido mais um contato do cliente, e é tema do ADR-004.
7. **Criação do banco:** `docker/initdb` só habilita a extensão `vector` (infraestrutura, roda uma vez). Schema e dados são criados por script Python, para poder recriar tudo com um comando durante o desenvolvimento.

## Alternativas consideradas

- **pandas em memória:** simples, mas sem restrições de integridade, sem permissões e sem um banco real para o agente consultar.
- **Schema inteiro em `docker/initdb`:** declarativo, mas só roda quando o volume é novo; iterar no schema exigiria `docker compose down -v` a cada mudança.
- **Calcular preço e disponibilidade no prompt ou na tool:** mais frágil, porque o LLM pode errar a aritmética ou esquecer a regra de PIX com promoção.
- **Expor `v_orders` ao agente agora:** mais simples, mas vaza dados de pedido sem validar identidade (LGPD).
- **Colunas em português nas views:** descartado para manter os nomes alinhados aos CSVs de origem; o contexto do agente descreverá cada coluna.

## Consequências

- **Positivas:** regras de preço em um só lugar e testáveis em SQL; o banco impõe as permissões, mesmo que o LLM gere SQL inesperado; carga reproduzível com um comando (`python scripts/load_data.py`).
- **Negativas / riscos:**
  - A regra "PIX 5%" fica duplicada entre o manual e a view; se a política mudar, é preciso atualizar a view.
  - As anomalias de dados (produto 130, produto 136 descontinuado com estoque, categorias sem produtos) são tratadas pelo agente na resposta, não corrigidas no dado.
  - A senha do `agent_ro` tem um default de desenvolvimento (`agent_ro_dev`); em produção deve vir de um gerenciador de segredos.
- **Quando revisitar:** se as regras de preço ficarem mais complexas (frete, parcelamento), se surgirem tabelas muito grandes (índices) ou se a política de identidade mudar.
