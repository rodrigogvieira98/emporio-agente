"""Etapa 24, item 1: riscos finais antes do congelamento. Cada teste cobre uma intenção ou um estado, nunca uma frase só."""
from __future__ import annotations

import re

import pytest

from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="e24", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def chamados(sql) -> int:
    return sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0]


# --- item 1: defeito não é preferência ---------------------------------------------------------

RELATOS_DE_DEFEITO = [
    "comprei uma guitarra há 20 dias e ela veio com o captador do meio mudo, nunca funcionou",
    "meu violão está sem som nenhum desde ontem",
    "o tampo do violão começou a descolar da lateral",
    "o braço do baixo trincou depois de um mês",
    "o teclado parou de funcionar de repente",
    "o baixo está com um chiado forte quando ligo",
    "comprei um ukulele e ele quebrou sozinho",
    "o contrabaixo chegou com um defeito na pintura",
]


@pytest.mark.parametrize("relato", RELATOS_DE_DEFEITO)
def test_relato_de_falha_segue_a_regra_de_defeito(relato):
    (r,) = conversar(relato)
    assert "troca por defeito" in r.texto and "30 dias" in r.texto, r.texto
    assert "preferência" not in r.texto and "Encontrei" not in r.texto, r.texto


@pytest.mark.parametrize("pergunta", [
    "pedido nao tenho aqui agora, mas foi compra normal, pode trocar?",
    "A loja troca ou tenho que ir atrás do fabricante?",
    "então vocês trocam?",
])
def test_pergunta_se_troca_com_defeito_em_foco_mantem_a_regra_de_defeito(pergunta):
    rs = conversar("o tampo do violão começou a descolar da lateral", pergunta)
    assert "troca por defeito" in rs[-1].texto, rs[-1].texto
    assert "preferência" not in rs[-1].texto, rs[-1].texto


def test_defeito_depois_dos_30_dias_continua_sendo_defeito_na_pergunta_de_troca():
    rs = conversar("comprei uma guitarra há 50 dias e o captador está mudo", "pode trocar?")
    assert "preferência" not in rs[-1].texto, rs[-1].texto
    assert "fabricante" in rs[-1].texto, rs[-1].texto


def test_troca_por_preferencia_explicita_continua_valendo():
    (r,) = conversar("quero trocar a guitarra, não gostei da cor")
    assert "preferência" in r.texto, r.texto


def test_preferencia_dita_depois_do_defeito_ainda_e_preferencia():
    rs = conversar("o tampo do violão começou a descolar da lateral", "na verdade só não gostei da cor, posso trocar?")
    assert "preferência" in rs[-1].texto, rs[-1].texto


@pytest.mark.parametrize("relato", [
    "o entregador tá aqui na porta e a caixa do meu teclado veio toda amassada, recebo ou não recebo??",
    "a embalagem do meu violão chegou rasgada e o tampo parece amassado",
])
def test_avaria_no_transporte_com_nome_de_instrumento_nao_abre_o_catalogo(relato):
    (r,) = conversar(relato)
    assert "Encontrei" not in r.texto and "R$" not in r.texto, r.texto
    assert "recusar o recebimento" in r.texto, r.texto
