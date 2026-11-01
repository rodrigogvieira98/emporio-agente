"""Navegação sem duplicidade (SPEC, etapa 18): cada destino aparece uma vez entre cabeçalho e rodapé."""
from __future__ import annotations

import re
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from emporio.web.app import criar_app


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def trecho(html, ini, fim):
    i = html.index(ini)
    return html[i:html.index(fim, i)]


def hrefs(bloco):
    return re.findall(r'<a [^>]*href="([^"#][^"]*)"', bloco)


@pytest.mark.parametrize("caminho", ["/", "/catalogo", "/rastreio", "/carrinho", "/politicas"])
def test_cada_destino_aparece_uma_vez_entre_cabecalho_e_rodape(cliente, caminho):
    html = cliente.get(caminho).text
    destinos = hrefs(trecho(html, "<header", "</header>")) + hrefs(trecho(html, '<footer class="rodape">', "</footer>"))
    destinos = [d for d in destinos if not d.startswith(("tel:", "mailto:", "http"))]
    repetidos = {d: n for d, n in Counter(d.split("?")[0] for d in destinos if "categoria=" not in d).items() if n > 1}
    # a marca aponta para "/" e é o único destino fora da lista de itens; o cabeçalho não repete o rodapé
    assert not {d: n for d, n in repetidos.items() if d != "/"}, repetidos


def test_cabecalho_sem_perguntas_frequentes_e_sem_todos_os_instrumentos(cliente):
    cab = trecho(cliente.get("/").text, "<header", "</header>")
    assert "/perguntas-frequentes" not in cab and "Todos os instrumentos" not in cab
    assert [h for h in hrefs(cab) if h.startswith("/catalogo")].count("/catalogo") == 1


def test_perguntas_frequentes_alcancavel_pelo_rodape(cliente):
    rod = trecho(cliente.get("/").text, '<footer class="rodape">', "</footer>")
    assert 'href="/perguntas-frequentes"' in rod and cliente.get("/perguntas-frequentes").status_code == 200


def test_botao_rastrear_da_faixa_de_contato_permanece(cliente):
    faixa = trecho(cliente.get("/").text, 'aria-label="Fale conosco"', "</section>")
    assert 'class="botao" href="/rastreio"' in faixa


def test_contagem_do_carrinho_segue_como_selo(cliente):
    assert 'class="contagem-carrinho"' not in cliente.get("/").text  # vazio: sem selo
    css = open("src/emporio/web/static/site.css", encoding="utf-8").read()
    assert ".contagem-carrinho" in css
