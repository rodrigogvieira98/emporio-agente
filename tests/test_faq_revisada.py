"""Perguntas frequentes revisadas (etapa 22): voz da loja, sem expressões internas, temas e perguntas novas."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from emporio.politicas.manual import fato
from emporio.web import conteudo
from emporio.web.app import criar_app

INTERNAS = ("A regra não informa", "precisa de confirmação da nossa equipe", "a nossa equipe confirma", "(.package)",
            "regra não", "protótipo", "marco inicial", "tipo_dias")
TEMAS = ("Pagamento", "Entrega e frete", "Pedido e rastreio", "Trocas, devoluções e garantia", "Sobre a loja")


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app()) as c:
        yield c


def _resposta(trecho: str) -> str:
    achadas = [p["resposta"] for p in conteudo.perguntas() if trecho.lower() in p["pergunta"].lower()]
    assert achadas, trecho
    return achadas[0]


def test_nenhuma_resposta_tem_expressao_interna(cliente):
    for p in conteudo.perguntas():
        for ruim in INTERNAS:
            assert ruim.lower() not in p["resposta"].lower(), (p["pergunta"], ruim)
    html = cliente.get("/perguntas-frequentes").text
    assert "Jadlog (" not in html and "A regra não informa" not in html


def test_cada_tema_existe_e_tem_pergunta():
    assert tuple(g["tema"] for g in conteudo.faq_agrupada()) == TEMAS
    assert all(g["itens"] for g in conteudo.faq_agrupada())


def test_primeira_frase_responde_e_usa_a_voz_da_loja():
    r = _resposta("parcelar")
    assert r.startswith("Sim, ") and "equipe" not in r
    assert _resposta("acessórios").startswith("Não")


def test_reembolso_na_mesma_forma_e_prazo_do_manual():
    r = _resposta("reembolso")
    dias = fato("devolucao.arrependimento_reembolso_dias_uteis_max").valor
    assert "mesma forma de pagamento" in r and f"até {dias} dias úteis" in r


def test_avaria_acessorios_e_privacidade_respondidos():
    assert "recuse o recebimento" in _resposta("danificado")
    ac = _resposta("acessórios")
    for item in fato("escopo.acessorios_nao_vendidos").valor:
        assert item in ac
    priv = _resposta("meus dados")
    assert "marketing" in priv and "exclusão" in priv


def test_home_continua_com_as_quatro_perguntas_principais():
    principais = [p["pergunta"] for p in conteudo.perguntas(somente_principais=True)]
    assert principais == ["Quais formas de pagamento vocês aceitam?", "Como é o frete?", "Como acompanho meu pedido?",
                          "Como funcionam as trocas?"]


def test_largura_de_leitura_das_respostas():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "src" / "emporio" / "web" / "static" / "site.css").read_text(encoding="utf-8")
    assert ".faq-item p {" in css and "max-width: 75ch" in css.split(".faq-item p {")[1].split("}")[0]
