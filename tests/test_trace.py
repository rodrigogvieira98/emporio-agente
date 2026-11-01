"""Trace JSONL por turno: origem obrigatória e nenhum dado pessoal."""
from __future__ import annotations

import json

from emporio import config
from emporio.agente.estado import ORIGENS
from emporio.agente.laco import Agente

NOME, TELEFONE, EMAIL, FINAL = "Lucas Mendes da Silva", "(67) 99812-3456", "lucas.mendes@jmail.com", "3456"


def _linhas():
    return [json.loads(l) for l in config.caminho_trace().read_text(encoding="utf-8").splitlines()]


def _strings(valor):
    if isinstance(valor, dict):
        for k, v in valor.items():
            if k not in ("id_consulta", "ts"):  # ids aleatórios podem conter qualquer sequência
                yield from _strings(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _strings(v)
    elif isinstance(valor, str):
        yield valor


def test_um_registro_por_turno_com_origem_obrigatoria():
    agente = Agente()
    for origem in ORIGENS:
        agente.responder(f"c-{origem}", "oi", origem)
    registros = _linhas()
    assert [r["origem"] for r in registros] == ["real", "eval", "demo"]
    for r in registros:
        assert {"turno", "conversa", "intencao", "passos", "acoes", "latencia_ms", "estado_antes", "estado_depois"} <= set(r)
        assert isinstance(r["latencia_ms"], int)


def test_trace_registra_ferramentas_estados_e_acoes():
    agente = Agente()
    agente.responder("c1", "quanto custa o Crafter HT-100?", "eval")
    (r,) = _linhas()
    ferramentas = [p["ferramenta"] for p in r["passos"] if "ferramenta" in p]
    assert ferramentas == ["ver_produto", "calcular_condicoes"]
    assert all(p["estado"] == "ok" for p in r["passos"] if "ferramenta" in p)
    assert r["acoes"][-1] == {"tipo": "responder", "resposta": "preco"}


def test_trace_sem_nome_telefone_email_ou_final_digitado(sql):
    agente = Agente()
    mensagens = [
        f"Oi, sou {NOME}, meu telefone é {TELEFONE} e meu email é {EMAIL}",
        "quero devolver um violão",
        f"pedido 4 final {FINAL}",
        f"fiz a compra online, recebi em 15/12/2025 e está lacrado. Me liga no {TELEFONE}",
        f"sim, pode registrar, meu e-mail é {EMAIL}",
        f"quero abrir uma reclamação: sou {NOME}, falem comigo em {TELEFONE} ou {EMAIL}",
    ]
    for m in mensagens:
        agente.responder("c1", m, "eval")
    bruto = config.caminho_trace().read_text(encoding="utf-8")
    textos = " ".join(_strings([json.loads(l) for l in bruto.splitlines()]))
    for pii in ("Lucas", "Mendes", "Silva", "99812", "jmail", "lucas.mendes", FINAL, "(67)"):
        assert pii.lower() not in textos.lower(), pii
    # nem o resumo gravado no chamado, nem o estado persistido, nem as execuções guardam esses dados
    resumos = " ".join(r["resumo"] for r in sql.execute("SELECT resumo FROM chamados"))
    estado = " ".join(r["estado_json"] for r in sql.execute("SELECT estado_json FROM conversas"))
    execucoes = " ".join(r["entrada_json"] for r in sql.execute("SELECT entrada_json FROM execucoes"))
    for onde in (resumos, estado, execucoes):
        for pii in ("99812", "jmail", "lucas.mendes", NOME):
            assert pii not in onde, (pii, onde[:200])
    assert FINAL not in estado and FINAL not in execucoes


def test_trace_nao_grava_o_texto_do_cliente_nem_da_resposta():
    Agente().responder("c1", "quanto custa o Takamine GD20? ele é bonito demais", "demo")
    bruto = config.caminho_trace().read_text(encoding="utf-8")
    assert "bonito" not in bruto and "Takamine" not in bruto and "R$" not in bruto


def test_trace_nao_derruba_o_atendimento_se_nao_puder_gravar(monkeypatch, tmp_path):
    monkeypatch.setenv("EMPORIO_TRACE", str(tmp_path))  # diretório no lugar de arquivo
    r = Agente().responder("c1", "oi", "eval")
    assert "Lia" in r.texto
