"""Qualidade da busca nas políticas (integração: precisa de Postgres no ar, do índice criado
com `python -m emporio_agent.rag index` e de uma GOOGLE_API_KEY real).

Métrica: recall@3, ou seja, a seção esperada aparece entre os 3 primeiros resultados.
"""

import os

import psycopg
import pytest

from emporio_agent.config import database_url
from emporio_agent.rag import search_policies

# pergunta do cliente -> seções aceitáveis
CASOS = [
    ("Qual o horário de funcionamento aos sábados?", {"2"}),
    ("A loja abre no domingo?", {"2"}),
    ("Me arrependi da compra online, posso devolver?", {"4.1"}),
    ("Meu violão chegou com defeito, o que eu faço?", {"4.2"}),
    ("Quero trocar por outra cor, é possível?", {"4.3"}),
    ("Quanto custa o frete para Campo Grande?", {"5.1"}),
    ("Vocês entregam em Dourados? Em quantos dias?", {"5.2"}),
    ("Como recebo o código de rastreamento?", {"5.3"}),
    ("Em quantas vezes posso parcelar no cartão?", {"3", "3.1"}),
    ("PIX tem desconto?", {"3", "6.2"}),
    ("Posso somar a promoção com o desconto do PIX?", {"6.2"}),
    ("Vocês vendem cordas e palhetas?", {"1", "7.1"}),
    ("Quanto tempo de garantia tem o produto?", {"8.1", "8.2"}),
    ("O que a garantia não cobre?", {"8.3"}),
    ("Como vocês usam meus dados pessoais?", {"9"}),
    ("Qual o endereço da loja?", {"1.2"}),
]


def _index_disponivel() -> bool:
    key = os.getenv("GOOGLE_API_KEY", "")
    if len(key) < 20:  # placeholder
        return False
    try:
        with psycopg.connect(database_url(read_only=True), connect_timeout=3) as conn:
            return conn.execute("SELECT count(*) FROM rag.langchain_pg_embedding").fetchone()[0] > 0
    except psycopg.Error:
        return False


pytestmark = pytest.mark.skipif(not _index_disponivel(), reason="índice RAG ou GOOGLE_API_KEY indisponível")


@pytest.mark.parametrize("pergunta,aceitas", CASOS)
def test_recall_at_3(pergunta, aceitas):
    secoes = [r["section"] for r in search_policies(pergunta, k=3)]
    assert aceitas & set(secoes), f"esperava {aceitas} em {secoes}"
