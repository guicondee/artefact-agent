"""RAG das políticas: indexação (PDF -> embeddings -> pgvector) e busca por similaridade.

Usa o PGVector do LangChain. As tabelas ficam no schema "rag" porque a conexão é aberta com
`search_path=rag,public` (o PGVector não tem opção de schema, ele usa o primeiro do search_path).

Uso (na raiz do projeto):
    python -m emporio_agent.rag index
    python -m emporio_agent.rag search "posso devolver meu pedido?" -k 3
"""

import argparse

import psycopg
from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector

from emporio_agent.config import (
    DB_DIR,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    database_url,
    require_env,
)
from emporio_agent.policies import load_policy_chunks

COLLECTION = "politicas"

# Cache: o PGVector registra tabelas no metadata do SQLAlchemy. Se instanciado mais de uma
# vez no mesmo processo, o SQLAlchemy levanta InvalidRequestError. A solução é criar uma
# única instância por (embeddings, read_only) e reutilizar.
_store_cache: dict[tuple[int, bool], PGVector] = {}


def default_embeddings() -> Embeddings:
    # O LangChain usa RETRIEVAL_DOCUMENT ao indexar e RETRIEVAL_QUERY ao buscar.
    return GoogleGenerativeAIEmbeddings(
        model=f"models/{EMBEDDING_MODEL}",
        google_api_key=require_env("GOOGLE_API_KEY"),
        output_dimensionality=EMBEDDING_DIM,
    )


def get_store(embeddings: Embeddings, read_only: bool = False) -> PGVector:
    """Vector store das políticas. `read_only=True` conecta como agent_ro.

    O store é criado uma vez e reutilizado no mesmo processo para evitar conflitos de
    metadados do SQLAlchemy.
    """
    key = (id(embeddings), read_only)
    if key not in _store_cache:
        _store_cache[key] = PGVector(
            embeddings=embeddings,
            collection_name=COLLECTION,
            connection=database_url(read_only).replace("postgresql://", "postgresql+psycopg://"),
            embedding_length=EMBEDDING_DIM,
            create_extension=False,
            engine_args={"connect_args": {"options": "-csearch_path=rag,public"}},
        )
    return _store_cache[key]


def index_policies(embeddings: Embeddings | None = None) -> int:
    """Recria o schema rag e indexa todos os chunks do manual."""
    _store_cache.clear()  # o schema é recriado, então qualquer store anterior é inválido
    chunks = load_policy_chunks()
    with psycopg.connect(database_url()) as conn:
        conn.execute((DB_DIR / "rag.sql").read_text(encoding="utf-8"))
    store = get_store(embeddings or default_embeddings())
    store.add_documents(chunks)
    return len(chunks)


def search_policies(query: str, k: int = 3, embeddings: Embeddings | None = None) -> list[dict]:
    """Retorna os k trechos do manual mais parecidos com a pergunta (maior `score` = mais similar).

    Conecta como agent_ro (somente leitura). A similaridade é por cosseno: score = 1 - distância.
    """
    store = get_store(embeddings or default_embeddings(), read_only=True)
    results = store.similarity_search_with_score(query, k=k)
    return [
        {
            "section": doc.metadata["section"],
            "title": doc.metadata["title"],
            "content": doc.page_content,
            "score": 1 - distance,
        }
        for doc, distance in results
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="indexa o manual de políticas")
    search = sub.add_parser("search", help="busca trechos do manual")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=3)
    args = parser.parse_args()

    if args.command == "index":
        print(f"OK: {index_policies()} chunks indexados no schema rag")
    else:
        for r in search_policies(args.query, args.k):
            print(f"[{r['score']:.3f}] seção {r['section']} - {r['title']}")


if __name__ == "__main__":
    main()
