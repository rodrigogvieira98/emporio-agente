"""QA de conversas da Lia (etapa 11): correções gerais por intenção, estado e vocabulário."""
from __future__ import annotations

import pytest

from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="qa", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def textos(*mensagens, **kw):
    return [r.texto for r in conversar(*mensagens, **kw)]


# 1. próxima abertura com ressalva de feriado ---------------------------------------------------

@pytest.fixture
def quinta_noite(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-11-05T20:00:00")


def test_proxima_abertura_traz_ressalva_de_feriado(quinta_noite):
    saudacao, horario = textos("oi", "que horas vocês abrem?")
    for t in (saudacao, horario):
        assert "09:00" in t and "feriado" in t.lower()
    assert "o horário pode mudar" in saudacao


def test_horario_fechado_nao_se_contradiz(quinta_noite):
    (t,) = textos("qual o horário de vocês?")
    assert "feriado" in t.lower() and "o horário pode mudar" in t


# 2. número sozinho não identifica produto ---------------------------------------------------------

def test_numero_do_pedido_em_turno_separado_nao_vira_produto():
    t = textos("quero saber do meu pedido", "numero 8")
    assert "4 últimos dígitos" in t[1] and "preço de tabela" not in t[1]


def test_dias_desde_a_compra_nao_viram_produto():
    t = textos("comprei um violao e veio com defeito", "comprei faz 10 dias, a tarraxa nao segura a afinação")
    assert "preço de tabela" not in t[1] and "pedido" in t[1].lower()


def test_semana_depois_de_garantia_nao_pede_escolha_de_modelo():
    t = textos("meu ukulele caiu da escada e trincou, a garantia cobre?", "mas comprei faz so 1 semana")
    assert "modelo parecido" not in t[1]


def test_parcelas_sozinhas_nao_trocam_o_produto_em_foco():
    t = textos("preco do violao yamaha c70", "3x", "12x")
    assert "C70" in t[1] and "C70" in t[2]
    assert "Bass" not in t[1] + t[2]


def test_cep_na_mensagem_nao_vira_modelo_parecido():
    t = textos("quanto custa o Yamaha FG800?", "frete pro CEP 01310-100")
    assert "modelo parecido" not in t[1]
