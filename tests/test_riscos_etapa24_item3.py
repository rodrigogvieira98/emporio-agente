"""Etapa 24, item 3: riscos finais antes do congelamento. Cada teste cobre uma intenção ou um estado, nunca uma frase só."""
from __future__ import annotations

import re

import pytest

from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="e24", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def chamados(sql) -> int:
    return sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0]


# --- item 3: estoque e quantidade --------------------------------------------------------------

def test_quantidade_acima_do_estoque_diz_quantas_ha_e_nao_cota():
    (r,) = conversar("quero 20 Yamaha C40 pra uma escola de música, tem no estoque?")
    assert "12 unidades" in r.texto, r.texto
    assert "11.398" not in r.texto and "Para 20 unidades" not in r.texto, r.texto


def test_quantidade_acima_do_estoque_no_credito_tambem_nao_cota():
    (r,) = conversar("quero 15 Yamaha C40 no crédito em 3x")
    assert "12 unidades" in r.texto, r.texto
    assert not re.search(r"Para 15 unidades", r.texto), r.texto


def test_pergunta_de_estoque_com_quantidade_compara_com_o_estoque_do_produto():
    (acima,) = conversar("tem 20 Yamaha C40 no estoque?", conversa="e24a")
    assert "12 unidades" in acima.texto and "Para 20 unidades" not in acima.texto, acima.texto
    (dentro,) = conversar("tem 5 Yamaha C40 no estoque?", conversa="e24b")
    assert "Para 5 unidades" in dentro.texto, dentro.texto


def test_numero_de_garantia_nao_vira_quantidade():
    (r,) = conversar("o Yamaha C40 tem 12 meses de garantia?")
    assert "unidades" not in r.texto, r.texto
