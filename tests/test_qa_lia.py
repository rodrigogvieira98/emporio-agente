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
