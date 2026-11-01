"""QA 2 da Lia, etapa A."""
from __future__ import annotations

import pytest

from emporio.agente.fabrica import criar_agente


class _Dubla:
    chamadas: list = []

    def conversar(self, *a, **k):  # pragma: no cover - não deve ser chamado
        raise AssertionError("sem chamada")


def test_redacao_desligada_por_padrao(monkeypatch):
    monkeypatch.delenv("EMPORIO_REDACAO", raising=False)
    monkeypatch.setenv("EMPORIO_DECISOR", "regras")
    assert criar_agente("falso:1b", _Dubla()).redator is None
    monkeypatch.setenv("EMPORIO_REDACAO", "1")
    assert criar_agente("falso:1b", _Dubla()).redator is not None
    monkeypatch.setenv("EMPORIO_REDACAO", "0")
    assert criar_agente("falso:1b", _Dubla()).redator is None


from emporio.agente.laco import Agente


def conversar(*mensagens, agente=None, conversa="qa2"):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def textos(*mensagens, **kw):
    return [r.texto for r in conversar(*mensagens, **kw)]


# 2. o que não existe nos dados ------------------------------------------------------------------

@pytest.mark.parametrize("pergunta", [
    "tem estacionamento na loja?", "dá pra retirar na loja?", "vocês compram instrumento usado?",
    "emitem nota fiscal no CNPJ da minha banda?", "tem seguro contra queda?", "preciso levar na loja ou vcs buscam?"])
def test_assunto_fora_dos_dados_recebe_nao_tenho_a_informacao(pergunta):
    (t,) = textos(pergunta)
    assert "não tenho essa informação" in t.lower() and "atendente" in t.lower() and "Responda sim ou não" in t
    assert "R$" not in t and "CNPJ" not in t


def test_estacionamento_junto_do_endereco_responde_as_duas():
    (t,) = textos("onde fica a loja? tem estacionamento?")
    assert "Rua 14 de Maio" in t and "não tenho essa informação" in t.lower()


# 3. regra específica vence o tema anterior --------------------------------------------------------

def test_boquilha_no_meio_da_troca_recebe_a_exclusao():
    t = textos("comprei um violão na loja física faz 3 dias, posso devolver? desisti", "e se eu quiser trocar por outro modelo?",
               "e a boquilha de sax que comprei com minha amiga, dá pra trocar? ela nem usou")
    assert "boquilha" in t[2].lower() and "não" in t[2].lower() and "7 dias" not in t[2]


def test_sem_queda_nao_ativa_mau_uso_e_volta_para_defeito():
    t = textos("meu violão caiu do suporte e trincou o tampo, comprei tem 2 meses. a garantia cobre?",
               "e o braço que tá empenando sozinho, sem queda nenhuma? isso é defeito né")
    assert "mau uso" in t[0].lower()
    assert "mau uso" not in t[1].lower() and "fabricante" in t[1].lower()


# 4. saudação não engole o pedido ------------------------------------------------------------------

def test_saudacao_com_pedido_de_produto_segue_a_intencao():
    (t,) = textos("Bom dia, a igreja está procurando um piano digital até 2 mil reais")
    assert "Oi! Sou a Lia" not in t and "R$" in t


def test_saudacao_com_presente_e_teto_pergunta_o_que_falta():
    (t,) = textos("boa noite! queria dar um instrumento de presente pra minha sobrinha que faz 10 anos, gasto no max uns 300 reais")
    assert "Oi! Sou a Lia" not in t and ("instrumento" in t.lower() or "R$" in t)


def test_saudacao_sozinha_continua_saudacao():
    (t,) = textos("bom dia")
    assert t.startswith("Oi! Sou a Lia")


# 5. compra com o produto em foco -------------------------------------------------------------------

@pytest.mark.parametrize("fala", ["beleza, coloca ele no carrinho pra mim", "fechado, pode por no carrinho",
                                  "vou levar", "como eu faço pra finalizar?", "como finalizo"])
def test_compra_usa_o_produto_em_foco_e_mostra_o_botao(fala):
    r = conversar("Quanto fica o Tagima Memphis no pix?", fala)[1]
    assert "não entendi" not in r.texto.lower() and "Tagima Memphis" in r.texto
    assert any(l.get("acao") == "/carrinho/adicionar" for l in r.links)


@pytest.mark.parametrize("fala", ["vou levar", "coloca no carrinho", "como finalizo"])
def test_compra_sem_produto_pede_o_produto_em_uma_frase(fala):
    (t,) = textos(fala)
    assert "marca e o modelo" in t and "não entendi" not in t.lower()


def test_agradecimento_com_outro_pedido_nao_encerra():
    t = textos("Quanto fica o Tagima Memphis no pix?", "valeu, e o horário de vocês?")
    assert "horário de funcionamento" in t[1].lower() and "foi um prazer" not in t[1].lower()
