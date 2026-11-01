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


# --- item 1: forma do reembolso -------------------------------------------------------------

PERGUNTAS_FORMA_REEMBOLSO = [
    "se eu devolver, o dinheiro volta no cartão?",
    "paguei no pix, o reembolso volta como?",
    "como é feito o estorno de uma devolução?",
    "o dinheiro da devolução cai como?",
    "se eu devolver, o valor volta pra onde?",
    "o reembolso é feito em qual forma?",
    "devolvem o dinheiro no pix ou em crédito na loja?",
]


@pytest.mark.parametrize("pergunta", PERGUNTAS_FORMA_REEMBOLSO)
def test_forma_do_reembolso_responde_pela_regra_de_arrependimento(sql, pergunta):
    (r,) = conversar(pergunta)
    t = r.texto.lower()
    assert "mesma forma de pagamento" in t and "10 dias úteis" in t, r.texto
    assert "7 dias" in t and "embalagem original" in t, r.texto  # a condição de elegibilidade vem junto
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 0


# --- item 2: modelo com número no nome ------------------------------------------------------

@pytest.mark.parametrize("pergunta,nome,estado", [
    ("tem o baixo Ibanez 2X?", "Ibanez Bass 2X Electric Bass", "descontinuado"),
    ("tem o baixo 2X?", "Ibanez Bass 2X Electric Bass", "descontinuado"),
    ("me fala do baixo Ibanez 2X", "Ibanez Bass 2X Electric Bass", "descontinuado"),
    ("tem o violão Giannini GF-3D?", "Giannini GF-3D", "esgotado"),
    ("tem o violão Shelby SN-7C?", "Shelby SN-7C", "descontinuado"),
    ("tem o ukulele Kala KA-ABP-CTG?", "Kala KA-ABP-CTG", "ainda não está à venda"),
])
def test_produto_nomeado_responde_pelo_cadastro_mesmo_com_categoria(pergunta, nome, estado):
    (r,) = conversar(pergunta)
    assert nome in r.texto and estado in r.texto, r.texto
    assert "Não encontrei" not in r.texto


@pytest.mark.parametrize("pergunta,nome", [
    ("quanto custa o baixo Yamaha 3X?", "Yamaha Bass 3X"),
    ("quero o baixo Music Man 1X", "Music Man Bass 1X"),
    ("tem o contrabaixo Yamaha 3X?", "Yamaha Bass 3X"),
    ("o baixo 4X tem?", "Music Man Bass 4X"),
])
def test_modelo_com_numero_e_categoria_vira_o_produto_e_nao_uma_lista(pergunta, nome):
    (r,) = conversar(pergunta)
    assert nome in r.texto and "Encontrei" not in r.texto, r.texto


@pytest.mark.parametrize("pergunta,parcelas", [
    ("qual o preço do Yamaha Bass 3X em 3x?", "3x"),
    ("quero pagar o baixo Music Man 4X em 2x", "2x"),
    ("o Yamaha C40 no cartão 3x", "3x"),
    ("dá pra parcelar o Yamaha Bass 3X em 5x?", "5x"),
])
def test_numero_do_nome_e_parcela_na_mesma_frase(pergunta, parcelas):
    (r,) = conversar(pergunta)
    assert f"em {parcelas}, cada parcela" in r.texto, r.texto


def test_parcela_sozinha_depois_de_produto_em_foco():
    r = conversar("quanto custa o Yamaha Bass 3X", "3x")
    assert "Yamaha Bass 3X" in r[1].texto and "em 3x, cada parcela" in r[1].texto


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
