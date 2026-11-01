"""Voz da Lia (etapa 16): primeira pessoa, sem terceira pessoa de equipe e sem "Chamado registrado."."""
from __future__ import annotations

import re

import pytest

from emporio.agente.laco import Agente

CONVERSAS = [
    ("oi",), ("qual o horário?",), ("qual o horário?", "e feriado?"), ("quais as formas de pagamento?",),
    ("quero falar com um atendente", "sim"), ("como funciona a troca e a garantia?",),
    ("quero devolver", "pedido 4 final 3456", "online, recebi dia 15/12/2025, sem uso", "sim"),
    ("frete para Dourados",), ("frete para Dourados", "sim"), ("quero abrir uma reclamação porque o pedido 8 atrasou", "sim"),
    ("posso parcelar o Shelby SN-100 em 6x?",), ("como funciona a garantia?",),
    ("meu instrumento chegou amassado",), ("o frete da devolução é por conta de quem?",),
    ("quanto tempo demora o reembolso?",), ("tem estacionamento?",), ("quem é você?",),
    ("estou muito irritado, ninguém resolve",), ("isso é um absurdo",), ("qual o endereço de entrega do pedido 4?",),
    ("a promoção do Black Friday vale?",), ("quero devolver", "pedido 1 final 0000"),
]
PROIBIDOS = [r"a equipe confirma", r"chamado registrado\.", r"(^|[.!?]\s+|\n)a equipe\b", r"(^|[.!?]\s+|\n)a loja\b"]


@pytest.mark.parametrize("mensagens", CONVERSAS)
def test_nenhuma_resposta_fala_da_equipe_em_terceira_pessoa(mensagens):
    agente = Agente()
    for m in mensagens:
        texto = agente.responder("voz", m, "eval").texto
        for padrao in PROIBIDOS:
            assert not re.search(padrao, texto, re.I), (m, padrao, texto)
