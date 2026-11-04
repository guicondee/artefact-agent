# ADR-008: Suposições e limitações da entrega

- **Status:** Aceito
- **Data:** 2026-11-04
- **Etapa:** 7

## Contexto

O manual e os CSVs não fecham em vários pontos. O agente precisa de uma resposta estável mesmo assim. As decisões de stack, dados, RAG, tools, prompt, memória e avaliação estão nos ADR-001 a ADR-007. Este registro junta o que foi assumido quando a fonte era ambígua, e o que a entrega não cobre.

## Decisão

Suposições adotadas:

1. **Telefone e e-mail da loja.** O manual cita (67) 3341-4444 na seção 1.2 e (67) 3321-4500 na seção 7, e o e-mail aparece com e sem acento. O prompt usa (67) 3341-4444 e `contato@emporiodamusica.com.br`. Os dois trechos continuam no índice do RAG. A resposta curta de "qual o telefone" sai do prompt.
2. **Prazo de devolução.** A política conta 7 dias a partir da entrega. Os pedidos só têm `estimated_delivery`, não a data em que o pacote chegou. O agente informa a regra do manual. Não calcula sozinho se o prazo de um pedido já venceu.
3. **Totais de pedido.** Os pedidos 3 e 20 não batem com o preço atual vezes a quantidade. `total_brl` é o valor cobrado, não um total recalculado.
4. **Promoção vencida.** A view só expõe promoção ativa. Se o cliente cita um desconto que não vem em `promo_name`, o prompt manda tratar como encerrado e mostrar o preço atual. O percentual antigo não está visível para o agente.
5. **Categorias sem produto.** As categorias 6, 7 e 8 não têm itens, embora o manual diga que a loja trabalha com sopros e cordas orquestrais. O agente responde pelo catálogo, não pela frase do manual.
6. **Produto 130.** Está `coming_soon`, tem estoque e aparece em pedidos. A view o marca como `coming_soon`. O agente não o trata como disponível para levar hoje.
7. **E-mail repetido.** Dois clientes compartilham `bruno.martins@jmail.com`. O e-mail sozinho não identifica um cliente. A consulta de pedido exige o número do pedido e um contato que bata com o dono daquele pedido.
8. **Cache de prompt.** O desconto de tokens repetidos é o context cache da DeepSeek, ligado por padrão. Não há Redis. Ele não guarda a resposta, então a latência da frase continua.
9. **Thinking no padrão do modelo.** O cliente não envia flag para desligar. O `deepseek-flash` pensa, e a biblioteca leva o `reasoning_content` de um passo de tool para o seguinte. Ver ADR-001.

## Alternativas consideradas

- **Corrigir o PDF e os CSVs para uma versão única.** Deixaria a demo mais limpa e esconderia o problema que o avaliador quer ver tratado. As inconsistências ficam documentadas e o comportamento do agente é explícito.
- **Calcular o prazo de arrependimento com `estimated_delivery`.** Daria uma data, com a chance de estar errada quando a entrega real atrasou. A regra é dita. A conta do prazo de um pedido específico não é feita.
- **Redis para resultado de tool.** Economizaria milissegundos de banco. O tempo medido está nas idas ao modelo. Um serviço a mais não ataca essa espera.

## Consequências

- **Positivas:** quem ler o README e este ADR sabe qual telefone o agente fala, por que uma promoção citada some, e por que o cache não deixa a primeira resposta instantânea.
- **Negativas / riscos:**
  - A verificação de pedido é o telefone ou o e-mail que o cliente declara. Não é autenticação.
  - A nota da avaliação é regra, não leitura humana. Um caso pode passar com a alternativa de estoque fraca, ou falhar só pela formulação.
  - O Studio (`langgraph dev`) não grava o histórico no schema `memory`. Quem retoma a conversa depois de fechar o programa usa a CLI.
  - O custo em dólar da DeepSeek nesta entrega ficou na casa de centavos. A limitação sentida é o tempo, não a conta.
- **Quando revisitar:** se o manual for unificado, se os pedidos ganharem data real de entrega, ou se a primeira resposta passar de poucos segundos com frequência. Nesse último caso, o caminho é uma consulta SQL só, trazendo o produto e as alternativas, e não um cache de resposta.
