"""QA de conversas da Lia (etapa 11): correções gerais por intenção, estado e vocabulário."""
from __future__ import annotations

import pytest

from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="qa", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def textos(*mensagens, **kw):
    return [r.texto for r in conversar(*mensagens, **kw)]


# 1. próxima abertura com ressalva de feriado ---------------------------------------------------

@pytest.fixture
def quinta_noite(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-11-05T20:00:00")


def test_proxima_abertura_traz_ressalva_de_feriado(quinta_noite):
    saudacao, horario = textos("oi", "que horas vocês abrem?")
    for t in (saudacao, horario):
        assert "09:00" in t and "feriado" in t.lower()
    assert "o horário pode mudar" in saudacao


def test_horario_fechado_nao_se_contradiz(quinta_noite):
    (t,) = textos("qual o horário de vocês?")
    assert "feriado" in t.lower() and "o horário pode mudar" in t


# 2. número sozinho não identifica produto ---------------------------------------------------------

def test_numero_do_pedido_em_turno_separado_nao_vira_produto():
    t = textos("quero saber do meu pedido", "numero 8")
    assert "4 últimos dígitos" in t[1] and "preço de tabela" not in t[1]


def test_dias_desde_a_compra_nao_viram_produto():
    t = textos("comprei um violao e veio com defeito", "comprei faz 10 dias, a tarraxa nao segura a afinação")
    assert "preço de tabela" not in t[1] and "pedido" in t[1].lower()


def test_semana_depois_de_garantia_nao_pede_escolha_de_modelo():
    t = textos("meu ukulele caiu da escada e trincou, a garantia cobre?", "mas comprei faz so 1 semana")
    assert "modelo parecido" not in t[1]


def test_parcelas_sozinhas_nao_trocam_o_produto_em_foco():
    t = textos("preco do violao yamaha c70", "3x", "12x")
    assert "C70" in t[1] and "C70" in t[2]
    assert "Bass" not in t[1] + t[2]


def test_cep_na_mensagem_nao_vira_modelo_parecido():
    t = textos("quanto custa o Yamaha FG800?", "frete pro CEP 01310-100")
    assert "modelo parecido" not in t[1]


# 3. escopo depois da intenção ---------------------------------------------------------------------

ACESSORIOS = "não vendemos acessórios"


@pytest.mark.parametrize("pergunta", ["qual tem captação?", "esse tem captador?", "qual a diferença entre nylon e aço?"])
def test_caracteristica_do_instrumento_nao_vira_recusa_de_acessorio(pergunta):
    t = textos("quanto custa o Yamaha FG800?", pergunta)
    assert ACESSORIOS not in t[1] and "Não entendi" not in t[1]


def test_baixo_de_cinco_cordas_e_instrumento():
    (t,) = textos("preciso de um baixo 5 cordas ativo")
    assert ACESSORIOS not in t and "Bass" in t


def test_corda_arrebentada_responde_desgaste_natural():
    (t,) = textos("a corda arrebentou, cobre?")
    ref = t.lower()
    assert ACESSORIOS not in t and "desgaste natural" in ref and "garantia" in ref


def test_pedido_de_parecido_usa_o_produto_em_foco():
    t = textos("quanto custa o Yamaha C40?", "tem outro parecido?")
    assert ACESSORIOS not in t[1] and "Yamaha C40" in t[1] and "R$" in t[1]
    assert t[1].count("\n- ") >= 1


def test_parecido_mais_barato_respeita_o_preco_do_foco():
    t = textos("quanto custa o Yamaha C40?", "nao tem algo parecido mais barato?")
    assert "mais barato" in t[1] and ACESSORIOS not in t[1]


def test_precinho_e_objecao_de_preco_nao_recusa_de_acessorio():
    t = textos("quanto ta a Fender Stratocaster?", "tem como fazer um precinho?")
    assert ACESSORIOS not in t[1] and "desconto" not in t[1].lower().replace("sem desconto", "")


def test_queixa_de_atendimento_segue_a_reclamacao():
    t = textos("o vendedor foi grosso comigo na loja")
    assert ACESSORIOS not in t[0] and "Não entendi" not in t[0]


# 4. produto em foco em todo follow-up -------------------------------------------------------------

def test_objecao_de_preco_usa_o_produto_em_foco():
    t = textos("quanto ta o Martin D-28?", "nossa, muito caro")
    assert "Qual produto" not in t[1] and "Entendo" in t[1]


def test_essa_guitarra_no_pix_depois_de_assunto_lateral():
    t = textos("queria ver guitarras", "qual a mais barata?", "ah, e vocês abrem amanhã?",
               "voltando, essa guitarra no pix fica quanto?")
    assert "Telecaster" in t[3] and "PIX" in t[3] and "Qual produto" not in t[3]


def test_quanto_ele_fica_no_pix_entao():
    t = textos("o Ohana CK-20 quanto fica?", "ta bom, quanto ele fica no pix entao?")
    assert "Ohana CK-20" in t[1]


def test_quantidade_multiplica_o_produto_em_foco():
    t = textos("quanto custa o ukulele Shelby SU-21S?", "e se eu comprar dois?")
    assert "Qual produto" not in t[1] and "Para 2 unidades" in t[1] and "Shelby SU-21S" in t[1]
    assert "R$ 303,82" in t[1]  # 2 x R$ 151,91 (PIX, 5% sobre R$ 159,90)


def test_os_dois_soma_os_dois_ultimos_produtos_citados():
    t = textos("quanto custa o Yamaha C40?", "e o Shelby SN-100?", "quanto fica os dois?")
    assert "Yamaha C40" in t[2] and "Shelby SN-100" in t[2]
    assert "R$ 1.148,90" in t[2]  # 599,90 + 549,00 (preço de tabela)


@pytest.mark.parametrize("msg", ["caro", "tem algo mais barato?"])
def test_caro_e_mais_barato_usam_o_produto_em_foco(msg):
    t = textos("quanto custa o Yamaha C40?", msg)
    assert "Qual tipo de instrumento" not in t[1] and "Qual produto" not in t[1]


def test_esse_esta_em_promocao_responde_sobre_o_produto_em_foco():
    t = textos("quanto custa o Yamaha C40?", "esse ta em promocao?")
    assert "não está em promoção ativa" in t[1] and "Promoções ativas" not in t[1]


def test_acessorio_pedido_de_verdade_continua_recusado():
    for msg in ("vcs vendem cordas de violao?", "quanto custa uma palheta?", "quero comprar um cabo"):
        assert ACESSORIOS in textos(msg)[0]
