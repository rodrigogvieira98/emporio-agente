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
        assert "9h" in t and "feriado" in t.lower()
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


# 5. consulta de pedido em várias mensagens -------------------------------------------------------

def test_numero_e_final_em_turnos_separados_consultam_o_pedido(sql):
    t = textos("quero saber do meu pedido", "numero 4", "final 3456")
    assert "4 últimos dígitos" in t[1]
    assert "Por nada" not in t[2] and "Pedido 4" in t[2]


def test_final_do_telefone_sozinho_nunca_e_despedida():
    (t,) = textos("final 7821")
    assert "Por nada" not in t and "número do pedido" in t


def test_irritacao_no_meio_da_consulta_nao_abandona_a_consulta():
    t = textos("meu pedido nao chegou ainda e ja to puto", "pedido 8, ana carolina ferreira",
               "isso é um absurdo, quando chega?")
    assert "4 últimos dígitos" in t[2] and "Pode me contar em poucas palavras" not in t[2]


def test_depois_da_irritacao_o_final_conclui_a_consulta(sql):
    t = textos("meu pedido nao chegou ainda e ja to puto", "pedido 4", "isso é um absurdo, quando chega?", "3456")
    assert "Pedido 4" in t[3]


# 6. pós-venda ----------------------------------------------------------------------------------------

def test_dias_informados_pelo_cliente_aplicam_o_prazo_de_defeito():
    t = textos("minha guitarra deu defeito", "comprei faz 50 dias")
    assert "30 dias" in t[1] and "fabricante" in t[1] and "Não encontrei essa informação" not in t[1]


def test_dentro_do_prazo_continua_pedindo_o_pedido():
    t = textos("minha guitarra deu defeito", "comprei faz 10 dias")
    assert "fabricante" not in t[1] and "pedido" in t[1].lower()


@pytest.mark.parametrize("msg", ["o entregador ta aqui e a caixa do violao ta toda amassada",
                                 "o tampo do violao chegou rachado"])
def test_avaria_orienta_recusar_o_recebimento(msg):
    (t,) = textos(msg)
    assert "recusar o recebimento" in t and "Encontrei" not in t


def test_o_que_eu_faco_depois_da_avaria_continua_o_assunto():
    t = textos("o entregador ta aqui e a caixa do violao ta toda amassada", "o que eu faço??")
    assert "Não entendi" not in t[1]


def test_reembolso_em_quanto_tempo_responde_dez_dias_uteis():
    (t,) = textos("e o reembolso em quanto tempo?")
    assert "10 dias úteis" in t


def test_pedido_cancelado_explica_o_motivo_pela_observacao_do_pedido(sql):
    t = textos("pedido 17 telefone final 8765", "pq foi cancelado?")
    assert "cancelado" in t[0] and "Não entendi" not in t[1]
    assert "Pedido cancelado pelo cliente antes do processamento" in t[1]


def test_pedido_cancelado_com_pagamento_responde_sobre_reembolso(sql):
    t = textos("pedido 17 telefone final 8765", "quero meu dinheiro de volta")
    assert "10 dias úteis" in t[1] and "cancelado" in t[1] and "Ainda não consegui entender" not in t[1]


# 7. frete com produto conhecido -------------------------------------------------------------------

def test_frete_campo_grande_com_produto_barato_e_taxa_fixa():
    t = textos("quanto custa o ukulele Shelby SU-21S?", "moro em campo grande, quanto e o frete?")
    assert "taxa fixa de R$ 35,00" in t[1] and "valor aproximado do pedido" not in t[1]


def test_frete_campo_grande_com_produto_caro_e_gratis():
    t = textos("quanto custa o Martin D-28?", "e o frete pra campo grande?")
    assert "grátis" in t[1] and "valor aproximado do pedido" not in t[1]


def test_produto_e_cidade_na_mesma_frase_nao_pedem_o_valor():
    t = textos("moro em campo grande, quanto e o frete do ukulele Shelby SU-21S?", "e em quantos dias chega?")
    assert "taxa fixa de R$ 35,00" in t[0] and "Shelby SU-21S" in t[0]
    assert "Quantos Dias" not in t[1] and "1 a 3 dias úteis" in t[1]


