"""Histórico das conversas no schema `memory` do Postgres.

O `PostgresSaver` do LangGraph grava o estado de cada turno (mensagens, tool calls)
em tabelas com nome sem schema. A conexão usa `search_path=memory`, então essas
tabelas ficam nesse schema e não se misturam com `shop` nem com `rag`.

Cada conversa é uma thread (`thread_id`). Reiniciar a CLI com o mesmo id devolve
o histórico completo ao agente.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlencode

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from emporio_agent.config import DB_DIR, database_url

MEMORY_SCHEMA = "memory"


def memory_conninfo() -> str:
    """DSN do dono do banco, com as tabelas de checkpoint resolvidas no schema memory."""
    options = f"-csearch_path={MEMORY_SCHEMA},public"
    return f"{database_url()}?{urlencode({'options': options})}"


def ensure_memory_schema() -> None:
    """Cria o schema se ainda não existir. Não apaga conversas já gravadas."""
    with psycopg.connect(database_url()) as conn:
        conn.execute((DB_DIR / "memory.sql").read_text(encoding="utf-8"))


@contextmanager
def open_checkpointer() -> Iterator[PostgresSaver]:
    """Abre o PostgresSaver e cria as tabelas na primeira vez (`setup` é idempotente)."""
    ensure_memory_schema()
    with PostgresSaver.from_conn_string(memory_conninfo()) as saver:
        saver.setup()
        yield saver
