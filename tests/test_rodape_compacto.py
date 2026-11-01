"""Rodapé compacto: nome da loja e links em linha única, sem colunas nem títulos (SPEC, pedido do Rodrigo)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from emporio.web.app import criar_app

LINKS = {"/perguntas-frequentes": "Perguntas frequentes", "/politicas": "Políticas da Loja",
         "/privacidade": "Privacidade e cookies"}
FORA_DO_RODAPE = ("/catalogo", "/rastreio", "/creditos")


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def rodape(html):
    return html[html.index('<footer class="rodape">'):html.index("</footer>")]


def test_sem_titulos_de_coluna_e_com_os_tres_links(cliente):
    r = rodape(cliente.get("/").text)
    assert "<h2" not in r and "Comprar" not in r and "Informações" not in r
    assert dict(re.findall(r'<a href="([^"]+)">([^<]+)</a>', r)) == LINKS
    for fora in FORA_DO_RODAPE:  # Rastrear pedido, Créditos das imagens e Catálogo saem do rodapé
        assert f'href="{fora}"' not in r


@pytest.mark.parametrize("caminho", list(LINKS) + list(FORA_DO_RODAPE))
def test_cada_link_do_rodape_funciona(cliente, caminho):
    assert cliente.get(caminho).status_code == 200


def test_rodape_traz_onde_estamos_sem_horario_e_sem_contatos(cliente):
    from emporio.politicas.manual import fato

    r = rodape(cliente.get("/").text)
    e = fato("empresa.endereco").valor
    assert "Onde estamos" in r and e["logradouro"] in r and e["cep"] in r
    assert "Horário de atendimento" not in r and "Seg. a sex." not in r and "rodape-horas" not in r  # horário saiu do rodapé
    for chave in ("contato.telefone_capa", "contato.email_capa", "contato.telefone_whatsapp_dados_empresa"):
        assert str(fato(chave).valor) not in r


def test_fale_conosco_cards_com_horario_e_sem_endereco(cliente):
    html = cliente.get("/fale-conosco").text
    corpo = html[:html.index('<footer class="rodape">')]
    assert corpo.count("bloco-nota") >= 2 and "Horário de atendimento" in corpo and "seguem o horário da loja" in corpo
    assert 'href="/rastreio"' in corpo


# ---- etapa 14: cabeçalho, aviso do produto, título e horário ---------------------------------------------------------

def test_catalogo_no_cabecalho_ao_lado_de_categorias(cliente):
    html = cliente.get("/").text
    topo = html[html.index('<header class="topo">'):html.index("</header>")]
    assert '<a href="/catalogo">Catálogo</a>' in topo and "Categorias" in topo


def test_aviso_imagem_ilustrativa_do_produto_leva_a_creditos(cliente):
    html = cliente.get("/produto/90").text
    assert 'href="/creditos">Imagem ilustrativa</a>' in html
    assert cliente.get("/creditos").status_code == 200


def test_titulo_politicas_da_loja(cliente):
    html = cliente.get("/politicas").text
    assert "<title>Políticas da Loja | " in html and "<h1>Políticas da Loja</h1>" in html


def test_horario_sem_domingo_na_faixa_e_no_fale_conosco(cliente):
    for caminho in ("/", "/fale-conosco"):
        html = cliente.get(caminho).text
        corpo = html[:html.index("<footer")]
        assert "Dom." not in corpo and "Dom," not in corpo
        assert "Seg. a sex., das 9h às 18h" in corpo
    home = cliente.get("/").text
    faixa = home[home.index('faixa-contato" aria-label'):home.index("<footer")]
    assert "Dom" not in faixa
