"""Agente por regras: conversas completas, laço, validação e persistência."""
from __future__ import annotations

import json

import pytest

from emporio import config
from emporio.agente.decisor import Decisor
from emporio.agente.estado import Acao, Estado, carregar_estado
from emporio.agente.laco import MAX_PASSOS, Agente
from emporio.agente.percepcao import perceber
from emporio.agente.regras import RegrasDecisor

PEDIDO, FINAL = 4, "3456"


def conversar(*mensagens, conversa="c1", origem="eval", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, origem) for m in mensagens]


def protocolos(sql):
    return [r["protocolo"] for r in sql.execute("SELECT protocolo FROM chamados ORDER BY id")]


# --- conversa completa de devolução do pedido 4 -------------------------------------------

def test_devolucao_do_pedido_4_conversa_completa(sql):
    r1, r2, r3, r4 = conversar(
        "Oi, quero devolver um violão que comprei",
        f"o pedido é o {PEDIDO} e o final do telefone é {FINAL}",
        "foi compra online, recebi em 15/12/2025 e está na caixa, sem uso",
        "sim, pode registrar")
    # 1) pergunta o pedido
    assert "número do pedido" in r1.texto and r1.estado == "aguardando:pedido"
    # 2) pergunta canal, data e estado
    assert "online ou na loja" in r2.texto and "data em que você recebeu" in r2.texto and "estado do produto" in r2.texto
    assert r2.estado == "aguardando:dados_posvenda"
    assert [a["ferramenta"] for a in r1.acoes if "ferramenta" in a] == ["consultar_politica", "consultar_politica"]  # exceções e regra, antes de pedir o pedido
    assert [a["ferramenta"] for a in r2.acoes if "ferramenta" in a] == ["consultar_pedido"]
    # 3) propõe registro separando sistema, declarado e equipe, sem afirmar elegibilidade
    assert "O que consta no seu pedido" in r3.texto and "R$ 799,90" in r3.texto
    assert "(não verificado)" in r3.texto and "compra online" in r3.texto and "15/12/2025" in r3.texto
    assert "O que a equipe confirma" in r3.texto and "Posso registrar" in r3.texto
    assert "Eu não consigo garantir a elegibilidade" in r3.texto
    assert r3.estado == "aguardando:confirmacao_registro"
    # chamado só é anunciado depois do ok da ferramenta
    for r in (r1, r2, r3):
        assert "chamado registrado" not in r.texto.lower() and "protocolo:" not in r.texto.lower()
    assert protocolos(sql) == ["EM-000001"] and "EM-000001" in r4.texto
    assert "Chamado registrado" in r4.texto and r4.estado == "encaminhado"
    assert "24 horas" not in r4.texto  # prazo de 24h úteis é só de reclamação
    chamado = sql.execute("SELECT * FROM chamados").fetchone()
    assert chamado["tipo"] == "atendente" and "pedido 4" in chamado["resumo"]
    assert "nao verificado" in chamado["resumo"] and "Elegibilidade a confirmar" in chamado["resumo"]


def test_dados_declarados_ficam_marcados_e_separados_do_que_o_sistema_confirmou():
    conversar("quero devolver", f"pedido {PEDIDO} final {FINAL}", "online, recebi dia 15/12/2025, sem uso")
    estado = carregar_estado("c1")
    assert estado.declarados["canal_compra"] == {"valor": "online", "origem": "declarado"}
    assert estado.declarados["data_recebimento"]["origem"] == "declarado"
    assert estado.coletados["pedido"]["total_gravado_centavos"] == 79990  # veio da ferramenta
    assert "pedido" not in estado.declarados


def test_nao_afirma_elegibilidade_nunca():
    textos = " ".join(r.texto for r in conversar(
        "quero devolver", f"pedido {PEDIDO} final {FINAL}", "online, recebi dia 15/12/2025, na caixa sem uso")).lower()
    for proibida in ("você tem direito", "pode devolver", "está dentro do prazo", "devolução aprovada", "elegível"):
        assert proibida not in textos


