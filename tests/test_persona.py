"""Persona da Lia: o que o código verifica (a avaliação de tom é humana e não foi feita nesta entrega)."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from emporio.agente import persona, respostas, redacao
from emporio.agente.laco import Agente
from emporio.agente.llm import RespostaLlm
from emporio.agente.redacao import Redator

RESPOSTAS_PY = Path(respostas.__file__)


def conversar(*mensagens, conversa="p1", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def test_persona_tem_os_campos_obrigatorios_e_nenhum_fato_de_loja():
    p = persona.carregar()
    for campo in persona.CAMPOS_OBRIGATORIOS:
        assert p[campo], campo
    assert p["nome"] == "Lia" and "assistente virtual" in p["identificacao"]
    bruto = persona.CAMINHO.read_text(encoding="utf-8")
    assert not re.search(r"\d{4,5}-\d{4}|R\$|Campo Grande|Rua 14|Emp[óo]rio da M", bruto)  # só {loja} como marcador
    assert "—" not in bruto


def _textos_de_respostas() -> list[str]:
    """Literais de respostas.py que viram texto ao cliente: com espaço, fora docstrings."""
    arvore = ast.parse(RESPOSTAS_PY.read_text(encoding="utf-8"))
    docstrings = {id(n.body[0].value) for n in ast.walk(arvore)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(arvore) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings and " " in n.value]


def test_nenhum_texto_de_respostas_usa_expressao_proibida_pela_persona():
    achados = {t[:60]: persona.proibida_em(t) for t in _textos_de_respostas() if persona.proibida_em(t)}
    achados |= {f[:60]: persona.proibida_em(f) for fs in respostas.RECONHECIMENTOS.values() for f in fs
                if persona.proibida_em(f)}
    assert achados == {}


def _turnos_dos_casos() -> list[list[str]]:
    base = Path(__file__).resolve().parents[1] / "eval"
    casos = []
    for nome in ("casos_dev.jsonl", "casos_variacoes.jsonl"):
        for linha in (base / nome).read_text(encoding="utf-8").splitlines():
            if linha.strip():
                casos.append(json.loads(linha)["turnos"])
    casos += [  # caminhos com ambiguidade do manual, que o cliente vê em linguagem de loja
        ["Shelby SN-100 em 6x", "sim"], ["qual o telefone, e-mail e whatsapp?"], ["quanto custa o Crafter HT-100?"],
        ["qual o frete pra compra de R$ 500 em Campo Grande?"], ["tem promoção?", "a Black Friday vale?"],
        ["como funciona a garantia?"], ["como funciona a troca e a garantia?", "sim"],
        ["quero trocar meu violão", "pedido 4, final 3456", "recebi dia 15/12/2025, compra online, sem uso"],
        ["quero devolver", "pedido 4, final 3456", "online, recebi dia 15/12/2025, sem uso", "sim"],
        ["quero abrir reclamação", "o violão chegou riscado e ninguém me responde", "sim"],
        ["o Giannini GF-3D Dreadnought Sunburst está disponível?"], ["pedido PED-0099"], ["qual o horário?"],
        ["posso pagar parte no pix e parte no cartão?"], ["prazo de entrega para Dourados?"],
    ]
    return casos


def test_nenhuma_resposta_em_execucao_cita_bastidor_nem_expressao_proibida():
    """Roda os casos do dev e das variações e varre o texto que o cliente realmente recebe."""
    achados = {}
    for i, turnos in enumerate(_turnos_dos_casos()):
        agente = Agente()
        for t in turnos:
            texto = agente.responder(f"varredura-{i}", t, "eval").texto
            if persona.proibida_em(texto):
                achados[f"{t[:40]} -> {texto[:50]}"] = persona.proibida_em(texto)
    assert achados == {}


def test_o_proibido_inclui_os_detalhes_internos_e_nao_palavras_soltas():
    for termo in ("no sistema", "do sistema", "manual", "ferramenta", "seção", "origem do dado", "demonstração",
                  "fictícia", "desafio"):
        assert persona.proibida_em(f"isso vem {termo} da loja"), termo
    for legitima in ("Vou testar o violão com você? Pode testar na loja.", "O teste de som é na loja.",
                     "Qual a origem do instrumento?", "Aceitamos mais de um sistema de pagamento."):
        assert not persona.proibida_em(legitima), legitima


def test_o_detector_de_proibidas_pega_o_que_deveria():
    for ruim in ("Certo, sem enrolação.", "Prezado cliente, bom dia", "Beleza, mano!", "ok 😀"):
        assert persona.proibida_em(ruim), ruim
    assert not persona.proibida_em("Entendo sua frustração.")


def test_saudacao_se_apresenta_na_voz_da_persona_com_o_nome_da_loja_do_manual():
    (r,) = conversar("oi")
    assert r.texto.startswith("Oi! Sou a Lia, assistente virtual do Empório da Música. Como posso te ajudar?")


def test_apresentacao_no_maximo_uma_vez_na_conversa():
    rs = conversar("oi", "qual o horário?", "oi de novo", "quanto custa o Crafter HT-100?", "bom dia",
                   agente=Agente(concisao=True))
    assert sum(len(re.findall(r"\bSou a Lia\b", r.texto)) for r in rs) == 1


def test_apresentacao_nao_aparece_fora_da_saudacao():
    textos = conversar("qual o endereço?", "vocês vendem cordas?", "o que acha do futebol?", "quero devolver")
    assert not any("Sou a Lia" in r.texto or "assistente virtual" in r.texto for r in textos)


class ClienteQueGuarda:
    def __init__(self, saida):
        self.saida, self.sistemas = saida, []

    def conversar(self, modelo, mensagens, formato=None, limite=None, maximo_tokens=400):
        self.sistemas.append(mensagens[0]["content"])
        return RespostaLlm(conteudo=json.dumps(self.saida), tokens_prompt=1, tokens_resposta=1, latencia_ms=1)


def test_persona_vai_nas_instrucoes_em_todo_turno_redigido():
    cliente = ClienteQueGuarda({"abertura": "Claro.", "fechamento": None})
    agente = Agente(redator=Redator("falso:1b", cliente), concisao=True)
    conversar("qual o endereço?", "qual o horário?", "quanto custa o Crafter HT-100?", "vocês vendem cordas?",
              agente=agente)
    assert len(cliente.sistemas) == 3  # a resposta de escopo ("cordas") não passa pela redação
    p = persona.carregar()
    for sistema in cliente.sistemas:
        assert sistema.startswith(persona.instrucoes()) and p["nome"] in sistema
        assert all(t in sistema for t in p["tom"])
        assert "emoji" in sistema.lower()


def test_reconhecimento_de_frustracao_na_voz_da_persona_sem_desculpa_nem_giria():
    todas = [f for fs in respostas.RECONHECIMENTOS.values() for f in fs]
    assert "Certo, sem enrolação." not in todas and "Dá para ver que isso está incomodando." not in todas
    assert "Entendo sua frustração." in todas


def test_conferi_o_pedido_so_quando_a_consulta_ocorre_no_turno(sql):
    r = conversar("de novo, quero saber do pedido 8, final 7821", conversa="c1")[0]
    assert "Conferi o que está registrado sobre o seu pedido" in r.texto
    sem = conversar("de novo, qual o horário?", conversa="c2")[0]
    assert "Conferi" not in sem.texto and "Vou conferir" not in sem.texto


# sim para "opções parecidas" executa buscar_produtos na mesma categoria ---------------------------------

def _agente_com_busca_que_falha_uma_vez(monkeypatch):
    from emporio.agente import laco

    original = laco.FERRAMENTAS["buscar_produtos"]
    estado = {"falhou": False}

    def instavel(*a, **k):
        if not estado["falhou"]:
            estado["falhou"] = True
            from emporio.ferramentas.envelope import resultado
            return resultado("falha", motivo="erro_interno")
        return original(*a, **k)

    instavel.modelo_entrada = original.modelo_entrada
    instavel.__name__ = "buscar_produtos"
    monkeypatch.setitem(laco.FERRAMENTAS, "buscar_produtos", instavel)
    return estado


def test_sim_a_opcoes_parecidas_executa_nova_busca_na_mesma_categoria(monkeypatch):
    _agente_com_busca_que_falha_uma_vez(monkeypatch)
    r = conversar("o Giannini GF-3D Dreadnought Sunburst está disponível?", "sim")
    assert "Não consegui consultar opções parecidas agora" in r[0].texto and "Quer que eu tente de novo" in r[0].texto
    assert r[0].estado == "aguardando:retentar_parecidas"
    assert "buscar_produtos" in [a.get("ferramenta") for a in r[1].acoes]  # nova tentativa real
    assert "Opções disponíveis na mesma categoria" in r[1].texto and "Violões" in r[1].texto


def test_nao_a_opcoes_parecidas_nao_busca_de_novo(monkeypatch):
    _agente_com_busca_que_falha_uma_vez(monkeypatch)
    r = conversar("o Giannini GF-3D Dreadnought Sunburst está disponível?", "não")
    assert "buscar_produtos" not in [a.get("ferramenta") for a in r[1].acoes] and r[1].estado == "concluido"


def test_sem_falha_as_opcoes_parecidas_ja_vem_na_primeira_resposta():
    (r,) = conversar("o Giannini GF-3D Dreadnought Sunburst está disponível?")
    assert "Opções disponíveis na mesma categoria" in r.texto and "Quer que eu tente de novo" not in r.texto
