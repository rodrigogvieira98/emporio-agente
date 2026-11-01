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


# 6. extração de produto em frase composta, dois produtos e pronome --------------------------------

def test_produto_em_frase_composta_com_promocao_citada():
    t = textos("poxa, e a Telecaster que tava na queima de estoque?")
    assert "Telecaster" in t[0] and "não encontrei esse produto" not in t[0].lower()


def test_produto_com_comparacao_de_preco_de_outra_loja():
    (t,) = textos("achei 500 reais mais barato em outra loja na telecaster, cobre o preço?")
    assert "Telecaster" in t


def test_dois_produtos_com_ou_mostram_os_dois():
    (t,) = textos("stratocaster ou telecaster? to em duvida")
    assert "Stratocaster" in t and "Telecaster" in t and "R$" in t


def test_dois_produtos_com_entre():
    (t,) = textos("Entre o Taylor 214ce e o Martin D-28E, qual você levaria pro palco?")
    assert "Taylor 214ce" in t and "Martin D-28E" in t


def test_ela_usa_o_ultimo_produto_citado_nunca_o_mais_antigo():
    t = textos("Vi que o Martin D-28 tava com 15% de desconto na páscoa, ainda vale?",
               "poxa, e a Telecaster que tava na queima de estoque?", "tá bom, então me fala só quanto fica ela no pix")
    assert "Telecaster" in t[2] and "Martin" not in t[2]


# 7. regra certa por tema ---------------------------------------------------------------------------

def test_extravio_nao_cai_em_arrependimento():
    t = textos("se o pedido nunca chegar, vcs devolvem o dinheiro?")
    assert "arrependimento" not in t[0].lower() and "não tenho essa informação" in t[0].lower()


def test_estorno_de_pedido_cancelado_responde_reembolso_do_cancelado():
    t = textos("o pedido 17 foi cancelado, quero o estorno", "termina em 8765")
    assert "cancelado" in t[1].lower() and "dias úteis" in t[1] and "arrependimento" not in t[1].lower()


def test_reembolso_em_quanto_tempo_depois_de_consultar_cancelado():
    t = textos("oi, por que cancelaram meu pedido 17?", "Telefone termina em 8765",
               "vou receber meu dinheiro de volta quando?")
    assert "cancelado" in t[2].lower() and "dias úteis" in t[2] and "arrependimento" not in t[2].lower()


def test_dano_no_transporte_nao_vira_defeito():
    t = textos("o entregador amassou a caixa do violão, é defeito?")
    assert "recusar o recebimento" in t[0] and "troca por defeito" not in t[0]


def test_pix_sobre_promocao_responde_direto():
    t = textos("tem desconto no pix em produto na promoção?")
    assert "não" in t[0].lower() and "promocion" in t[0].lower() and "Formas de pagamento" not in t[0]


def test_pix_em_cima_do_preco_com_desconto_responde_direto():
    t = textos("e se eu pagar no pix fica quanto em cima do preço com desconto?")
    assert "promocion" in t[0].lower() and "Formas de pagamento" not in t[0]


def test_segurar_preco_ate_sexta_responde_direto():
    t = textos("consegue segurar esse preço pra mim até sexta? recebo só dia 5")
    assert "não seguramos" in t[0].lower() and "marca e o modelo" not in t[0]


@pytest.mark.parametrize("fala", ["quero excluir meus dados", "quero que apaguem meu cadastro, como faço?",
                                  "não quero receber promoção, como paro?"])
def test_excluir_dados_responde_a_secao_de_privacidade(fala):
    (t,) = textos(fala)
    assert "exclusão dos seus dados" in t and "Promoções ativas" not in t


# 10. telefone termina em ----------------------------------------------------------------------------

def test_telefone_termina_em_identifica_o_pedido():
    t = textos("oi, por que cancelaram meu pedido 17?", "Telefone termina em 8765")
    assert "Agora preciso dos 4 últimos" not in t[1] and "pedido 17" in t[1].lower()


# 8. convite de retomar --------------------------------------------------------------------------------

def test_convite_de_retomar_nunca_diz_o_assunto_anterior():
    ags = Agente()
    for fala in ("Entre o Taylor 214ce e o Martin D-28E, qual você levaria pro palco?", "qual a captação de cada um?",
                 "tem desconto pra músico profissional? nota fiscal no CNPJ da minha banda?", "onde fica a loja?",
                 "qual o whatsapp?", "quero devolver um violão", "qual o horário?", "e o cnpj?"):
        assert "o assunto anterior" not in ags.responder("r1", fala, "eval").texto


def test_nao_convida_a_retomar_assunto_que_ja_foi_respondido():
    t = textos("Quanto fica o Tagima Memphis no pix?", "onde fica a loja? tem estacionamento?")
    assert "retomar" not in t[1]


def test_convida_a_retomar_o_assunto_nomeado_que_ainda_espera_dado():
    t = textos("quero devolver um violão", "qual o horário de vocês?")
    assert "a devolução" in t[1] and "Quer retomar?" in t[1]
