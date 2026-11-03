# ADR-003: RAG das políticas com componentes do LangChain e pgvector

- **Status:** Aceito
- **Data:** 2026-11-03
- **Etapa:** 2

## Contexto

O agente precisa responder perguntas sobre regras da loja (horário, pagamento, trocas, frete, garantia, privacidade, diretrizes de atendimento) com base no manual em PDF, sem inventar regras. O manual tem 8 páginas e cerca de 25 trechos de conteúdo. Uma resposta errada aqui vira informação errada para o cliente (por exemplo, prazo de devolução), então a recuperação precisa trazer o trecho certo, inteiro.

O projeto já usa LangChain/LangGraph (ADR-001). Para carregar, dividir, embutir e armazenar documentos, o ecossistema já oferece componentes padrão, e a regra adotada é **usá-los, em vez de reimplementar**.

Observações sobre o PDF, feitas antes de decidir:

- A extração de texto simples (`pypdf`, modo padrão) devolve uma palavra por linha, o que inviabiliza dividir por estrutura. O `pymupdf4llm` converte o PDF em **Markdown já com títulos (`#`, `##`) e tabelas**.
- O PDF repete cabeçalho e rodapé em toda página e mistura tamanhos de fonte nos títulos (a seção 5.3 sai como `#` em vez de `##`).
- O manual traz inconsistências que o agente deve conhecer (dois telefones: 3341-4444 em 1.2 e 3321-4500 em 7; e-mail com e sem acento; regras de parcelamento sobrepostas entre a tabela da seção 3 e a 3.1). Elas são mantidas no índice e tratadas no prompt (ADR-005), não corrigidas.

## Decisão

1. **Carregamento:** `PyMuPDF4LLMLoader` (`langchain-pymupdf4llm`), que produz Markdown.
2. **Limpeza mínima do Markdown** (6 regras em `emporio_agent/policies.py`): remove separadores de página, cabeçalho e rodapé repetidos, e refaz o nível dos títulos pela **numeração** (`N.` é seção, `N.M` é subseção). Títulos sem número (capa, slogan) viram texto comum.
3. **Divisão:** `MarkdownHeaderTextSplitter` (`langchain-text-splitters`) por `#` e `##`. Um chunk por subseção, ou por seção sem subseções. Resultado: 25 chunks (a capa é descartada).
4. **Cabeçalho contextual:** cada chunk começa com `Manual de Políticas, seção 4.1: Direito de Arrependimento (em "Política de Trocas e Devoluções")`, para que o embedding saiba de que assunto o trecho trata. Metadados: `section`, `title`, `parent`.
5. **Embeddings:** Gemini `gemini-embedding-001` (`GoogleGenerativeAIEmbeddings`) com dimensão **768**. A biblioteca já usa `RETRIEVAL_DOCUMENT` ao indexar e `RETRIEVAL_QUERY` ao buscar.
6. **Armazenamento:** `PGVector` do `langchain-postgres`, busca exata por cosseno, top-3 por padrão, **sem índice vetorial**. O `PGVector` não tem opção de schema; as tabelas dele vão para o schema `rag` porque a conexão é aberta com `search_path=rag,public`.
7. **Permissões:** a indexação roda como dono do banco; a busca roda como `agent_ro`, que só tem `SELECT` (concedido por `ALTER DEFAULT PRIVILEGES` em `db/rag.sql`).
8. **Testabilidade:** os embeddings entram por parâmetro (`index_policies(embeddings=...)`), o que permitiu validar o fluxo inteiro com embeddings falsos, sem chamar a API.
9. **Avaliação:** `tests/test_policies.py` testa o chunking offline (7 testes). `tests/test_retrieval.py` mede recall@3 em 16 perguntas de clientes, cada uma com as seções aceitáveis.

## Alternativas consideradas

- **Chunking escrito à mão (regex sobre texto do `pypdf`):** foi a primeira versão (cerca de 150 linhas e 6 testes), e foi **descartada**. Reimplementava o que o `MarkdownHeaderTextSplitter` já faz, e era mais frágil: apresentou dois bugs (seções perdidas e listas numeradas lidas como tabela) que o pipeline atual não tem. A versão com LangChain cobre os mesmos testes com cerca de 80 linhas.
- **`RecursiveCharacterTextSplitter` por tamanho fixo:** simples, mas corta regras ao meio ("7 dias" num chunk, "sem justificativa" em outro) e mistura assuntos. O manual já é estruturado, então aproveitamos isso.
- **SQL direto com `pgvector` (segunda versão):** foi adotada por engano, alegando que o `PGVector` não aceita schema. Dá para resolver com `search_path`, então voltamos ao componente padrão, que também entrega `as_retriever()` para a Etapa 4.
- **`PyPDFLoader` / `langchain-community`:** exige o pacote `langchain-community` e uma dezena de dependências sem trazer títulos estruturados.
- **Manual inteiro no prompt:** cabe no contexto de 1M, mas aumenta custo e latência a cada mensagem e dilui a atenção do modelo. O retrieval também é parte do que o desafio quer avaliar.
- **Vector DB dedicado (Chroma, Qdrant):** sem ganho para 25 chunks (ver ADR-001).
- **Dimensão 3072 (padrão do modelo):** o pgvector não indexa vetores com mais de 2000 dimensões, e 768 mantém boa qualidade com menos armazenamento.
- **Índice aproximado (HNSW/IVFFlat):** para 25 linhas a busca exata é instantânea e 100% precisa.

## Consequências

- **Positivas:** menos código próprio e mais padrão de mercado; cada regra é recuperada inteira e com contexto; a busca devolve seção e score, o que permite citar a fonte; o agente nunca consegue alterar o índice.
- **Negativas / riscos:**
  - A limpeza depende do formato atual do PDF (numeração `N.` e `N.M` e o texto do cabeçalho repetido). Mudando o PDF, os testes de `test_policies.py` denunciam a quebra.
  - O `pymupdf4llm` traz o `pymupdf_layout` (com `onnxruntime`), uma dependência mais pesada do que `pypdf`.
  - O `PGVector` depende de um detalhe (`search_path`) para respeitar o schema, e cria as próprias tabelas (`langchain_pg_*`), sem controle fino do DDL.
  - Perguntas que cruzam seções (por exemplo, "posso devolver um produto em promoção?", que toca em 4.4 e 6.2) dependem de o top-3 trazer as duas. O prompt deve incentivar nova busca quando faltar informação.
  - A busca depende da API do Gemini (cota do tier gratuito e disponibilidade).
- **Quando revisitar:** se o manual crescer (aí usar HNSW), se o recall@3 ficar baixo (aí avaliar busca híbrida com texto) ou se a estrutura do PDF mudar.