def test_falha_ao_registrar_nao_anuncia_chamado(sql):
    conversar("quero devolver", f"pedido {PEDIDO} final {FINAL}", "online, recebi dia 15/12/2025, na caixa")
    sql.execute("DROP TABLE chamados")
    sql.commit()
    r = conversar("sim", conversa="c1")[0]
    assert "Protocolo" not in r.texto and "Chamado registrado" not in r.texto
    assert "ainda não existe protocolo" in r.texto and r.estado != "encaminhado"


# --- reclamação, atendente e negações -----------------------------------------------------

def test_nao_quero_abrir_reclamacao_nao_registra(sql):
    (r,) = conversar("Não quero abrir reclamação")
    assert protocolos(sql) == [] and "não vou abrir reclamação" in r.texto


def test_quero_abrir_reclamacao_registra_com_prazo_de_24h(sql):
    agente = Agente()
    r1 = agente.responder("c1", "quero abrir reclamação", "eval")
    assert r1.estado == "aguardando:relato" and protocolos(sql) == []
    r2 = agente.responder("c1", "o pedido 8 chegou quebrado e ninguém me respondeu", "eval")
    assert protocolos(sql) == ["EM-000001"]
    assert "Chamado registrado" in r2.texto and "24 horas úteis" in r2.texto
    assert sql.execute("SELECT tipo FROM chamados").fetchone()[0] == "reclamacao"


def test_reclamacao_com_detalhe_na_mesma_frase_registra_direto(sql):
    (r,) = conversar("quero abrir uma reclamação porque o pedido 8 atrasou muito e ninguém avisou")
    assert "EM-000001" in r.texto and "24 horas úteis" in r.texto


def test_insatisfacao_sem_pedido_explicito_pede_confirmacao_antes_de_registrar(sql):
    agente = Agente()
    r1 = agente.responder("c1", "estou muito insatisfeito com o atendimento de vocês", "eval")
    assert r1.estado == "aguardando:confirmacao_registro" and protocolos(sql) == []
    r2 = agente.responder("c1", "sim", "eval")
    assert protocolos(sql) == ["EM-000001"] and "24 horas úteis" in r2.texto


def test_recusar_a_proposta_nao_registra(sql):
    r1, r2 = conversar("estou muito insatisfeito com o atendimento de vocês", "não")
    assert r1.estado == "aguardando:confirmacao_registro"
    assert protocolos(sql) == [] and "não registrei nada" in r2.texto


def test_pedido_de_atendente_registra_e_negacao_nao_encaminha(sql):
    (r,) = conversar("quero falar com um atendente")
    assert "Chamado registrado" in r.texto and "24 horas" not in r.texto
    assert sql.execute("SELECT tipo FROM chamados").fetchone()[0] == "atendente"
    (n,) = conversar("não quero falar com atendente", conversa="c2")
    assert protocolos(sql) == ["EM-000001"] and "sigo te ajudando" in n.texto


def test_mesmo_pedido_repetido_nao_duplica_chamado(sql):
    conversar("quero falar com um atendente", "quero falar com um atendente")
    assert len(protocolos(sql)) == 1  # mesma conversa, chamado em aberto: o segundo pedido informa o protocolo
    r = conversar("sim", conversa="c9")[0]
    assert len(protocolos(sql)) == 1 and "Não entendi" in r.texto


