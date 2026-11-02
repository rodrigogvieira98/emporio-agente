"""Tom das conversas de exemplo (etapa 26): acolhimento, chamado completo, dia específico e resumo curto."""
from __future__ import annotations

from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="t26"):
    agente = Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def test_reclamacao_irritada_abre_com_uma_frase_de_acolhimento():
    _, r2 = conversar("quero abrir reclamação", "o violão chegou riscado e ninguém me responde, que absurdo")
    assert "Protocolo: EM-" in r2.texto
    primeira = r2.texto.split("\n")[0]
    assert primeira.startswith(("Entendo", "Sinto muito", "Percebo", "Imagino"))
    assert "Registrei o seu chamado" in r2.texto
    assert len(primeira) < 80
    assert "desculp" not in r2.texto.lower()


def test_chamado_neutro_nao_ganha_acolhimento():
    r = conversar("quero abrir reclamação", "o violão chegou com a caixa amassada, quero que alguém veja")[1]
    assert not r.texto.startswith(("Entendo", "Sinto muito", "Percebo", "Imagino"))


def test_nenhum_texto_diz_que_o_atendente_ja_tem_como_falar():
    r1, r2 = conversar("quero abrir reclamação", "o violão chegou riscado e ninguém me responde, que absurdo")
    for r in (r1, r2):
        assert "já tem como falar" not in r.texto


def test_todo_chamado_traz_protocolo_prazo_canais_e_pede_citar_o_protocolo():
    r = conversar("quero abrir reclamação", "o violão chegou riscado e ninguém me responde, que absurdo")[1]
    t = r.texto
    assert "EM-000001" in t and "24 horas úteis" in t
    assert "WhatsApp" in t and "telefone" in t and "das 9h às 18h" in t
    assert "cite o protocolo" in t.lower()
    assert t.count("24 horas") == 1


def test_chamado_de_devolucao_tambem_traz_prazo_e_canais():
    r4 = conversar("quero devolver", "pedido 4 final 3456", "online, recebi dia 15/12/2025, sem uso", "sim")[3]
    assert "EM-000001" in r4.texto and "24 horas úteis" in r4.texto and "WhatsApp" in r4.texto
    assert "cite o protocolo" in r4.texto.lower()


def test_pergunta_de_sabado_responde_so_o_sabado():
    r = conversar("E que horas vocês abrem no sábado?")[0]
    assert "9h às 13h" in r.texto
    assert "segunda" not in r.texto and "domingo" not in r.texto and "18h" not in r.texto
    assert "feriado" in r.texto


def test_pergunta_de_domingo_responde_so_o_domingo():
    r = conversar("domingo abre?")[0]
    assert "domingo" in r.texto and "fechad" in r.texto
    assert "segunda" not in r.texto and "sábado" not in r.texto


def test_semana_inteira_so_quando_pedida():
    r = conversar("qual o horário de funcionamento de vocês?")[0]
    assert "segunda a sexta" in r.texto and "sábado" in r.texto and "domingo" in r.texto


def test_resumo_de_devolucao_tem_ate_4_linhas():
    r3 = conversar("Oi, quero devolver um violão que comprei", "o pedido é o 4 e o final do telefone é 3456",
                   "foi compra online, recebi em 15/12/2025 e está na caixa, sem uso")[2]
    linhas = [ln for ln in r3.texto.split("\n") if ln.strip()]
    assert len(linhas) <= 4
    assert "R$ 799,90" in r3.texto and "(não verificado)" in r3.texto and "15/12/2025" in r3.texto
    assert "7 dias" in r3.texto and "Posso registrar" in r3.texto
    assert "Eu não consigo garantir a elegibilidade" in r3.texto or "atendente" in linhas[-2]
