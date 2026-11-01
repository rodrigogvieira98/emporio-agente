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


# --- item 3: pedido explícito de atendente traz prazo e canais ------------------------------

@pytest.mark.parametrize("mensagem", ["quero falar com um atendente", "me passa para uma pessoa de verdade",
                                      "preciso de um humano"])
def test_pedido_explicito_de_atendente_traz_protocolo_prazo_e_canais(sql, mensagem):
    (r,) = conversar(mensagem)
    assert "EM-" in r.texto and "24 horas úteis" in r.texto
    assert "WhatsApp" in r.texto and "telefone" in r.texto.lower() and "9h" in r.texto
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1


def test_chamado_aberto_por_devolucao_continua_sem_prazo_de_reclamacao(sql):
    r = conversar("quero devolver um violão", "pedido 4 final 3456", "online, recebi dia 15/12/2025, sem uso", "sim")
    assert "EM-" in r[3].texto and "24 horas" not in r[3].texto
