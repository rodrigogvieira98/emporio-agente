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


# --- item 2: convite de retomar -----------------------------------------------------------------

def test_sem_convite_quando_o_assunto_anterior_era_so_um_produto_a_nomear():
    rs = conversar("dá pra pagar metade no pix e metade no cartão? o violão custa 1299", "e num de 1700?",
                   "pix tem desconto?", conversa="e23r1")
    assert "Quer retomar" not in rs[-1].texto, rs[-1].texto


def test_sem_convite_quando_o_assunto_anterior_era_escolha_entre_modelos_parecidos():
    rs = conversar("quero o Rozini", "qual o horário de vocês?", conversa="e23r2")
    assert "Achei mais de um modelo" in rs[0].texto
    assert "Quer retomar" not in rs[1].texto, rs[1].texto


def test_convite_so_uma_vez_por_assunto():
    rs = conversar("quero devolver o violão que comprei, ainda tá na caixa", "que horas vocês fecham?", "sim",
                   "onde fica a loja?", conversa="e23r3")
    assert "Quer retomar" in rs[1].texto
    assert "4 últimos" in rs[2].texto
    assert "Rua 14 de Maio" in rs[3].texto and "Quer retomar" not in rs[3].texto, rs[3].texto


def test_convite_continua_quando_falta_dado_de_pos_venda_que_o_cliente_pode_dar():
    rs = conversar("quero trocar a guitarra que comprei online, ainda na caixa", "qual o endereço da loja?", conversa="e23r4")
    assert "Quer retomar" in rs[1].texto


# --- item 3: pergunta sobre o produto ----------------------------------------------------------

def _nao_entendi(r) -> bool:
    return "Não entendi" in r.texto or "Ainda não consegui entender" in r.texto


def test_teclas_pela_ficha_com_produto_nomeado_e_em_foco():
    rs = conversar("quanto custa o Teclado Korg Synth 1 Pro?", "quantas teclas ele tem?", conversa="e23f1")
    assert "61 teclas" in rs[1].texto and not _nao_entendi(rs[1]), rs[1].texto
    (r,) = conversar("e o Nord Synth 2 Pro, tem quantas teclas?", conversa="e23f1")
    assert "Nord Synth 2 Pro" in r.texto and "61 teclas" in r.texto, r.texto


def test_dado_divergente_entre_ficha_e_descricao_aparece_nos_dois():
    (r,) = conversar("o Korg Synth 1 Pro tem quantas teclas?", conversa="e23f2")
    assert "61" in r.texto and "88" in r.texto, r.texto  # ficha diz 61, a descrição do mesmo cadastro fala em 88


def test_pecas_e_ferragem_da_bateria_na_mesma_pergunta():
    rs = conversar("tem a Bateria Acústica Yamaha Kit 1 Studio?", "o kit 1 cabe em quantas peças e vem com ferragem?",
                   conversa="e23f3")
    t = rs[1].texto
    assert "5 peças" in t and "ferragens" in t.lower() and "inclu" in t.lower(), t


def test_cordas_pela_ficha():
    (r,) = conversar("quantas cordas tem o Yamaha Bass 3X?", conversa="e23f4")
    assert "4 cordas" in r.texto and not _nao_entendi(r), r.texto


def test_captacao_do_violao_pela_ficha():
    rs = conversar("quero ver o Yamaha C40", "ele tem captação?", conversa="e23f5")
    assert "Yamaha C40" in rs[1].texto and ("não tem" in rs[1].texto.lower() or "sem" in rs[1].texto.lower()), rs[1].texto
    (r,) = conversar("e o Tagima Vegas Elétrico, tem captação?", conversa="e23f5")
    assert "captação" in r.texto.lower() and "ativa" in r.texto.lower(), r.texto


@pytest.mark.parametrize("pergunta", [
    "o Yamaha C70 é pra quem já toca?",
    "o Yamaha C70 serve para iniciante?",
    "qual o nível do Yamaha C70?",
])
def test_nivel_indicado_pela_descricao(pergunta):
    (r,) = conversar(pergunta, conversa="e23f6")
    assert "intermediário" in r.texto and "Yamaha C70" in r.texto and not _nao_entendi(r), r.texto


def test_nivel_com_produto_em_foco_e_demonstrativo():
    rs = conversar("quanto custa o Yamaha C70?", "esse é bom pra quem tá começando?", conversa="e23f7")
    assert "intermediário" in rs[1].texto and not _nao_entendi(rs[1]), rs[1].texto


def test_sem_o_dado_diz_que_nao_tem_a_informacao_e_nao_inventa():
    (r,) = conversar("o Yamaha FG800 serve pra iniciante?", conversa="e23f8")
    assert "Não tenho essa informação" in r.texto and "Yamaha FG800" in r.texto, r.texto
    assert "iniciante" not in r.texto.replace("serve pra iniciante", "").lower() or "não tenho" in r.texto.lower()


