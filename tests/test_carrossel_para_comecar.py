"""Secao "Para comecar" da home como carrossel, independente do carrossel de destaques."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from emporio.web.app import criar_app


@pytest.fixture
def home(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        return c.get("/").text


def secao(html: str, ident: str) -> str:
    i = html.index(f'id="{ident}"')
    return html[i:html.index("</section>", i)]


def test_home_tem_dois_carrosseis_com_rotulos_proprios(home):
    assert home.count("data-carrossel") == 2
    d, m = secao(home, "destaques"), secao(home, "mais")
    assert 'aria-label="Produtos em destaque"' in d and 'aria-roledescription="carrossel"' in d
    assert 'aria-roledescription="carrossel"' in m and 'aria-label="Menores preços por categoria"' in m
    assert 'aria-label="Produtos em destaque"' not in m
    for trecho in ('aria-label="Instrumento anterior"', 'aria-label="Próximo instrumento"', "data-anuncio", 'aria-live="polite"'):
        assert trecho in m
    assert 'aria-label="Destaque anterior"' in d and 'aria-label="Destaque anterior"' not in m


def test_para_comecar_nao_e_mais_grade_e_mantem_o_link_ver_todos(home):
    m = secao(home, "mais")
    assert 'class="grade"' not in m and 'href="/catalogo">Ver todos os instrumentos</a>' in m


def test_cada_card_do_carrossel_leva_ao_produto_e_ha_um_ponto_por_produto(home):
    m = secao(home, "mais")
    itens = re.findall(r'<li class="carrossel-item" data-produto="(\d+)"', m)
    assert len(itens) >= 4 and len(set(itens)) == len(itens)
    for pid in itens:
        assert f'href="/produto/{pid}"' in m
    assert len(re.findall(r"data-ponto=", m)) == len(itens)


def test_produtos_do_para_comecar_nao_repetem_os_destaques(home):
    d = set(re.findall(r'data-produto="(\d+)"', secao(home, "destaques")))
    m = set(re.findall(r'data-produto="(\d+)"', secao(home, "mais")))
    assert d and m and not (d & m)


def test_anuncio_do_leitor_de_tela_usa_rotulo_da_propria_secao():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "src" / "emporio" / "web" / "static" / "vitrine.js").read_text(encoding="utf-8")
    assert "data-rotulo-anuncio" in js and "setInterval" not in js
