"""Ajustes finais de tela (etapa 12): o site não anuncia que é demonstração no pedido nem no rastreio."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from emporio.ferramentas.condicoes import calcular_condicoes
from emporio.web.app import criar_app

UKULELE_SOPRANO = 117
CEP_CAMPO_GRANDE = "79002-000"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def test_pedido_e_rastreio_dizem_pedido_sem_a_palavra_demonstracao(cliente, sql):
    cliente.post("/carrinho/adicionar", data={"produto_id": UKULELE_SOPRANO, "quantidade": 1})
    base = calcular_condicoes(produto_id=UKULELE_SOPRANO, forma="debito").dados["final_centavos"]
    taxa = calcular_condicoes(valor=base, forma="debito", cidade="Campo Grande").dados["frete"]["taxa_centavos"]
    r = cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cep": CEP_CAMPO_GRANDE, "total_visto": str(base + taxa)})
    assert r.status_code == 303
    numero = r.headers["location"].rsplit("/", 1)[1]
    pedido = cliente.get(f"/pedido/{numero}").text
    rastreio = cliente.post("/rastreio", data={"pedido": numero, "final_telefone": ""}).text
    for html in (pedido, rastreio):
        assert 'class="categoria">Pedido</p>' in html and "Nenhum valor foi cobrado" in html  # o aviso do checkout segue
        assert "demonstra" not in html.lower()
