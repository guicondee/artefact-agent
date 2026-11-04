"""CLI do agente de atendimento da Empório da Música.

Uso:
    python -m emporio_agent                 # retoma a última conversa
    python -m emporio_agent --nova          # começa uma conversa nova
    python -m emporio_agent --thread ID     # retoma uma conversa específica

Dentro da conversa:
    /nova   começa outra conversa (a anterior continua salva no banco)
    sair    encerra
"""

import argparse
import uuid

from langchain_core.messages import HumanMessage

from emporio_agent.agent import build_agent
from emporio_agent.config import ROOT
from emporio_agent.memory import open_checkpointer

SESSION_FILE = ROOT / ".emporio_thread"


def _read_session() -> str | None:
    if not SESSION_FILE.exists():
        return None
    value = SESSION_FILE.read_text(encoding="utf-8").strip()
    return value or None


def _write_session(thread_id: str) -> None:
    SESSION_FILE.write_text(thread_id + "\n", encoding="utf-8")


def resolve_thread_id(*, nova: bool, thread: str | None, saved: str | None) -> str:
    """Escolhe o id da conversa. `--thread` e `--nova` não podem vir juntos."""
    if thread and nova:
        raise SystemExit("Use apenas um: --thread ou --nova.")
    if thread:
        return thread
    if nova or not saved:
        return str(uuid.uuid4())
    return saved


def texto_do_token(token) -> str:
    """Texto visível de um token. Não inclui argumentos de tool nem o raciocínio interno."""
    content = getattr(token, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        partes = []
        for bloco in content:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(str(bloco.get("text", "")))
        return "".join(partes)
    return ""


def _tem_tool(token) -> bool:
    return bool(getattr(token, "tool_call_chunks", None) or getattr(token, "tool_calls", None))


def imprimir_resposta(eventos) -> None:
    """Imprime a fala do agente token a token, no mesmo ritmo do Studio.

    `eventos` é o stream `messages` do LangGraph: pares `(token, metadata)`.
    Tokens do nó de tools e os pedaços de tool call não entram no texto.
    """
    iniciou = False
    nova_fala = True
    for token, metadata in eventos:
        if metadata.get("langgraph_node") != "agent":
            if iniciou:
                nova_fala = True
            continue
        texto = texto_do_token(token)
        if texto:
            if nova_fala:
                if iniciou:
                    print()
                print("\n🎵 Empório: ", end="", flush=True)
                iniciou = True
                nova_fala = False
            print(texto, end="", flush=True)
        if _tem_tool(token) and iniciou:
            nova_fala = True
    if iniciou:
        print()


def _chat(agent, thread_id: str) -> None:
    print("=" * 60)
    print("  Empório da Música — Assistente Virtual")
    print(f"  Conversa: {thread_id}")
    print("  /nova começa outra. sair encerra.")
    print("=" * 60)
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            user_input = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté mais! 🎵")
            break

        if not user_input:
            continue
        if user_input.lower() in ("sair", "exit", "quit"):
            print("\nFoi um prazer atender você! Até a próxima! 🎶")
            break
        if user_input.lower() == "/nova":
            thread_id = str(uuid.uuid4())
            _write_session(thread_id)
            config = {"configurable": {"thread_id": thread_id}}
            print(f"\nNova conversa: {thread_id}")
            continue

        imprimir_resposta(
            agent.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                stream_mode="messages",
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Assistente da Empório da Música")
    parser.add_argument("--nova", action="store_true", help="Começa uma conversa nova")
    parser.add_argument("--thread", help="Retoma a conversa com este id")
    args = parser.parse_args()

    thread_id = resolve_thread_id(nova=args.nova, thread=args.thread, saved=_read_session())
    _write_session(thread_id)

    with open_checkpointer() as checkpointer:
        _chat(build_agent(checkpointer), thread_id)


if __name__ == "__main__":
    main()
