"""A CLI imprime a resposta token a token e deixa de fora as tools."""

from langchain_core.messages import AIMessageChunk

from emporio_agent.__main__ import imprimir_resposta, texto_do_token


def test_texto_do_token_ignora_bloco_que_nao_e_texto():
    token = AIMessageChunk(content=[{"type": "text", "text": "Olá"}, {"type": "tool_use", "text": "sql"}])
    assert texto_do_token(token) == "Olá"


def test_imprime_token_a_token_e_separar_fala_depois_da_tool(capsys):
    eventos = [
        (AIMessageChunk(content="Vou "), {"langgraph_node": "agent"}),
        (AIMessageChunk(content="consultar."), {"langgraph_node": "agent"}),
        (
            AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "consultar_catalogo", "args": "", "id": "1", "index": 0}],
            ),
            {"langgraph_node": "agent"},
        ),
        (AIMessageChunk(content="linha do banco"), {"langgraph_node": "tools"}),
        (AIMessageChunk(content="O "), {"langgraph_node": "agent"}),
        (AIMessageChunk(content="preço é 10."), {"langgraph_node": "agent"}),
    ]

    imprimir_resposta(eventos)

    assert capsys.readouterr().out == "\n🎵 Empório: Vou consultar.\n\n🎵 Empório: O preço é 10.\n"


def test_so_tool_nao_imprime_nada(capsys):
    eventos = [
        (
            AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "consultar_horario", "args": "", "id": "1", "index": 0}],
            ),
            {"langgraph_node": "agent"},
        )
    ]

    imprimir_resposta(eventos)

    assert capsys.readouterr().out == ""
