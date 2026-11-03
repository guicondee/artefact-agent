"""Testes das tools do agente (integração: precisa de Postgres e do schema shop carregado)."""

import os

import psycopg
import pytest

from emporio_agent.config import database_url


def _banco_disponivel() -> bool:
    try:
        with psycopg.connect(database_url(read_only=True), connect_timeout=3) as conn:
            return conn.execute("SELECT count(*) FROM shop.v_catalog").fetchone()[0] > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _banco_disponivel(), reason="Banco shop indisponível")


# --------------------------------------------------------------------------- #
#  consultar_catalogo
# --------------------------------------------------------------------------- #

from emporio_agent.tools import consultar_catalogo


class TestConsultarCatalogo:
    def test_busca_takamine(self):
        result = consultar_catalogo.invoke(
            {"sql": "SELECT name, list_price_brl FROM shop.v_catalog WHERE name ILIKE '%Takamine GD20%'"}
        )
        assert "Takamine GD20" in result
        assert "2199" in result

    def test_violoes_ate_1000(self):
        result = consultar_catalogo.invoke(
            {"sql": "SELECT name, list_price_brl FROM shop.v_catalog WHERE category = 'Violões' AND list_price_brl <= 1000 AND availability = 'in_stock' ORDER BY list_price_brl"}
        )
        assert "Tagima" in result or "Yamaha" in result

    def test_produtos_em_promocao(self):
        result = consultar_catalogo.invoke(
            {"sql": "SELECT name, promo_name FROM shop.v_catalog WHERE promo_price_brl IS NOT NULL"}
        )
        assert "Oferta Especial" in result or "Desconto Exclusivo" in result

    def test_bloqueia_drop(self):
        result = consultar_catalogo.invoke({"sql": "DROP TABLE shop.products"})
        assert "Erro" in result

    def test_bloqueia_update(self):
        result = consultar_catalogo.invoke({"sql": "UPDATE shop.products SET price_brl = 1"})
        assert "Erro" in result

    def test_bloqueia_multi_statement(self):
        result = consultar_catalogo.invoke({"sql": "SELECT 1; DROP TABLE shop.products"})
        assert "Erro" in result

    def test_bloqueia_tabela_base(self):
        result = consultar_catalogo.invoke({"sql": "SELECT * FROM shop.customers"})
        assert "Erro" in result or "permission denied" in result.lower()

    def test_limit_automatico(self):
        result = consultar_catalogo.invoke({"sql": "SELECT name FROM shop.v_catalog ORDER BY name"})
        assert result.count("\n") <= 20  # LIMIT 20 injetado


# --------------------------------------------------------------------------- #
#  consultar_pedido
# --------------------------------------------------------------------------- #

from emporio_agent.tools import consultar_pedido


class TestConsultarPedido:
    def test_pedido_com_telefone_correto(self):
        result = consultar_pedido.invoke({"order_id": 1, "phone": "(67) 98432-1098"})
        assert "Pedido #1" in result
        assert "delivered" in result

    def test_pedido_com_email_correto(self):
        result = consultar_pedido.invoke({"order_id": 1, "email": "pedro.oliveira@jmail.com"})
        assert "Pedido #1" in result

    def test_rejeita_pedido_sem_contato(self):
        result = consultar_pedido.invoke({"order_id": 1})
        assert "telefone ou e-mail" in result.lower()

    def test_rejeita_pedido_com_contato_errado(self):
        result = consultar_pedido.invoke({"order_id": 1, "phone": "(11) 99999-0000"})
        assert "Não encontrei" in result

    def test_pedido_com_rastreamento(self):
        result = consultar_pedido.invoke({"order_id": 1, "phone": "(67) 98432-1098"})
        assert "BRAB1234567BR" in result

    def test_pedido_cancelado_mostra_notas(self):
        # Pedido 17, cliente 15 (Matheus Ramos Correia)
        result = consultar_pedido.invoke({"order_id": 17, "phone": "(67) 98109-8765"})
        assert "cancelled" in result.lower()


# --------------------------------------------------------------------------- #
#  consultar_horario
# --------------------------------------------------------------------------- #

from emporio_agent.tools import consultar_horario


class TestConsultarHorario:
    def test_retorna_data_e_status(self):
        result = consultar_horario.invoke({})
        assert "Agora:" in result
        assert "ABERTA" in result or "FECHADA" in result
        assert "Campo_Grande" in result
