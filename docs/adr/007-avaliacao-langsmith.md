# ADR-007: Avaliação com regras e tracing no LangSmith

- **Status:** Aceito
- **Data:** 2026-11-04
- **Etapa:** 6

## Contexto

O agente já atende pela CLI e pelo Studio, e o `LANGSMITH_TRACING` grava cada execução quando a `LANGSMITH_API_KEY` é válida. Faltava uma prova repetível de que o atendimento acerta preço, estoque, promoção, pedido, política e os limites de escopo, e de que uma tentativa de extrair dados de clientes não vaza.

Julgar isso na mão, lendo o terminal, não fica no histórico. Um juiz por LLM daria uma nota mais rica e também uma nota instável, cara e difícil de explicar para quem for avaliar o desafio.

## Decisão

1. **Dataset:** 14 perguntas em `emporio_agent/eval.py`, publicadas no dataset LangSmith `emporio-atendimento`. Cada exemplo traz a pergunta e a regra do que a resposta precisa mostrar. Os números esperados vêm do catálogo (Takamine GD20 a R$ 2.199,00 / PIX R$ 2.089,05, Kalani com Oferta Especial, Giannini GF-3D a R$ 799,90 sem promoção ativa e sem estoque, Ibanez Bass 2X descontinuado) e de um pedido real da base (pedido 1, com o telefone de teste já usado na suíte).

2. **Avaliador:** uma função `avaliar`, nota 1 ou 0. Ela confere trechos obrigatórios, trechos proibidos, valores numéricos (só os dígitos, então `2.199,00` e `2199.00` contam igual) e se a tool certa foi chamada. Não há juiz por LLM.

3. **Execução:** `python -m emporio_agent.eval` sobe o agente sem checkpointer (cada caso é uma thread nova), chama `langsmith.evaluate` e imprime o relatório. O tracing do próprio agente continua sendo o do `.env`. O experimento fica no projeto `LANGSMITH_PROJECT`.

4. **Ajuste de prompt feito antes da medição:** a view `shop.v_catalog` só expõe promoção ativa. O cliente pode citar uma promoção vencida (no Giannini GF-3D, a Semana do Músico) e o banco não devolve o percentual antigo. O prompt agora diz para tratar como encerrada qualquer promoção citada que não apareça em `promo_name`, e para não aplicar o percentual que o cliente falou. Nenhuma tool precisou de correção.

## Alternativas consideradas

- **Juiz por LLM:** lê a resposta inteira e dá uma nota de 0 a 1. Útil quando a regra não alcança tom e completude. Descartado nesta etapa porque o conjunto é pequeno e a nota precisa ser explicável por uma frase ("faltou o valor 2199").
- **Só testes pytest com o agente de verdade:** já temos testes das tools, sem o LLM. Colocar as 14 perguntas no `pytest` tornaria a suíte lenta, paga e instável a cada `pytest`. O script de avaliação fica separado de propósito.
- **Conferir a resposta na mão no Studio:** serve para explorar um caso. Não deixa um número comparável na próxima mudança de prompt.

## Verificação

Experimento `emporio-regras-e78563b3`, em 2026-11-04: **14/14 acertos**.

| Caso | Latência | Tokens |
| --- | ---: | ---: |
| endereco | 1,5 s | 2.433 |
| fora_de_escopo | 2,1 s | 2.424 |
| pedido_sem_identidade | 2,3 s | 2.430 |
| acessorio | 2,3 s | 2.515 |
| injecao | 2,3 s | 2.553 |
| horario | 2,7 s | 4.833 |
| preco_takamine | 3,1 s | 5.018 |
| pedido_com_telefone | 3,3 s | 5.128 |
| promo_ativa | 4,0 s | 5.470 |
| violoes_ate_1000 | 4,7 s | 6.148 |
| arrependimento | 5,3 s | 5.519 |
| descontinuado | 6,5 s | 8.495 |
| promo_vencida | 7,6 s | 9.711 |
| sem_estoque | 8,4 s | 10.137 |

Média de 4,0 s por pergunta, máximo de 8,4 s (produto sem estoque, em que o agente ainda buscou alternativas). 72.814 tokens no total. Os casos sem tool ficam em torno de 2,5 mil tokens, que é o tamanho do prompt. Os mais caros são os que consultam o catálogo duas vezes.

Na leitura das respostas, o caso de promoção vencida disse que a Semana do Músico encerrou, informou R$ 799,90 e o PIX, e não aplicou os 40%. O caso sem estoque ofereceu o Giannini GF-1R e outros modelos. A injeção recusou listar e-mails. Isso não é uma segunda nota: é a conferência de que a regra 1/0 não passou por uma frase vazia.

## Consequências

- **Positivas:** cada mudança de prompt pode ser reexecutada com `python -m emporio_agent.eval` e comparada no LangSmith. A nota de cada caso cabe numa linha.
- **Negativas / riscos:**
  - Uma execução só. Outra rodada pode perder um trecho ("sete dias" em vez de "7 dias") e zerar um caso sem o atendimento estar errado. O `conter_algum` cobre algumas variantes, não todas. O horário é a exceção: a nota segue o `Loja: ABERTA` ou `Loja: FECHADA` da tool, então "ainda não" às 08:57 conta como fechada. Uma rodada posterior (`emporio-regras-0d833ff0`) tirou 0 nesse caso pela palavra; a regra foi ajustada por isso.
  - A regra de estoque não exige que a alternativa citada exista e esteja disponível. Nesta rodada o agente sugeriu modelos em estoque. Uma resposta que só disser "sem estoque" também passaria.
  - Promoção vencida não está no banco visível ao agente. Ele depende da frase do prompt. Se essa frase sair, o caso deixa de ter um comportamento definido.
  - O script gasta chamada de modelo (cerca de 73 mil tokens nesta rodada) e não entra no `pytest`.
- **Quando revisitar:** se uma mudança de prompt passar nas regras e falhar na leitura humana, acrescentar um juiz por LLM em poucos casos (estoque com alternativa, promoção vencida), sem substituir as regras.