def test_extrator_de_cidade_nao_aceita_pergunta_de_prazo():
    t = textos("quanto custa o Yamaha C40?", "e em quantos dias chega?")
    assert "Quantos" not in t[1]


def test_outra_cidade_com_produto_pede_o_cep_e_depois_estima():
    t = textos("quanto custa o Yamaha C40?", "e o frete para Dourados?", "79800-000")
    assert "cotação" in t[1] and "CEP" in t[1] and "Yamaha C40" in t[1]
    assert "Qual produto" not in t[2] and "qual é o produto" not in t[2]


def test_cidade_informada_antes_fica_no_estado():
    t = textos("moro em campo grande", "quanto custa o Martin D-28?", "e o frete?")
    assert "grátis" in t[2]


def test_grande_porte_diz_cotacao_individual():
    t = textos("quanto custa a bateria Pearl?", "e o frete para Cuiabá?")
    assert "individual" in t[1] or "cotação" in t[1]
    assert "Qual produto" not in t[1]


# 8. compra com produto em foco ---------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["quero esse", "quero fechar", "coloca no carrinho", "beleza, quero fechar", "vou levar"])
def test_compra_com_produto_em_foco_mostra_o_botao(msg):
    r = conversar("quanto custa o Yamaha F310?", msg)[1]
    assert any(x["tipo"] == "carrinho" for x in r.links), r.texto
    assert "Não entendi" not in r.texto and "eu não adiciono nada por você" in r.texto


def test_resposta_de_compra_nao_recebe_texto_livre_do_modelo():
    from emporio.agente.redacao import Redator

    from emporio.agente.llm import RespostaLlm

    class Modelo:
        chamadas = 0

        def conversar(self, modelo, mensagens, formato=None, limite=None, maximo_tokens=400):
            Modelo.chamadas += 1
            return RespostaLlm(conteudo='{"abertura": null, "fechamento": null}', tokens_prompt=1, tokens_resposta=1,
                               latencia_ms=1)

    agente = Agente(redator=Redator("m", cliente=Modelo()))
    conversar("quanto custa o Yamaha F310?", agente=agente)
    antes = Modelo.chamadas
    r = conversar("quero esse", conversa="qa", agente=agente)[0]
    assert Modelo.chamadas == antes and any(x["tipo"] == "carrinho" for x in r.links)


# 9. orçamento ----------------------------------------------------------------------------------------

def _precos(texto):
    import re
    return [int(a.replace(".", "")) for a in re.findall(r"R\$ (\d{1,3}(?:\.\d{3})*),\d\d", texto)]


def test_teto_dito_depois_da_busca_refina_a_lista():
    t = textos("quero um violao pro meu filho de 10 anos", "até 600 reais")
    assert "Qual produto" not in t[1] and "Crafter" not in t[1]
    assert _precos(t[1]) and max(_precos(t[1])) <= 600


def test_recomendacao_respeita_o_teto_informado():
    t = textos("quero um violao", "tenho 500 reais, qual voce indica?", "qual vc recomenda?")
    for texto in t[1:]:
        assert _precos(texto) and max(_precos(texto)) <= 500, texto
        assert "Qual tipo de instrumento" not in texto


def test_sem_produto_dentro_do_teto_nao_sugere_produto_acima():
    (t,) = textos("guitarra até 1000 reais")
    assert not _precos(t) or max(_precos(t)) <= 1000
    assert "Minha sugestão" not in t


def test_numero_sem_unidade_nao_vira_teto():
    t = textos("quero um violao", "tenho 2 filhos")
    assert not _precos(t[1]) or max(_precos(t[1])) > 100


# 10. promoção e cupom ---------------------------------------------------------------------------------

def test_promocao_citada_inativa_de_produto_recebe_nao_esta_ativa():
    (t,) = textos("a promocao de pascoa do Martin D-28 ainda ta valendo?")
    assert "não está ativa" in t and "Páscoa" in t.title().replace("Pascoa", "Páscoa")


def test_promocao_inativa_sem_produto_recebe_nao_esta_ativa():
    (t,) = textos("vai ter promocao de dia das maes?")
    assert "não está ativa" in t