def test_fora_do_expediente_informa_horario_de_retorno(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-11-01T10:00:00")  # domingo
    (r,) = conversar("quero falar com um atendente")
    assert "fora do expediente" in r.texto and "amanhã às 09:00" in r.texto
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-31T15:00:00")  # sábado à tarde
    (r2,) = conversar("quero falar com um atendente", conversa="c2")
    assert "segunda-feira às 09:00" in r2.texto
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-30T12:00:00")  # sexta ao meio-dia
    (r3,) = conversar("quero falar com um atendente", conversa="c3")
    assert "fora do expediente" not in r3.texto


def test_saudacao_fora_do_expediente_e_com_nome_da_loja_vindo_do_manual(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-30T07:30:00")  # sexta cedo
    (r,) = conversar("bom dia")
    assert "Lia" in r.texto and "assistente virtual" in r.texto and "hoje às 09:00" in r.texto


# --- escopo, produtos e preços ------------------------------------------------------------

def test_fora_de_escopo_explica_e_nao_cita_loja_parceira():
    for pergunta in ("vocês vendem cordas de violão?", "quanto custa uma palheta?", "tem amplificador?"):
        (r,) = conversar(pergunta, conversa=pergunta)
        assert "só com instrumentos" in r.texto and "parceira" not in r.texto.lower()


def test_preco_crafter_ht100_com_promocao_ativa():
    (r,) = conversar("quanto custa o Crafter HT-100?")
    assert "R$ 2.399,00" in r.texto and "18%" in r.texto and "R$ 1.967,18" in r.texto
    assert {f.atributo for f in r.fatos} >= {"final_centavos", "percentual"}


def test_preco_takamine_gd20_sem_promocao_no_pix():
    (r,) = conversar("e o Takamine GD20 no pix?")
    assert "R$ 2.199,00" in r.texto and "R$ 2.089,05" in r.texto and "promoção" not in r.texto


def test_takamine_ambiguo_lista_quatro_e_aceita_o_numero():
    r1, r2 = conversar("qual o preço do Takamine?", "2")
    assert r1.estado == "aguardando:escolha_produto"
    assert all(f"{i})" in r1.texto for i in (1, 2, 3, 4)) and "5)" not in r1.texto
    assert "Takamine GC5CE" in r2.texto and "R$ 3.299,00" in r2.texto


def test_shelby_em_6x_pede_confirmacao_da_equipe_e_registra_duvida(sql):
    r1, r2 = conversar("Shelby SN-100 em 6x", "sim")
    assert "precisa de confirmação da nossa equipe" in r1.texto
    assert "R$ 91,50" in r1.texto
    assert sql.execute("SELECT tipo FROM chamados").fetchone()[0] == "duvida_politica" and "EM-000001" in r2.texto


def test_busca_de_violoes_ate_mil_reais_mostra_total_e_cinco_itens():
    (r,) = conversar("quero um violão até R$ 1000")
    assert "Encontrei 12 opções" in r.texto and "mostrando 5" in r.texto
    assert r.texto.count("\n- ") == 5


def test_busca_sem_resultado_e_produto_inexistente():
    (r,) = conversar("tem flauta?")
    assert "Não encontrei" in r.texto
    (p,) = conversar("quanto custa o Gibson Flying V?", conversa="outra")
    assert "Não encontrei esse produto" in p.texto and p.estado == "aguardando:referencia_produto"


def test_disponibilidade_vem_do_estoque_do_sistema():
    (r,) = conversar("o Giannini GF-3D está disponível?")
    assert "esgotado" in r.texto


# --- pedido ---------------------------------------------------------------------------------

def test_status_do_pedido_mostra_total_gravado_mesmo_divergente(sql):
    tel = sql.execute("SELECT c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = 3").fetchone()[0]
    final = "".join(ch for ch in tel if ch.isdigit())[-4:]
    (r,) = conversar(f"qual o status do pedido 3, final {final}")
    assert "R$ 3.450,00" in r.texto and "R$ 3.498,00" not in r.texto
    assert "cartão de crédito em 12x" in r.texto and "entregue" in r.texto


def test_final_errado_nao_revela_nada_do_pedido():
    (r,) = conversar("onde está o pedido 8? final 0000")
    assert "Não consegui validar" in r.texto and "Kala" not in r.texto


def test_pedido_8_com_final_correto(sql):
    tel = sql.execute("SELECT c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = 8").fetchone()[0]
    final = "".join(ch for ch in tel if ch.isdigit())[-4:]
    (r,) = conversar(f"rastreio do pedido 8 final {final}")
    assert "enviado" in r.texto and "28/02/2026" in r.texto and "já passou" in r.texto and "Posso" not in r.texto.split("registre")[0]
    assert r.estado == "aguardando:confirmacao_registro"


def test_negado_igual_para_pedido_inexistente_e_final_errado():
    (a,) = conversar("pedido 999 final 1111", conversa="a")
    (b,) = conversar(f"pedido {PEDIDO} final 0000", conversa="b")
    assert a.texto == b.texto and "Não consegui validar" in a.texto


def test_tres_tentativas_erradas_bloqueiam_e_oferecem_atendente(sql):
    rs = conversar("pedido 4 final 0001", "pedido 4 final 0002", "pedido 4 final 0003", f"pedido 4 final {FINAL}")
    assert "atendente" in rs[2].texto and rs[2].estado == "aguardando:confirmacao_registro"
    assert "Encontrei" not in rs[3].texto and "Itens" not in rs[3].texto  # com o limite estourado, nem o final certo passa
    assert protocolos(sql) == []


def test_pergunta_o_final_quando_so_veio_o_pedido():
    (r,) = conversar("quero saber do pedido 4")
    assert "4 últimos dígitos" in r.texto and r.estado == "aguardando:pedido"


# --- informativos, frete e troca de assunto -------------------------------------------------

def test_horario_endereco_e_contato_vem_do_manual():
    h, e, c = conversar("qual o horário de funcionamento?", "onde fica a loja?", "qual o telefone?")
    assert "09:00 às 18:00" in h.texto and "09:00 às 13:00" in h.texto and "calendário de feriados" in h.texto
    assert "79202-333" in e.texto and "Campo Grande" in e.texto
    assert "(67) 3341-4444" in c.texto and "(67) 3321-4500" in c.texto and "não consigo confirmar" not in c.texto  # um canal de cada tipo, sem variantes


def test_pagamento_cita_as_duas_leituras_da_parcela_minima():
    (r,) = conversar("quais as formas de pagamento?")
    assert "5% de desconto" in r.texto and "até 12x" in r.texto and "equipe confirma" in r.texto


def test_frete_campo_grande_e_outra_cidade():
    r1, r2, r3 = conversar("qual o frete?", "Campo Grande", "R$ 300")
    assert r1.estado == "aguardando:cidade" and r2.estado == "aguardando:valor_pedido"
    assert "taxa fixa de R$ 35,00" in r3.texto
    (o,) = conversar("frete para Dourados, pedido de R$ 800", conversa="o")
    assert "cotação" in o.texto
    (g,) = conversar("frete para Campo Grande de um pedido de R$ 900", conversa="g")
    assert "grátis" in g.texto


def test_frete_de_exatamente_500_pede_confirmacao_da_equipe():
    (r,) = conversar("frete para Campo Grande de um pedido de R$ 500")
    assert "exatamente o limite" in r.texto and r.estado == "aguardando:confirmacao_registro"


def test_troca_de_assunto_guarda_o_anterior_e_oferece_retomar():
    r1, r2, r3 = conversar("quero devolver um produto", "qual o horário de vocês?", "sim")
    assert r1.estado == "aguardando:pedido"
    assert "09:00" in r2.texto and "Quer retomar" in r2.texto and "devolução" in r2.texto
    estado = carregar_estado("c1")
    assert estado.objetivo == "devolucao" and estado.pendentes == []
    assert "número do pedido" in r3.texto and r3.estado == "aguardando:pedido"


def test_recusar_retomada_descarta_o_assunto_guardado():
    conversar("quero devolver um produto", "qual o horário de vocês?", "não")
    estado = carregar_estado("c1")
    assert estado.objetivo is None and estado.pendentes == [] and estado.aguardando is None


def test_mensagem_incompreendida_e_depois_oferta_de_atendente(sql):
    r1, r2 = conversar("asdf qwer", "zzz")
    assert "Não entendi" in r1.texto and "atendente" in r2.texto
    assert protocolos(sql) == []


def test_garantia_informa_prazos_e_aponta_a_ambiguidade():
    (r,) = conversar("como funciona a garantia?")
    assert "90 dias" in r.texto and "30 dias corridos" in r.texto and "depende de confirmação da nossa equipe" in r.texto


# --- percepção por intenção -----------------------------------------------------------------

@pytest.mark.parametrize("mensagem,intencao", [
    ("oi, tudo bem?", "saudacao"),
    ("que horas vocês abrem?", "horario"),
    ("onde fica a loja?", "endereco"),
    ("qual o whatsapp de vocês?", "contato"),
    ("quais formas de pagamento?", "pagamento"),
    ("quero um violão", "busca_produto"),
    ("quanto custa o Takamine GD20?", "preco_produto"),
    ("o Takamine GD20 está disponível?", "disponibilidade"),
    ("onde está meu pedido 5?", "status_pedido"),
    ("quero devolver o violão", "devolucao"),
    ("quero trocar por outra cor", "troca_preferencia"),
    ("o violão chegou com defeito", "defeito"),
    ("como funciona a garantia?", "garantia"),
    ("qual o frete para Dourados?", "frete"),
    ("quero abrir uma reclamação", "reclamacao"),
    ("quero falar com um atendente", "pedir_atendente"),
    ("vocês vendem palheta?", "fora_escopo"),
    ("blablabla", "desconhecido"),
])
def test_dezoito_intencoes(mensagem, intencao):
    estado = Estado()
    perceber(estado, mensagem)
    assert estado.intencao == intencao


def test_negacoes_sao_percebidas():
    e1, e2 = Estado(), Estado()
    perceber(e1, "Não quero abrir reclamação")
    perceber(e2, "não quero falar com atendente")
    assert e1.slots["nega_reclamacao"] and not e1.permissao_registro
    assert e2.slots["nega_atendente"]


# --- laço, validação e decisor trocável -----------------------------------------------------

class DecisorFixo:
    def __init__(self, *acoes):
        self.acoes = list(acoes)

    def decidir(self, estado, mensagem):
        return self.acoes.pop(0) if len(self.acoes) > 1 else self.acoes[0]


def test_regras_decisor_cumpre_o_protocol():
    assert isinstance(RegrasDecisor(), Decisor) and isinstance(DecisorFixo(), Decisor)
    agente = Agente(DecisorFixo(Acao(tipo="responder", resposta="nao_entendi")))
    assert "Não entendi" in agente.responder("x", "oi", "eval").texto


def test_encaminhar_sem_permissao_vira_pergunta_e_nao_grava(sql):
    acao = Acao(tipo="encaminhar", ferramenta="registrar_encaminhamento",
                args={"tipo": "atendente", "resumo": "teste", "chave_idempotencia": "k"})
    r = Agente(DecisorFixo(acao)).responder("x", "oi", "eval")
    assert "Posso registrar" in r.texto and protocolos(sql) == []


def test_ferramenta_desconhecida_e_entrada_invalida_sao_bloqueadas(sql):
    ruim = Acao(tipo="ferramenta", ferramenta="apagar_banco", args={})
    r = Agente(DecisorFixo(ruim)).responder("x", "oi", "eval")
    assert "problema" in r.texto and r.estado == "falha"
    invalida = Acao(tipo="ferramenta", ferramenta="consultar_pedido", args={"pedido_id": "4", "final_telefone": "3456"})
    r2 = Agente(DecisorFixo(invalida)).responder("y", "oi", "eval")
    assert r2.estado == "falha"
    atalho = Acao(tipo="ferramenta", ferramenta="registrar_encaminhamento",
                  args={"tipo": "atendente", "resumo": "x", "chave_idempotencia": "k"})
    r3 = Agente(DecisorFixo(atalho)).responder("z", "oi", "eval")
    assert r3.estado == "falha" and protocolos(sql) == []


def test_limite_de_tres_passos():
    laco = Acao(tipo="ferramenta", ferramenta="consultar_politica", args={"temas": ["horario"]})
    r = Agente(DecisorFixo(laco)).responder("x", "oi", "eval")
    assert MAX_PASSOS == 3 and len([a for a in r.acoes if a.get("ferramenta")]) == 3
    assert r.estado == "falha" and "problema" in r.texto


def test_decisor_que_levanta_excecao_nao_derruba_o_atendimento():
    class Quebrado:
        def decidir(self, estado, mensagem):
            raise RuntimeError("boom")

    r = Agente(Quebrado()).responder("x", "oi", "eval")
    assert r.estado == "falha" and r.texto


def test_origem_invalida_e_recusada():
    with pytest.raises(ValueError):
        Agente().responder("x", "oi", "producao")


def test_falha_de_ferramenta_aparece_ao_cliente_sem_inventar(tmp_path, monkeypatch):
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text("manual: {versao: '2.1'}\n", encoding="utf-8")
    monkeypatch.setenv("EMPORIO_MANUAL", str(ruim))
    (r,) = conversar("qual o horário?")
    assert "problema" in r.texto and "09:00" not in r.texto and r.acoes[0]["estado"] == "falha"


def test_falhas_seguidas_oferecem_registro_do_problema(tmp_path, monkeypatch, sql):
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text("manual: {versao: '2.1'}\n", encoding="utf-8")
    monkeypatch.setenv("EMPORIO_MANUAL", str(ruim))
    r1, r2, r3 = conversar("qual o horário?", "qual o horário?", "sim")
    assert "registro o problema" in r2.texto and r2.estado == "aguardando:confirmacao_registro"
    assert sql.execute("SELECT tipo FROM chamados").fetchone()[0] == "falhas" and "Chamado registrado" in r3.texto


def test_yaml_alterado_muda_a_resposta_do_agente(tmp_path, monkeypatch):
    origem = config.caminho_manual().read_text(encoding="utf-8")
    (antes,) = conversar("qual o horário?", conversa="a")
    assert "09:00 às 18:00" in antes.texto
    alterado = tmp_path / "alterado.yaml"
    alterado.write_text(origem.replace('abre: "09:00", fecha: "18:00"', 'abre: "08:30", fecha: "19:00"'), encoding="utf-8")
    monkeypatch.setenv("EMPORIO_MANUAL", str(alterado))
    (depois,) = conversar("qual o horário?", conversa="b")
    assert "08:30 às 19:00" in depois.texto and "09:00 às 18:00" not in depois.texto


def test_estado_persiste_entre_instancias_do_agente():
    Agente().responder("p", "quero devolver", "eval")
    estado = carregar_estado("p")
    assert estado.objetivo == "devolucao" and estado.aguardando == "pedido" and estado.turno == 1
    r = Agente().responder("p", f"pedido {PEDIDO} final {FINAL}", "eval")
    assert "Encontrei o pedido 4" in r.texto


def test_mensagens_exibidas_e_execucoes_sao_tabelas_separadas(sql):
    conversar("quero devolver", f"pedido {PEDIDO} final {FINAL}")
    msgs = sql.execute("SELECT turno, texto, origem FROM mensagens_exibidas ORDER BY id").fetchall()
    exec_ = sql.execute("SELECT ferramenta, estado, entrada_json FROM execucoes ORDER BY id").fetchall()
    assert [m["turno"] for m in msgs] == [1, 2] and all(m["origem"] == "eval" for m in msgs)
    assert [e["ferramenta"] for e in exec_] == ["consultar_politica", "consultar_politica", "consultar_pedido"]
    assert FINAL not in " ".join(e["entrada_json"] for e in exec_)
    assert json.loads(exec_[2]["entrada_json"])["final_telefone"] == "[omitido]"
    assert not any(e["ferramenta"] in m["texto"] for m in msgs for e in exec_)


def test_resposta_traz_fatos_com_fonte():
    (r,) = conversar("quanto custa o Crafter HT-100?")
    assert r.fatos and all(f.fonte.tipo in ("banco", "manual", "calculo") for f in r.fatos)
    final = next(f for f in r.fatos if f.atributo == "final_centavos")
    assert final.valor == 196718 and final.entidade_id == 90