@pytest.mark.parametrize("pergunta", ["e em quantas vezes dá?", "em quantas vezes sem juros dá pra fazer?",
                                      "até quantas parcelas?"])
def test_quantas_vezes_mostra_a_maior_parcela_valida(pergunta):
    rs = conversar("quanto custa o Yamaha C70?", pergunta, conversa="e23f9")
    assert "No crédito em 8x" in rs[1].texto and "R$ 106,13" in rs[1].texto, rs[1].texto


def test_quantas_vezes_sem_produto_em_foco_segue_sendo_pergunta_geral_de_pagamento():
    (r,) = conversar("em quantas vezes posso parcelar?", conversa="e23f10")
    assert "até 12x sem juros" in r.texto, r.texto


def test_diferenca_entre_o_produto_em_foco_e_outro_citado_usa_a_comparacao():
    rs = conversar("quanto custa o Shelby SU-21S?", "e qual a diferença dele pro Kala KA-15S?", conversa="e23f11")
    t = rs[1].texto
    assert t.startswith("Comparando os dois") and "Shelby SU-21S" in t and "Kala KA-15S" in t, t


# --- item 4: números com contexto ------------------------------------------------------------------

@pytest.mark.parametrize("fala", ["se eu levar 2 quanto dá?", "e se eu comprar 2?", "quero levar duas unidades, quanto fica?"])
def test_quantidade_multiplica_o_produto_em_foco(fala):
    rs = conversar("quero o Kalani KAL-700T", fala, conversa="e23n1")
    t = rs[1].texto
    assert "Kalani KAL-700T" in t and "646,20" in t and "Achei mais de um modelo" not in t, t


@pytest.mark.parametrize("fala", ["o 2", "2", "opção 2", "a 2", "quero o 2"])
def test_escolha_em_lista_numerada(fala):
    rs = conversar("quero o Rozini", fala, conversa="e23n2")
    assert "1) " in rs[0].texto
    assert "Rozini RV-174" in rs[1].texto and "Achei mais de um modelo" not in rs[1].texto, rs[1].texto


def test_numero_sozinho_sem_lista_nao_e_produto():
    (r,) = conversar("o 2", conversa="e23n3")
    assert "Pearl Kit 2" not in r.texto and "Nord Synth 2" not in r.texto, r.texto


@pytest.mark.parametrize("fala", ["4 últimos 7654", "os 4 últimos dígitos são 7654", "4 ultimos 7654"])
def test_quatro_ultimos_e_identificacao_nao_numero_de_pedido(fala):
    rs = conversar("oi meu pedido 18 foi cancelado? pq?", fala, conversa="e23n4")
    assert "Pedido 18 foi cancelado" in rs[1].texto, rs[1].texto


def test_quatro_ultimos_com_pedido_ja_em_foco_nao_pede_o_numero_de_novo():
    rs = conversar("pedido 18 final 7654", "4 últimos 7654", conversa="e23n5")
    assert "Pedido 18" in rs[1].texto and "Qual é o número do pedido" not in rs[1].texto, rs[1].texto


def test_valor_citado_nao_entra_na_busca_de_produto():
    rs = conversar("vi esse Yamaha F310 por 620 na internet, vcs cobrem?", conversa="e23n6")
    assert "Não encontrei esse produto" not in rs[0].texto and "Yamaha F310" in rs[0].texto, rs[0].texto


@pytest.mark.parametrize("fala", ["dá pra pagar metade no pix e metade no cartão? o violão custa 1299",
                                  "e num de 1700?"])
def test_preco_dito_pelo_cliente_nao_vira_modelo(fala):
    (r,) = conversar(fala, conversa="e23n7")
    assert "Não encontrei esse produto" not in r.texto, r.texto


def test_data_dita_como_dia_nao_entra_na_busca_e_vira_data():
    from emporio.agente.estado import Estado
    from emporio.agente.percepcao import extrair_slots

    est = Estado()
    s = extrair_slots("foi dia 27 de outubro, nao usei nada, posso trocar?", "foi dia 27 de outubro, não usei nada, posso trocar?", est)
    assert not s.get("referencia") and not s.get("termo"), s
    assert [d.isoformat() for d, _ in s["datas"]] == ["2026-10-27"], s["datas"]


# --- item 5: filtros acumulados e destino de frete no estado ----------------------------------------

def _nomes_listados(texto: str) -> list[str]:
    return re.findall(r"^- (.+?): R\$", texto, flags=re.M)