def test_cupom_desconhecido_nao_existe():
    t = textos("e cupom PRIMEIRACOMPRA funciona?")
    assert "não existe esse cupom" in t[0].lower() and "Formas de pagamento" not in t[0]


def test_desconto_prometido_por_vendedor_nao_vira_produto():
    t = textos("vi no instagram que tem 30% de desconto de black friday no Tagima Woodstock",
               "mas o vendedor me prometeu 20% de desconto")
    assert "não está ativa" in t[0]
    assert "Ohana" not in t[1].split("Promoções ativas")[0] and "não consigo confirmar" in t[1].lower()


def test_nome_de_produto_com_promocao_citada_e_encontrado():
    t = textos("a promocao do Ohana CK-20 ainda esta valendo?")
    assert "Ohana CK-20" in t[0] and "20%" in t[0]


# 11. endereço de entrega do pedido -----------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["qual o endereço de entrega cadastrado?", "pra onde vai ser entregue meu pedido?",
                                 "me confirma o endereço do meu pedido"])
def test_endereco_de_entrega_do_pedido_nao_e_mostrado_nem_trocado_pelo_da_loja(sql, msg):
    t = textos("pedido 10, final 2109", msg)
    assert "Rua 14 de Maio" not in t[1] and "Estamos na" not in t[1]
    assert "privacidade" in t[1].lower()


def test_endereco_da_loja_continua_respondido():
    (t,) = textos("onde fica a loja?")
    assert "Rua 14 de Maio" in t


# 12. pedido de humano ----------------------------------------------------------------------------------

def test_pedido_de_humano_registra_com_protocolo(sql):
    (r,) = conversar("quero falar com um humano")
    assert "EM-" in r.texto
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1


def test_pedir_humano_no_meio_do_relato_de_irritacao_registra_atendente(sql):
    r = conversar("meu pedido nao chegou ainda e ja to puto", "isso é um absurdo, quando chega?",
                  "quero falar com um humano")
    assert "EM-" in r[2].texto or "sim ou não" in r[2].texto
    assert "Não entendi" not in r[2].texto


def test_sim_a_oferta_de_registro_registra_com_protocolo_e_prazo(sql):
    r = conversar("to muito insatisfeito com o atendimento de vcs", "sim")
    assert "EM-" in r[1].texto and "24 horas úteis" in r[1].texto
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1


# 13. limite por número de pedido na ferramenta -------------------------------------------------------------

def test_ferramenta_limita_tentativas_por_pedido_entre_conversas(sql, monkeypatch):
    from datetime import datetime, timedelta

    from emporio.ferramentas import pedidos
    from emporio.ferramentas.pedidos import consultar_pedido

    for i in range(pedidos.MAX_TENTATIVAS_POR_PEDIDO):  # cada conversa falha poucas vezes: o limite por conversa não pega
        r = consultar_pedido(pedido_id=4, final_telefone="0000", conversa_id=f"c{i // 2}")
        assert r.estado == "negado"
    certo = consultar_pedido(pedido_id=4, final_telefone="3456", conversa_id="nova")
    assert certo.estado == "negado" and certo.motivo == pedidos.MOTIVO_NEGADO  # nem o final correto passa na janela
    outro = consultar_pedido(pedido_id=5, final_telefone="0000", conversa_id="nova")
    assert outro.estado == "negado"  # outro pedido segue o fluxo normal (negado por dado errado, não bloqueado)


def test_limite_por_pedido_expira_depois_da_janela(sql, monkeypatch):
    from emporio.ferramentas import pedidos
    from emporio.ferramentas.pedidos import consultar_pedido

    for i in range(pedidos.MAX_TENTATIVAS_POR_PEDIDO):
        consultar_pedido(pedido_id=4, final_telefone="0000", conversa_id=f"d{i // 2}")
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-31T12:30:00")  # passou a janela
    assert consultar_pedido(pedido_id=4, final_telefone="3456", conversa_id="nova").estado == "ok"


# 14. insulto, caixa alta e inglês ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["vcs sao uns lixos, porra", "VOCES SAO MUITO LENTOS", "que merda de loja"])
def test_insulto_ou_queixa_recebe_acolhimento_e_oferta_de_atendente(sql, msg):
    (r,) = conversar(msg)
    assert "Não entendi" not in r.texto and "atendente" in r.texto and "sim ou não" in r.texto
    assert len(r.texto) < 200 and r.texto.count("?") == 1
    assert r.estado == "aguardando:confirmacao_registro"


