"""Memória: o histórico de uma thread sobrevive a fechar e reabrir o checkpointer.

Integração: precisa do Postgres no ar (`docker compose up -d`). Não chama o LLM.
"""

import uuid
from typing import Annotated

import psycopg
import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from emporio_agent.__main__ import resolve_thread_id
from emporio_agent.config import database_url
from emporio_agent.memory import open_checkpointer


def test_resolve_thread_id():
    assert resolve_thread_id(nova=False, thread="abc", saved="salvo") == "abc"
    assert resolve_thread_id(nova=False, thread=None, saved="salvo") == "salvo"
    novo = resolve_thread_id(nova=True, thread=None, saved="salvo")
    assert novo != "salvo"
    assert resolve_thread_id(nova=False, thread=None, saved=None) != ""


def test_resolve_thread_id_rejeita_flags_juntos():
    with pytest.raises(SystemExit):
        resolve_thread_id(nova=True, thread="abc", saved=None)


def _banco_disponivel() -> bool:
    try:
        with psycopg.connect(database_url(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


_precisa_banco = pytest.mark.skipif(not _banco_disponivel(), reason="Postgres indisponível")


class State(TypedDict):
    messages: Annotated[list, add_messages]


def _eco(state: State):
    return {"messages": [("ai", f"eco: {state['messages'][-1].content}")]}


def _grafo(checkpointer):
    builder = StateGraph(State)
    builder.add_node("eco", _eco)
    builder.add_edge(START, "eco")
    return builder.compile(checkpointer=checkpointer)


def _apagar(thread_id: str) -> None:
    with psycopg.connect(database_url()) as conn:
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            conn.execute(f"DELETE FROM memory.{table} WHERE thread_id = %s", (thread_id,))


@_precisa_banco
def test_historico_sobrevive_a_reabrir_a_conexao():
    thread_id = f"test-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        with open_checkpointer() as saver:
            graph = _grafo(saver)
            graph.invoke({"messages": [HumanMessage(content="primeira")]}, config)
            graph.invoke({"messages": [HumanMessage(content="segunda")]}, config)

        with open_checkpointer() as saver:
            graph = _grafo(saver)
            state = graph.get_state(config)
            schema = saver.conn.execute(
                """
                SELECT table_schema FROM information_schema.tables
                WHERE table_name = 'checkpoints'
                """
            ).fetchall()

        assert [m.content for m in state.values["messages"]] == [
            "primeira",
            "eco: primeira",
            "segunda",
            "eco: segunda",
        ]
        assert any(row["table_schema"] == "memory" for row in schema)
    finally:
        _apagar(thread_id)


@_precisa_banco
def test_agent_ro_nao_le_memoria():
    with psycopg.connect(database_url()) as conn:
        role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'agent_ro'").fetchone()
    if role is None:
        pytest.skip("role agent_ro ainda não existe")

    with open_checkpointer():
        pass

    with psycopg.connect(database_url(read_only=True)) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT 1 FROM memory.checkpoints LIMIT 1")
