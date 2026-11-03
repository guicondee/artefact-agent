"""Testes do chunking do manual de políticas (offline: só lê o PDF)."""

import re

import pytest

from emporio_agent.policies import load_policy_chunks


@pytest.fixture(scope="module")
def chunks():
    return load_policy_chunks()


@pytest.fixture(scope="module")
def by_section(chunks):
    return {c.metadata["section"]: c for c in chunks}


def test_todas_as_secoes_com_conteudo_foram_extraidas(by_section):
    esperadas = {
        "1", "1.1", "1.2", "2", "3", "3.1", "4", "4.1", "4.2", "4.3", "4.4",
        "5.1", "5.2", "5.3", "6.1", "6.2", "7", "7.1", "7.2", "7.3",
        "8.1", "8.2", "8.3", "9", "10",
    }
    assert set(by_section) == esperadas


def test_capa_e_secoes_sem_conteudo_proprio_nao_geram_chunk(by_section):
    # "5. Frete" e "8. Garantia" só têm subseções. A capa vem antes da seção 1.
    assert "5" not in by_section and "8" not in by_section
    assert not any("EMPÓRIO DA MÚSICA" in c.page_content for c in by_section.values())


def test_regras_de_negocio_chave_estao_no_chunk_certo(by_section):
    def texto(secao: str) -> str:
        return by_section[secao].page_content

    assert "7 (sete) dias corridos" in texto("4.1")
    assert "30 (trinta) dias" in texto("4.2")
    assert "09:00 às 18:00" in texto("2") and "09:00 às 13:00" in texto("2")
    assert "R$ 35,00" in texto("5.1")
    assert "90 (noventa) dias" in texto("8.1")
    assert "BR4K7M2X9P1BR" in texto("5.3")
    assert "não se aplica sobre preços já promocionais" in texto("6.2")
    assert "Rua 14 de Maio, 3200" in texto("1.2")


def test_metadados_de_titulo_e_secao_pai(by_section):
    assert by_section["6.2"].metadata["title"] == "Regras de Promoções"
    assert by_section["6.2"].metadata["parent"] == "Promoções e Descontos"
    assert by_section["2"].metadata["parent"] is None  # seção sem subseções


def test_chunk_comeca_com_cabecalho_contextual(by_section):
    assert by_section["4.1"].page_content.startswith(
        'Manual de Políticas, seção 4.1: Direito de Arrependimento (Compras Online) (em "Política de Trocas e Devoluções")\n'
    )


def test_lista_numerada_do_fluxo_de_atendimento_nao_vira_secao(by_section):
    corpo = by_section["7.2"].page_content
    assert len(re.findall(r"^\d\. ", corpo, flags=re.MULTILINE)) == 5


def test_sem_ruido_de_cabecalho_ou_rodape(chunks):
    for chunk in chunks:
        assert "Manual de Políticas e Procedimentos" not in chunk.page_content
        assert not re.search(r"^Página \d+$", chunk.page_content, flags=re.MULTILINE)
        assert "-----" not in chunk.page_content