def test_sim_depois_do_acolhimento_registra_o_chamado(sql):
    r = conversar("vcs sao uns lixos, porra", "sim")
    assert "EM-" in r[1].texto and sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1


def test_nao_depois_do_acolhimento_nao_registra(sql):
    r = conversar("vcs sao uns lixos, porra", "nao")
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 0


@pytest.mark.parametrize("msg,tema", [("hi, do you ship to Portugal?", "frete"),
                                       ("what is the price of the Fender Stratocaster?", "preço"),
                                       ("what time do you open?", "horário")])
def test_ingles_recebe_resposta_curta_em_portugues_com_o_tema(msg, tema):
    (r,) = conversar(msg)
    assert "em português" in r.texto and tema in r.texto and "Não entendi" not in r.texto
    assert len(r.texto) < 250 and "Nosso horário de funcionamento" not in r.texto


def test_agradecimento_em_ingles_nao_repete_o_preco():
    t = textos("quanto custa o Yamaha C40?", "ok thanks")
    assert "preço de tabela" not in t[1]


@pytest.mark.parametrize("msg", ["quanto custa o Yamaha C40?", "oi", "tem violao?"])
def test_portugues_nao_vira_ingles(msg):
    (r,) = conversar(msg)
    assert "em português" not in r.texto


# 15. comparação de dois produtos ----------------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["qual a diferença entre o Yamaha C40 e o Yamaha C70?", "Yamaha C40 vs Yamaha C70",
                                 "quero comparar o Yamaha C40 com o C70"])
def test_comparacao_mostra_os_dois_com_preco(msg):
    (r,) = conversar(msg)
    assert "Yamaha C40" in r.texto and "Yamaha C70" in r.texto
    assert "R$ 599,90" in r.texto and "R$ 849,00" in r.texto
    assert "Não encontrei" not in r.texto


def test_comparacao_nao_escolhe_o_melhor_por_conta_propria():
    (r,) = conversar("o Music Man 4X vs o Yamaha 3X, qual melhor pra slap?")
    assert "Music Man Bass 4X" in r.texto and "Yamaha Bass 3X" in r.texto
    assert "R$ 7.157,00" in r.texto and "R$ 11.445,00" in r.texto


def test_comparacao_com_produto_inexistente_nao_inventa():
    (r,) = conversar("qual a diferença entre o Yamaha C40 e o Zebra Z999?")
    assert "R$" not in r.texto.split("Zebra")[-1] or "não encontrei" in r.texto.lower()


# 16. pergunta dupla ------------------------------------------------------------------------------------------

def test_preco_e_frete_na_mesma_mensagem_respondem_as_duas():
    (r,) = conversar("qual o preço do Yamaha C40 e vcs entregam em Dourados?")
    assert "R$ 599,90" in r.texto and "Dourados" in r.texto
    assert "cotação" in r.texto or "CEP" in r.texto


def test_frete_primeiro_e_preco_depois_tambem_respondem_as_duas():
    (r,) = conversar("vcs entregam em Dourados? quanto custa o Yamaha C40?")
    assert "R$ 599,90" in r.texto and "Dourados" in r.texto


def test_pix_e_parcelas_respondem_as_duas():
    (r,) = conversar("quanto fica o Yamaha APX600 no pix e em 10x?")
    assert "PIX" in r.texto and "10x" in r.texto
    assert "R$ 1.804,05" in r.texto and "R$ 189,90" in r.texto  # 1899 -5% e 1899/10
    assert "Tive um problema" not in r.texto


def test_combinar_formas_abaixo_de_dois_mil_responde_pela_regra():
    (r,) = conversar("posso pagar metade no pix e metade no cartao o Yamaha FG800?")
    assert "R$ 2.000,00" in r.texto and "Yamaha FG800" in r.texto
    assert "não" in r.texto.lower()


def test_combinar_formas_acima_de_dois_mil_pode():
    (r,) = conversar("posso pagar metade no pix e metade no cartao o Takamine GD20?")
    assert "R$ 2.000,00" in r.texto and "pode" in r.texto.lower()


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
