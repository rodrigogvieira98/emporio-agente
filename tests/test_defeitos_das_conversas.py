"""Defeitos achados ao rodar conversas reais: laço na devolução, texto do modelo duplicado, eco de rótulo
e chamado duplicado."""
from __future__ import annotations

import json

from emporio.agente import redacao
from emporio.agente.laco import Agente
from emporio.agente.llm import RespostaLlm
from emporio.agente.redacao import Redator, repete_o_bloco, validar
from emporio.agente.estado import Estado


def conversar(*mensagens, conversa="c1", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def protocolos(sql):
    return [r["protocolo"] for r in sql.execute("SELECT protocolo FROM chamados ORDER BY id")]


class ClienteFalso:
    def __init__(self, saida):
        self.saida = saida

    def conversar(self, modelo, mensagens, formato=None, limite=None, maximo_tokens=400):
        return RespostaLlm(conteudo=json.dumps(self.saida), tokens_prompt=1, tokens_resposta=1, latencia_ms=1)


# 1. devolução sem laço ------------------------------------------------------------------------

def test_devolucao_do_enunciado_fecha_com_protocolo_sem_laco(sql):
    r = conversar("Me arrependi da minha compra, posso devolver meu pedido?", "pedido 4, final 3456",
                  "Comprei pelo site, recebi anteontem, nem abri", "sim")
    assert "Posso registrar" in r[2].texto  # "nem abri" completou o estado do produto
    assert "garanto" not in r[2].texto.lower() and "Eu não consigo garantir a elegibilidade" in r[2].texto
    assert "EM-" in r[3].texto and len(protocolos(sql)) == 1


def test_sim_responde_a_pergunta_so_do_estado_do_produto(sql):
    agente = Agente(concisao=True)
    r = conversar("quero devolver", "pedido 4, final 3456", "comprei pelo site, recebi anteontem", "sim", agente=agente)
    assert "Encontrei o pedido" in r[1].texto
    assert "estado do produto" in r[2].texto and "Encontrei o pedido" not in r[2].texto  # concisão: não repete o achado
    assert "Posso registrar" in r[3].texto and "produto na embalagem original" in r[3].texto


def test_sim_nao_preenche_quando_a_pergunta_tinha_varios_campos(sql):
    r = conversar("quero devolver", "pedido 4, final 3456", "sim")
    assert "Posso registrar" not in r[2].texto and "me conta" in r[2].texto


def test_nao_responde_estado_do_produto_como_com_uso(sql):
    r = conversar("quero devolver", "pedido 4, final 3456", "comprei pelo site, recebi anteontem", "não")
    assert "com sinais de uso" in r[3].texto


def test_mesma_pergunta_no_maximo_duas_vezes_e_na_terceira_oferece_registro(sql):
    r = conversar("quero devolver", "pedido 4, final 3456", "hmm", "hmm", "sim")
    assert "me conta" in r[1].texto and "me conta" in r[2].texto  # a pergunta saiu duas vezes
    assert "me conta" not in r[3].texto and "Posso registrar o seu caso" in r[3].texto  # na terceira, oferta
    assert "EM-" in r[4].texto and len(protocolos(sql)) == 1


def test_pergunta_diferente_zera_a_contagem(sql):
    r = conversar("quero devolver", "pedido 4, final 3456", "hmm", "comprei pelo site", "hmm", "hmm")
    assert "Posso registrar o seu caso" not in " ".join(x.texto for x in r[:5])
    assert "Posso registrar o seu caso" in r[5].texto


# 2. texto do modelo duplicando o bloco -------------------------------------------------------

def test_frase_do_modelo_que_repete_o_bloco_sai_e_o_bloco_fica():
    bloco = "Nosso horário de funcionamento:\n- sábado: das 09:00 às 13:00\nAgora a loja está aberta."
    assert repete_o_bloco("A loja está aberta.", bloco)
    assert not repete_o_bloco("Qualquer coisa é só chamar.", bloco)
    r = Redator("falso:1b", ClienteFalso({"abertura": None, "fechamento": "A loja está aberta."}))
    saida = r.envolver(Estado(), "e sábado?", bloco, True, [])
    assert saida == bloco and saida.count("aberta") == 1


def test_frase_nova_do_modelo_continua_valendo():
    bloco = "Agora a loja está aberta."
    r = Redator("falso:1b", ClienteFalso({"abertura": "Claro!", "fechamento": "Qualquer coisa é só chamar."}))
    assert r.envolver(Estado(), "oi", bloco, True, []) == "Claro!\nAgora a loja está aberta.\nQualquer coisa é só chamar."


# 3. eco de rótulo ------------------------------------------------------------------------------

def test_eco_de_rotulo_do_prompt_e_rejeitado():
    for eco in ("Texto da loja", "texto_da_loja: ok", "Mensagem do cliente", "{\"abertura\": \"oi\"}"):
        assert validar(eco, "bloco", Estado()) == "eco_de_rotulo", eco
    assert validar("Claro, já te ajudo.", "bloco", Estado()) is None
    assert redacao.ECO_DE_ROTULO.search("Abertura: oi")


def test_redator_descarta_texto_com_eco_e_devolve_so_o_bloco():
    r = Redator("falso:1b", ClienteFalso({"abertura": "Texto da loja", "fechamento": None}))
    assert r.envolver(Estado(), "vocês vendem cordas?", "Não vendemos cordas.", True, []) == "Não vendemos cordas."
    assert r.telemetria[-1]["resultado"] == "descartada:eco_de_rotulo"


# 4. chamado duplicado -------------------------------------------------------------------------

def test_atendente_depois_de_reclamacao_nao_abre_segundo_chamado(sql):
    r = conversar("quero abrir reclamação", "o violão chegou riscado e ninguém me responde, que absurdo",
                  "quero falar com um atendente")
    assert protocolos(sql) == ["EM-000001"]
    assert "EM-000001" in r[2].texto and "na fila da equipe" in r[2].texto


def test_atendente_em_outra_conversa_abre_chamado_proprio(sql):
    conversar("quero falar com um atendente", conversa="a")
    conversar("quero falar com um atendente", conversa="b")
    assert protocolos(sql) == ["EM-000001", "EM-000002"]


# 5. pergunta geral sobre troca, devolução e garantia ------------------------------------------

import pytest  # noqa: E402


@pytest.mark.parametrize("frase", [
    "Quero saber como funciona a troca e a garantia.", "como funciona a troca?", "qual a política de devolução?",
    "como funciona a troca e a garantia?", "vocês trocam produto?",
])
def test_pergunta_geral_de_troca_responde_a_politica_sem_pedir_pedido(frase):
    (r,) = conversar(frase)
    assert "consultar_pedido" not in [a.get("ferramenta") for a in r.acoes]
    assert "número do pedido" not in r.texto.split("Se quiser")[0]
    assert "Devolução por arrependimento" in r.texto and "Troca por defeito" in r.texto
    assert "Troca por preferência" in r.texto and "Garantia legal" in r.texto
    assert "Se quiser, posso verificar um pedido" in r.texto
    assert "o manual não diz se a contagem parte da compra" in r.texto  # a ambiguidade do manual aparece
    assert r.estado == "concluido"


@pytest.mark.parametrize("frase", [
    "quero trocar meu violão", "quero devolver", "Me arrependi da minha compra, posso devolver meu pedido?",
    "comprei um violão e quero trocar",
])
def test_caso_proprio_continua_no_fluxo_do_pedido(frase):
    (r,) = conversar(frase)
    assert "me diga o número do pedido" in r.texto and "Como funcionam troca" not in r.texto


def test_garantia_sozinha_continua_com_a_resposta_de_garantia():
    (r,) = conversar("como funciona a garantia?")
    assert "Garantia legal" in r.texto and "Como funcionam troca" not in r.texto


def test_pergunta_geral_depois_do_caso_proprio_nao_perde_o_fluxo(sql):
    r = conversar("quero devolver", "pedido 4, final 3456", "como funciona a troca?")
    assert "Como funcionam troca" in r[2].texto and "Quer retomar" in r[2].texto
