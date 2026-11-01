"""Correções do QA de cliques: contraste do Fechar, categoria da Lia, frete com CEP inválido, URL do checkout,
tabelas focáveis, confirmação do pedido e botão da Lia no celular."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio.web.app import criar_app

WEB = Path(__file__).resolve().parents[1] / "src" / "emporio" / "web"
CSS = (WEB / "static" / "site.css").read_text(encoding="utf-8")
CRAFTER = 90


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def _regra(seletor: str) -> str:
    achados = re.findall(r"(?m)^" + re.escape(seletor) + r"\s*\{([^}]*)\}", CSS)
    assert achados, seletor
    return " ".join(achados)


# 1. Sem botão Fechar: a Lia fecha por clique fora e Esc (gerenciador único), ou no botão da Lia

def test_chat_nao_tem_botao_fechar_e_fecha_por_clique_fora_e_esc(cliente):
    assert "chat-fechar" not in cliente.get("/").text and "chat-fechar" not in CSS
    js = (WEB / "static" / "chat.js").read_text(encoding="utf-8")
    assert "chat-fechar" not in js and "Sobreposicoes.registrar" in js


def test_toque_na_faixa_superior_do_celular_fecha_sem_acionar_o_que_esta_por_baixo():
    js = (WEB / "static" / "chat.js").read_text(encoding="utf-8")
    assert "stopPropagation" in js and "preventDefault" in js


# 2. categoria em slug

@pytest.mark.parametrize("slug", ["ukulele", "UKULELE", "Ukulele", "ukuleles"])
def test_catalogo_normaliza_categoria_para_o_nome_canonico(cliente, slug):
    r = cliente.get("/catalogo", params={"categoria": slug})
    assert r.status_code == 200
    assert "<h1>Ukuleles</h1>" in r.text
    assert "<title>Ukuleles" in r.text
    assert re.search(r'<option value="Ukuleles" selected>', r.text)
    assert re.search(r'class="card"', r.text)


def test_catalogo_categoria_inexistente_segue_com_aviso(cliente):
    r = cliente.get("/catalogo", params={"categoria": "tuba"})
    assert "Não temos essa categoria no catálogo." in r.text


def test_paginacao_do_catalogo_usa_o_nome_canonico(cliente):
    r = cliente.get("/catalogo", params={"categoria": "violao"})
    assert "<h1>Violões</h1>" in r.text


# 3. CEP inválido

@pytest.mark.parametrize("cep", ["123", "99999-999"])
def test_checkout_com_cep_invalido_nao_diz_informe_o_cep(cliente, monkeypatch, cep):
    from emporio.ferramentas import cep as cep_mod
    monkeypatch.setenv("EMPORIO_CEP_EXTERNO", "1")
    cep_mod._memoria.clear()
    monkeypatch.setattr(cep_mod, "_consultar_externo", lambda d: {"erro": "true"})
    cliente.post("/carrinho/adicionar", data={"produto_id": CRAFTER, "quantidade": 1})
    html = cliente.get("/checkout", params={"cep": cep}).text
    assert 'role="alert"' in html and ("CEP" in html)
    assert "Informe o CEP" not in html and "Frete: a calcular" in html
    cep_mod._memoria.clear()


def test_checkout_sem_cep_continua_pedindo_o_cep(cliente):
    cliente.post("/carrinho/adicionar", data={"produto_id": CRAFTER, "quantidade": 1})
    assert "Informe o CEP" in cliente.get("/checkout").text


# 4. total_visto fora da URL

def test_checkout_nao_grava_total_visto_na_url(cliente):
    cliente.post("/carrinho/adicionar", data={"produto_id": CRAFTER, "quantidade": 1})
    html = cliente.get("/checkout", params={"cep": "79002-000"}).text
    form = re.search(r'<form class="checkout"[^>]*>', html).group(0)
    assert 'hx-replace-url="true"' in form
    assert re.search(r'hx-params="not total_visto"', form)


# 5. tabelas de políticas

def test_tabelas_rolaveis_das_politicas_sao_focaveis_e_nomeadas(cliente):
    html = cliente.get("/politicas").text
    blocos = re.findall(r'<div class="tabela-rolavel"[^>]*>', html)
    assert blocos
    for b in blocos:
        assert 'tabindex="0"' in b and 'role="region"' in b
        assert re.search(r'aria-label="[^"]{3,}"', b)


# 6. confirmação do pedido

def _pedido(cliente):
    cliente.post("/carrinho/adicionar", data={"produto_id": CRAFTER, "quantidade": 1})
    r = cliente.post("/checkout", data={"forma": "pix", "parcelas": "1", "cep": "79002-000",
                                         "total_visto": _total(cliente)})
    assert r.status_code == 303, r.text[:200]
    return cliente.get(r.headers["location"]).text


def _total(cliente):
    return re.search(r'name="total_visto" value="(\d+)"', cliente.get("/checkout", params={"cep": "79002-000"}).text).group(1)


def test_confirmacao_diz_pedido_registrado_uma_vez(cliente):
    html = _pedido(cliente)
    texto = re.sub(r"<[^>]+>", " ", html[html.index("<main"):])
    assert len(re.findall(r"Pedido registrado", texto)) == 1
    assert "Nenhum valor foi cobrado" in texto


def test_valor_monetario_nao_quebra_entre_rs_e_numero():
    achado = re.findall(r"(?m)^([^{\n]*\.resumo-sub[^{\n]*)\{([^}]*)\}", CSS)
    assert any("white-space: nowrap" in corpo and ".resumo-final dd" in seletor and ".resumo-qtd" in seletor
               for seletor, corpo in achado)


# 7. botão da Lia compacto no celular

def test_botao_da_lia_fica_compacto_abaixo_de_768px():
    m = re.search(r"@media \(max-width: 767px\) \{(.*?)\n\}", CSS, re.S)
    assert m
    bloco = CSS[CSS.index("@media (max-width: 767px)"):]
    assert ".lia-botao span" in bloco and "clip" in bloco
