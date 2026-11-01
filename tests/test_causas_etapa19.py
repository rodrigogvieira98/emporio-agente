"""Etapa 19: correções de causa. Cada teste generaliza por intenção, estado e vocabulário."""
from __future__ import annotations

import re

import pytest

from emporio.agente.expediente import hora_br
from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="e19", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


# --- item 6: horário no formato do site ---------------------------------------------------

@pytest.mark.parametrize("entrada,saida", [("09:00", "9h"), ("18:00", "18h"), ("08:30", "8h30"), ("13:05", "13h05")])
def test_hora_br(entrada, saida):
    assert hora_br(entrada) == saida


def test_horario_escrito_no_formato_do_site():
    (r,) = conversar("que horas vocês abrem sábado?")
    assert "das 9h às 13h" in r.texto and "das 9h às 18h" in r.texto
    assert not re.search(r"\b\d{2}:\d{2}\b", r.texto)


def test_retorno_fora_do_expediente_no_formato_do_site(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-11-01T10:00:00")
    (r,) = conversar("bom dia")
    assert "amanhã às 9h" in r.texto and not re.search(r"\b\d{2}:\d{2}\b", r.texto)
