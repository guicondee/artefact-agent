"""Smoke tests da Etapa 0.

Uso:
    uv run python scripts/smoke_test.py db
    uv run python scripts/smoke_test.py embeddings
    uv run python scripts/smoke_test.py llm
    uv run python scripts/smoke_test.py thinking     # compara thinking on/off
    uv run python scripts/smoke_test.py all
"""

import statistics
import sys
import time

import psycopg
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from emporio_agent.config import load_settings


# --------------------------------------------------------------------------- #
# 1) Banco
# --------------------------------------------------------------------------- #
def test_db() -> None:
    s = load_settings()
    with psycopg.connect(s.pg_dsn, connect_timeout=5) as conn:
        version = conn.execute("select version()").fetchone()[0]
        ext = conn.execute("select extversion from pg_extension where extname = 'vector'").fetchone()
        assert ext, "extensão pgvector NÃO instalada"
        dist = conn.execute("select '[1,2,3]'::vector <=> '[1,2,4]'::vector").fetchone()[0]
    print(f"[db] OK  {version.split(',')[0]} | pgvector {ext[0]} | distância cosseno de teste = {dist:.6f}")


# --------------------------------------------------------------------------- #
# 2) Embeddings
# --------------------------------------------------------------------------- #
def test_embeddings() -> None:
    s = load_settings()
    emb = GoogleGenerativeAIEmbeddings(model=f"models/{s.embedding_model}", google_api_key=s.google_api_key)
    vec = emb.embed_query("Qual o horário de funcionamento da loja?")
    print(f"[embeddings] OK  modelo={s.embedding_model} | dimensões={len(vec)}")


# --------------------------------------------------------------------------- #
# 3) LLM com tool calling
# --------------------------------------------------------------------------- #
@tool
def consultar_preco(produto: str) -> str:
    """Consulta o preço atual de um instrumento musical pelo nome."""
    return f"O preço de '{produto}' é R$ 1.999,00 (em estoque)."


@tool
def consultar_politica(assunto: str) -> str:
    """Consulta as políticas da loja (horário, trocas, frete, pagamento, garantia)."""
    return f"Política sobre '{assunto}': troca em até 7 dias corridos, produto na embalagem original."


TOOLS = [consultar_preco, consultar_politica]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def make_llm(thinking: str) -> ChatDeepSeek:
    s = load_settings()
    return ChatDeepSeek(
        model=s.deepseek_model,
        api_key=s.deepseek_api_key,
        extra_body={"thinking": {"type": thinking}},
        max_retries=1,
        timeout=120,
    )


def run_tool_loop(llm, question: str, max_steps: int = 4) -> dict:
    """Executa o ciclo completo: pergunta -> tool call -> ToolMessage -> resposta final."""
    llm_tools = llm.bind_tools(TOOLS)
    messages = [HumanMessage(question)]
    tools_called: list[str] = []
    tokens = 0
    t0 = time.perf_counter()
    for _ in range(max_steps):
        ai = llm_tools.invoke(messages)
        tokens += (ai.usage_metadata or {}).get("total_tokens", 0)
        messages.append(ai)
        if not ai.tool_calls:
            break
        for call in ai.tool_calls:
            tools_called.append(call["name"])
            result = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
    latency = time.perf_counter() - t0
    return {
        "tools": tools_called,
        "answer": messages[-1].content,
        "latency": latency,
        "tokens": tokens,
        "has_reasoning": "reasoning_content" in messages[1].additional_kwargs if len(messages) > 1 else False,
    }


def test_llm() -> None:
    s = load_settings()
    out = run_tool_loop(make_llm(s.deepseek_thinking), "Quanto custa o violão Takamine GD20?")
    print(f"[llm] OK  modelo={s.deepseek_model} thinking={s.deepseek_thinking}")
    print(f"      tools chamadas: {out['tools']} | latência {out['latency']:.1f}s | tokens {out['tokens']}")
    print(f"      resposta: {out['answer'][:200]}")


# --------------------------------------------------------------------------- #
# 4) Comparação thinking on/off
# --------------------------------------------------------------------------- #
CASES = [
    ("Quanto custa o violão Takamine GD20?", "consultar_preco"),
    ("Qual o preço da guitarra Squier Stratocaster?", "consultar_preco"),
    ("Me arrependi da compra, posso devolver?", "consultar_politica"),
    ("Como funciona o frete para Dourados?", "consultar_politica"),
    ("Posso parcelar em 12x no cartão?", "consultar_politica"),
]


def test_thinking() -> None:
    print("[thinking] comparando enabled vs disabled (5 casos, ciclo completo de tools)\n")
    summary = {}
    for mode in ("disabled", "enabled"):
        llm = make_llm(mode)
        rows = []
        for question, expected in CASES:
            try:
                out = run_tool_loop(llm, question)
                ok = expected in out["tools"]
                err = ""
            except Exception as exc:  # o ponto aqui é justamente descobrir se quebra
                out, ok, err = {"latency": 0, "tokens": 0, "tools": []}, False, f"{type(exc).__name__}: {exc}"[:160]
            rows.append((question, ok, out["latency"], out["tokens"], err))
            flag = "OK " if ok else "ERR"
            print(f"  [{mode:8}] {flag} {out['latency']:5.1f}s {out['tokens']:5} tok | {question}")
            if err:
                print(f"             {err}")
        summary[mode] = rows
        print()
    print("Resumo:")
    for mode, rows in summary.items():
        acertos = sum(r[1] for r in rows)
        lat = statistics.mean(r[2] for r in rows)
        tok = statistics.mean(r[3] for r in rows)
        print(f"  {mode:8} acertos {acertos}/{len(rows)} | latência média {lat:.1f}s | tokens médios {tok:.0f}")


COMMANDS = {"db": test_db, "embeddings": test_embeddings, "llm": test_llm, "thinking": test_thinking}


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "all":
        for fn in (test_db, test_embeddings, test_llm):
            fn()
    elif arg in COMMANDS:
        COMMANDS[arg]()
    else:
        sys.exit(__doc__)