def test_filtros_somam_numa_busca_em_andamento():
    rs = conversar("queria um violão", "já toco, quero de aço", "com captação", "até 1500", conversa="e23b1")
    assert "Yamaha F310" in rs[1].texto and "Tagima Memphis AC-39" not in rs[1].texto, rs[1].texto  # aço pela ficha
    assert "Shelby SGD-195E" in rs[2].texto and "Yamaha F310" not in rs[2].texto, rs[2].texto  # aço e captação
    assert _nomes_listados(rs[3].texto) == ["Shelby SGD-195E Elétrico Aço Sunburst", "Tagima Vegas Elétrico Aço Natural"], rs[3].texto
    assert "Encontrei 2 opções" in rs[3].texto


def test_filtro_do_mesmo_tipo_troca_o_anterior():
    rs = conversar("queria um violão", "de aço", "e de nylon?", conversa="e23b2")
    nomes = _nomes_listados(rs[2].texto)
    assert nomes and all("Aço" not in n for n in nomes), rs[2].texto
    assert "Tagima Memphis AC-39 Nylon Natural" in nomes


def test_cor_e_faixa_somam():
    rs = conversar("queria um violão", "tem preto?", "até 600 reais", conversa="e23b3")
    assert _nomes_listados(rs[2].texto) == ["Shelby SN-100 Folk Aço Preto"], rs[2].texto


def test_o_que_nao_existe_no_catalogo_e_dito():
    rs = conversar("quero ver guitarras", "de nylon", conversa="e23b4")
    t = rs[1].texto
    assert t.startswith("Não encontrei") and "nylon" in t.lower() and "guitarra" in t.lower(), t
    assert "Encontrei" not in t.replace("Não encontrei", "")


def test_filtros_na_primeira_mensagem():
    (r,) = conversar("quero um violão de aço com captação até 1000", conversa="e23b5")
    assert _nomes_listados(r.texto) == ["Shelby SGD-195E Elétrico Aço Sunburst"], r.texto


def test_destino_do_frete_fica_no_estado_e_o_produto_retoma_a_cidade():
    rs = conversar("quanto é o frete pra Dourados?", "é de um violão Yamaha C40", conversa="e23b6")
    t = rs[1].texto
    assert "Dourados" in t and "Yamaha C40" in t and "CEP" in t, t
    assert "Em Campo Grande" not in t


def test_qual_chega_mais_rapido_responde_pelos_prazos():
    rs = conversar("quanto é o frete pra Dourados?", "é de um violão Yamaha C40", "qual chega mais rápido?",
                   conversa="e23b7")
    t = rs[2].texto
    assert "SEDEX" in t and "2 a 5 dias úteis" in t and not _nao_entendi(rs[2]), t


def test_outra_cidade_depois_de_pergunta_de_frete_com_produto():
    rs = conversar("quanto é o frete pra Dourados?", "é de um violão Yamaha C40", "e pra São Paulo capital?",
                   conversa="e23b8")
    assert re.search(r"S[aã]o Paulo", rs[2].texto) and "Yamaha C40" in rs[2].texto and not _nao_entendi(rs[2]), rs[2].texto


# --- item 6: pós-venda com ação ---------------------------------------------------------------------

@pytest.mark.parametrize("fala", ["quero cancelar meu pedido 13, desisti", "cancela o pedido 13 pra mim",
                                  "como faço pra cancelar meu pedido?", "preciso cancelar a compra"])
def test_cancelar_pedido_diz_que_nao_e_feito_aqui_e_oferece_atendente(sql, fala):
    (r,) = conversar(fala, conversa="e23p1")
    t = r.texto
    assert "cancel" in t.lower() and "por aqui" in t and "atendente" in t and "Responda sim ou não" in t, t
    assert "4 últimos" not in t
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 0


def test_cancelar_pedido_aceito_registra_o_chamado(sql):
    conversar("quero cancelar meu pedido 13", conversa="e23p2")
    (r,) = conversar("sim", conversa="e23p2")
    assert "Protocolo" in r.texto
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1


def test_pedido_ja_cancelado_nao_e_pedido_de_cancelamento():
    (r,) = conversar("oi meu pedido 18 foi cancelado? pq?", conversa="e23p3")
    assert "4 últimos" in r.texto


@pytest.mark.parametrize("fala", ["quanto tempo pra me darem retorno?", "qual o prazo de retorno do atendimento?",
                                  "em quanto tempo vocês me respondem?"])
def test_prazo_de_retorno_responde_24_horas_uteis(fala):
    (r,) = conversar(fala, conversa="e23p4")
    assert "24 horas úteis" in r.texto and not _nao_entendi(r), r.texto


def test_garantia_depois_dos_30_dias_informa_legal_fabricante_e_intermediacao():
    rs = conversar("meu violão parou de funcionar a captação, faz uns 2 meses que recebi, tem garantia?", conversa="e23p5")
    t = rs[0].texto
    assert "90 dias" in t and "fabricante" in t and "intermediar" in t, t


