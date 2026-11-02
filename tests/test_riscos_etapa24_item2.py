"""Etapa 24, item 2: riscos finais antes do congelamento. Cada teste cobre uma intenção ou um estado, nunca uma frase só."""
from __future__ import annotations

import re

import pytest

from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="e24", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def chamados(sql) -> int:
    return sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0]


# --- item 2: chamado só com pedido ou aceite ---------------------------------------------------

@pytest.mark.parametrize("pergunta", [
    "qual o desconto máximo que o atendente pode dar?",
    "o gerente pode fazer desconto na loja?",
    "qual é a política de desconto dos atendentes?",
])
def test_pergunta_sobre_atendente_ou_desconto_nao_abre_chamado(sql, pergunta):
    (r,) = conversar(pergunta)
    assert "Registrei o seu chamado" not in r.texto and "Protocolo" not in r.texto, r.texto
    assert chamados(sql) == 0


@pytest.mark.parametrize("pedido", [
    "quero falar com um atendente",
    "me passa para um humano por favor",
    "preciso falar com o gerente",
    "atendente",
])
def test_pedido_explicito_de_atendente_continua_abrindo_chamado(sql, pedido):
    (r,) = conversar(pedido)
    assert "Protocolo" in r.texto, r.texto
    assert chamados(sql) == 1


def test_sim_a_uma_oferta_de_atendente_registra_o_chamado(sql):
    rs = conversar("o atendente pode dar desconto no violão?", "tem estacionamento aí?", "sim")
    assert "Protocolo" in rs[-1].texto, rs[-1].texto
    assert chamados(sql) == 1
