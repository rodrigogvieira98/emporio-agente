"""Etapa 23: causas estruturais do QA 3. Cada teste cobre uma estrutura de fluxo ou de percepção, nunca uma frase."""
from __future__ import annotations

import re

import pytest

from emporio.agente.laco import Agente
from emporio.agente.estado import carregar_estado


def conversar(*mensagens, conversa="e23", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def tem_carrinho(r) -> bool:
    return any(x.get("tipo") == "carrinho" for x in r.links)


# --- item 1: sim ou não com conteúdo ----------------------------------------------------------

def _com_convite_de_retomar():
    """Devolução em andamento (falta o pedido), interrompida por uma pergunta de horário: a Lia oferece retomar."""
    rs = conversar("quero devolver o violão que comprei, ainda tá na caixa", "que horas vocês fecham?")
    assert "Quer retomar?" in rs[-1].texto, rs[-1].texto
    return rs


@pytest.mark.parametrize("fala", [
    "não, quero colocar o Rozini RC-104 no carrinho",
    "não, ja deu. quero comprar o Yamaha C40",
    "não precisa, quero ver o preço do Yamaha C40",
])
def test_recusa_com_conteudo_encerra_a_pendencia_e_segue_o_resto(fala):
    conversar("quero devolver o violão que comprei, ainda tá na caixa", "que horas vocês fecham?", conversa="e23a")
    (r,) = conversar(fala, conversa="e23a")
    assert "deixei esse assunto de lado" not in r.texto and "Quer retomar" not in r.texto, r.texto
    assert re.search(r"R\$ \d", r.texto), r.texto  # a intenção do resto da frase foi atendida
    est = carregar_estado("e23a")
    assert not est.pendentes


def test_recusa_pura_continua_encerrando_a_pendencia():
    _com_convite_de_retomar()
    (r,) = conversar("não", conversa="e23")
    assert "deixei esse assunto de lado" in r.texto


def test_sim_puro_continua_retomando():
    _com_convite_de_retomar()
    (r,) = conversar("sim", conversa="e23")
    assert "pedido" in r.texto.lower() and "4 últimos" in r.texto


def test_sim_com_outra_pergunta_nao_retoma_e_responde_a_pergunta():
    _com_convite_de_retomar()
    (r,) = conversar("sim, e onde fica a loja?", conversa="e23")
    assert "Rua 14 de Maio" in r.texto, r.texto
    assert not carregar_estado("e23").pendentes


def test_recusa_de_registro_com_pergunta_responde_a_pergunta():
    (r,) = conversar("vocês têm estacionamento?", conversa="e23b")
    assert "Responda sim ou não" in r.texto
    (r,) = conversar("não, qual o horário de vocês?", conversa="e23b")
    assert "das 9h às 18h" in r.texto and "não registrei nada" not in r.texto.lower(), r.texto
