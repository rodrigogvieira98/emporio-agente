"""Rodapé compacto: nome da loja e links em linha única, sem colunas nem títulos (SPEC, pedido do Rodrigo)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from emporio.web.app import criar_app

LINKS = {"/catalogo": "Catálogo", "/perguntas-frequentes": "Perguntas frequentes", "/politicas": "Políticas",
         "/rastreio": "Rastrear pedido", "/privacidade": "Privacidade e cookies", "/creditos": "Créditos das imagens"}


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def rodape(html):
    return html[html.index('<footer class="rodape">'):html.index("</footer>")]


def test_sem_titulos_de_coluna_e_com_os_seis_links(cliente):
    r = rodape(cliente.get("/").text)
    assert "<h2" not in r and "Comprar" not in r and "Informações" not in r
    assert dict(re.findall(r'<a href="([^"]+)">([^<]+)</a>', r)) == LINKS


@pytest.mark.parametrize("caminho", list(LINKS))
def test_cada_link_do_rodape_funciona(cliente, caminho):
    assert cliente.get(caminho).status_code == 200


def test_rodape_traz_onde_estamos_e_horario_do_manual_sem_contatos(cliente):
    from emporio.politicas.manual import fato

    r = rodape(cliente.get("/").text)
    e = fato("empresa.endereco").valor
    assert "Onde estamos" in r and e["logradouro"] in r and e["cep"] in r and "Horário de atendimento" in r
    assert "Seg. a sex., das 9h às 18h" in r
    for chave in ("contato.telefone_capa", "contato.email_capa", "contato.telefone_whatsapp_dados_empresa"):
        assert str(fato(chave).valor) not in r


def test_fale_conosco_cards_com_horario_e_sem_endereco(cliente):
    html = cliente.get("/fale-conosco").text
    corpo = html[:html.index('<footer class="rodape">')]
    assert corpo.count("bloco-nota") >= 2 and "Horário de atendimento" in corpo and "seguem o horário da loja" in corpo
    assert 'href="/rastreio"' in corpo