def test_garantia_pergunta_de_acompanhamento_sobre_a_loja_fazer_por_mim():
    rs = conversar("meu violão parou de funcionar, faz 2 meses que recebi, tem garantia?",
                   "e a loja faz isso por mim?", conversa="e23p6")
    assert "intermediar" in rs[1].texto and not _nao_entendi(rs[1]), rs[1].texto


def test_devolucao_fora_do_prazo_aplica_a_regra_ao_que_o_cliente_disse():
    rs = conversar("quero devolver um ukulele que comprei faz 15 dias, já usei um pouco, recebi dia 15 do mês passado",
                   "então não dá mais pra devolver, né?", "mas posso trocar por outro modelo?", conversa="e23p7")
    assert "7 dias" in rs[0].texto and "fora do prazo" in rs[0].texto and "Para consultar o pedido" not in rs[0].texto, rs[0].texto
    assert "fora do prazo" in rs[1].texto, rs[1].texto
    assert "troca" in rs[2].texto.lower() and "fora do prazo" in rs[2].texto, rs[2].texto


def test_pedido_nao_entregue_nao_pergunta_a_data_de_recebimento():
    rs = conversar("cadê meu pedido 8", "7821", "quero devolver, quero meu dinheiro de volta", conversa="e23p8")
    assert "Pedido 8 foi enviado" in rs[1].texto
    assert "data em que você recebeu" not in rs[2].texto, rs[2].texto
    assert "fora do prazo" not in rs[2].texto


@pytest.mark.parametrize("fala", ["comprei um violão preto e veio sunburst, vocês mandaram errado",
                                  "mandaram o produto errado, pedi um e veio outro"])
def test_envio_errado_e_tratado_como_defeito_do_pedido(fala):
    (r,) = conversar(fala, conversa="e23p9")
    assert "troca por defeito" in r.texto, r.texto


# --- item 7: intenções erradas -----------------------------------------------------------------------

@pytest.mark.parametrize("fala", ["quanto precisa comprar pra ser grátis?", "a partir de quanto o frete fica grátis?"])
def test_pra_ser_gratis_nao_e_cidade_e_responde_a_regra_do_frete(fala):
    rs = conversar("moro em campo grande, frete é grátis?", fala, conversa="e23i1")
    t = rs[1].texto
    assert "Ser Gratis" not in t and "R$ 500,00" in t and "R$ 35,00" in t, t


@pytest.mark.parametrize("fala", ["fazem regulagem de guitarra?", "vocês dão aula de música?", "vocês fazem conserto de violão?"])
def test_servico_sem_dado_recebe_nao_tenho_essa_informacao(fala):
    (r,) = conversar(fala, conversa="e23i2")
    assert "Não tenho essa informação" in r.texto and "Encontrei" not in r.texto, r.texto


def test_loja_parceira_nao_e_indicada():
    (r,) = conversar("qual loja vocês indicam pra comprar um violão barato?", conversa="e23i3")
    assert "Não tenho essa informação" in r.texto and "parceira" in r.texto and "Encontrei" not in r.texto, r.texto


def test_loja_para_acessorio_recebe_o_escopo_e_nao_indicamos_loja():
    (r,) = conversar("qual loja vocês indicam pra comprar amp?", conversa="e23i3b")
    assert "não vendemos acessórios" in r.texto and "lojas parceiras" in r.texto and "Encontrei" not in r.texto, r.texto


def test_data_comemorativa_cita_a_campanha_do_manual_sem_prometer_valor():
    rs = conversar("vai ter black friday?", "de quanto vai ser o desconto?", conversa="e23i4")
    assert "Black Friday (Novembro)" in rs[0].texto and "não está ativa" in rs[0].texto, rs[0].texto
    assert "%" not in rs[0].texto
    assert "não posso prometer" in rs[1].texto.lower() and "15%" not in rs[1].texto and "30%" not in rs[1].texto, rs[1].texto


def test_dia_do_musico_cita_a_campanha_do_manual():
    (r,) = conversar("a promoção do dia do músico vale pra quem?", conversa="e23i5")
    assert "Semana do Músico" in r.texto and "22 de novembro" in r.texto and "não está ativa" in r.texto, r.texto
    assert "Promoções ativas" not in r.texto.split("Se quiser")[0]


@pytest.mark.parametrize("fala", ["vcs passam meu telefone pra alguém?", "vocês vendem meus dados?",
                                  "compartilham meu e-mail com terceiros?"])
def test_passam_meu_dado_responde_privacidade(fala):
    (r,) = conversar(fala, conversa="e23i6")
    assert "dados pessoais" in r.texto and "Telefone: (67)" not in r.texto, r.texto
