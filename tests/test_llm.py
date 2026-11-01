"""Cliente Ollama, LlmDecisor e Redator, sem Ollama: servidor HTTP falso e cliente falso."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from emporio import config
from emporio.agente import llm, llm_decisor
from emporio.agente.estado import Acao
from emporio.agente.laco import Agente
from emporio.agente.llm import ErroModelo, RespostaLlm, TimeoutModelo
from emporio.agente.llm_decisor import LlmDecisor
from emporio.agente.redacao import Redator


# --- servidor falso -------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    corpos: list = []
    modo = "ok"

    def log_message(self, *a):  # silêncio
        pass

    def do_GET(self):
        self._responder({"models": [{"name": "falso:1b"}]})

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        _Handler.corpos.append(json.loads(self.rfile.read(tamanho)))
        if _Handler.modo == "lento":
            time.sleep(1.5)
        if _Handler.modo == "500":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        self._responder({"message": {"content": '{"x": 1}'}, "prompt_eval_count": 7, "eval_count": 3})

    def _responder(self, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


@pytest.fixture
def servidor(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.corpos, _Handler.modo = [], "ok"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{srv.server_address[1]}")
    yield _Handler
    srv.shutdown()


def test_cliente_envia_temperatura_zero_semente_42_e_raciocinio_desligado(servidor):
    r = llm.conversar("falso:1b", [{"role": "user", "content": "oi"}], formato={"type": "object"})
    corpo = servidor.corpos[0]
    assert corpo["options"]["temperature"] == 0 and corpo["options"]["seed"] == 42
    assert corpo["think"] is False and corpo["stream"] is False and corpo["format"] == {"type": "object"}
    assert corpo["model"] == "falso:1b"
    assert (r.conteudo, r.tokens_prompt, r.tokens_resposta) == ('{"x": 1}', 7, 3) and r.latencia_ms >= 0


def test_num_ctx_fixo_em_8192_por_padrao_e_configuravel_por_env(servidor, monkeypatch):
    monkeypatch.delenv("EMPORIO_NUM_CTX", raising=False)
    r = llm.conversar("falso:1b", [{"role": "user", "content": "oi"}])
    assert servidor.corpos[-1]["options"]["num_ctx"] == 8192 and r.num_ctx == 8192
    monkeypatch.setenv("EMPORIO_NUM_CTX", "4096")
    llm.conversar("falso:1b", [{"role": "user", "content": "oi"}])
    assert servidor.corpos[-1]["options"]["num_ctx"] == 4096
    monkeypatch.setenv("EMPORIO_NUM_CTX", "lixo")
    assert llm.num_ctx() == 8192


def test_trace_registra_num_ctx():
    cliente = ClienteFalso(proposta(ferramenta="consultar_politica", temas=["horario"]), proposta(resposta="horario"))
    agente_com(cliente).responder("c1", "qual o horário de vocês?", "eval")
    (t,) = trace_do_turno()
    assert all("num_ctx" in x for x in t["telemetria_modelo"])


def test_cliente_usa_ollama_host_e_lista_modelos(servidor):
    assert llm.modelos_instalados() == ["falso:1b"]
    llm.conferir_modelo("falso:1b")
    with pytest.raises(ErroModelo, match="nao esta instalado"):
        llm.conferir_modelo("outro:3b")


def test_timeout_e_erro_de_servidor_sao_distintos(servidor, monkeypatch):
    monkeypatch.setenv("EMPORIO_LLM_TIMEOUT", "0.3")
    servidor.modo = "lento"
    with pytest.raises(TimeoutModelo):
        llm.conversar("falso:1b", [{"role": "user", "content": "oi"}])
    servidor.modo = "500"
    with pytest.raises(ErroModelo, match="HTTP 500") as e:
        llm.conversar("falso:1b", [{"role": "user", "content": "oi"}])
    assert not isinstance(e.value, TimeoutModelo)


def test_conexao_recusada_vira_erro_modelo(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    with pytest.raises(ErroModelo):
        llm.conversar("falso:1b", [{"role": "user", "content": "oi"}])


def test_qwen3_recebe_o_reforco_de_no_think():
    assert llm.mensagens_do_modelo("qwen3:4b", "sis", "u")[0]["content"].endswith("/no_think")
    assert "/no_think" not in llm.mensagens_do_modelo("qwen2.5:3b", "sis", "u")[0]["content"]


# --- cliente falso ----------------------------------------------------------------------------

class ClienteFalso:
    """Devolve as saídas em ordem. Exceção na fila é levantada."""

    def __init__(self, *saidas):
        self.saidas = list(saidas)
        self.chamadas: list[dict] = []

    def conversar(self, modelo, mensagens, formato=None, limite=None, maximo_tokens=400):
        self.chamadas.append({"modelo": modelo, "mensagens": mensagens, "formato": formato})
        saida = self.saidas.pop(0) if len(self.saidas) > 1 else self.saidas[0]
        if isinstance(saida, Exception):
            raise saida
        texto = saida if isinstance(saida, str) else json.dumps(saida)
        return RespostaLlm(conteudo=texto, tokens_prompt=100, tokens_resposta=20, latencia_ms=5)


def proposta(**campos):
    base = {k: None for k in llm_decisor.SCHEMA["properties"]}
    base.update(campos)
    return base


def agente_com(cliente, redator=None, concisao=False):
    return Agente(LlmDecisor("falso:1b", cliente), redator, concisao=concisao)


def trace_do_turno():
    return [json.loads(l) for l in config.caminho_trace().read_text(encoding="utf-8").splitlines()]


# --- LlmDecisor ---------------------------------------------------------------------------------

def test_prompt_e_versionado_com_hash_e_curto():
    texto, h = llm_decisor.prompt()
    assert h == hashlib.sha256(texto.encode("utf-8")).hexdigest() and len(h) == 64
    assert len(texto) < 6000  # sem catálogo nem manual inteiros
    assert "Takamine" not in texto and "R$" not in texto


def test_schema_tem_so_ferramentas_e_respostas_conhecidas():
    props = llm_decisor.SCHEMA["properties"]
    assert set(props["ferramenta"]["enum"]) - {None} == set(llm_decisor.NOMES_FERRAMENTAS)
    assert "horario" in props["resposta"]["enum"] and set(llm_decisor.SCHEMA["required"]) == set(props)


def test_proposta_valida_vira_acao_e_o_laco_executa():
    cliente = ClienteFalso(proposta(ferramenta="consultar_politica", temas=["horario"]),
                           proposta(resposta="horario"))
    r = agente_com(cliente).responder("c1", "qual o horário de vocês?", "eval")
    assert [a.get("ferramenta") or a.get("resposta") for a in r.acoes] == ["consultar_politica", "horario"]
    assert "09:00 às 18:00" in r.texto and r.contagens.get("proposta_invalida", 0) == 0
    assert len(cliente.chamadas) == 2
    # estado resumido no prompt: mensagem, percepção e o que rodou no turno
    entrada = json.loads(cliente.chamadas[1]["mensagens"][-1]["content"])
    assert entrada["neste_turno"][0]["ferramenta"] == "consultar_politica" and entrada["percepcao"]["intencao"] == "horario"


def test_proposta_invalida_cai_nas_regras_e_conta():
    cliente = ClienteFalso("isto nao e json")
    r = agente_com(cliente).responder("c1", "qual o horário de vocês?", "eval")
    assert "09:00 às 18:00" in r.texto  # as regras responderam
    assert r.contagens["proposta_invalida"] >= 3 and r.contagens["fallback_regras"] >= 1
    t = trace_do_turno()[0]
    assert t["contagens"]["proposta_invalida"] == r.contagens["proposta_invalida"]
    assert any(x["resultado"] == "recusada" and x["proposta_bruta"] == "isto nao e json" for x in t["telemetria_modelo"])


@pytest.mark.parametrize("ruim", [
    proposta(ferramenta="apagar_banco"), proposta(), proposta(ferramenta="ver_produto", resposta="busca"),
    proposta(resposta="busca"),  # sem a ferramenta que ela exige
    proposta(resposta="inventada"), proposta(ferramenta="ver_produto"),  # sem referencia
    proposta(ferramenta="calcular_condicoes", forma="cheque"), [1, 2],
])
def test_propostas_ruins_sao_recusadas(ruim):
    cliente = ClienteFalso(ruim)
    r = agente_com(cliente).responder("c1", "qual o horário de vocês?", "eval")
    assert r.contagens["proposta_invalida"] >= 1 and "09:00" in r.texto


def test_correcao_apos_recusa_e_contada():
    cliente = ClienteFalso(proposta(resposta="horario"), proposta(ferramenta="consultar_politica", temas=["horario"]),
                           proposta(resposta="horario"))
    r = agente_com(cliente).responder("c1", "qual o horário de vocês?", "eval")
    assert r.contagens["proposta_invalida"] == 1 and r.contagens["correcao_aceita"] >= 1
    segunda = json.loads(cliente.chamadas[1]["mensagens"][-1]["content"])
    assert "ainda nao pode ser a resposta" in segunda["erro"] and "consultar_politica" in segunda["erro"]


def test_timeout_e_erro_de_modelo_caem_nas_regras_com_contagem_propria():
    r = agente_com(ClienteFalso(TimeoutModelo("lento"))).responder("c1", "qual o horário de vocês?", "eval")
    assert "09:00" in r.texto and r.contagens["timeout"] >= 1 and "erro_modelo" not in r.contagens
    r2 = agente_com(ClienteFalso(ErroModelo("sem conexao"))).responder("c2", "qual o horário de vocês?", "eval")
    assert "09:00" in r2.texto and r2.contagens["erro_modelo"] >= 1 and "timeout" not in r2.contagens


def test_numero_e_final_do_pedido_vem_do_codigo_nao_do_modelo():
    cliente = ClienteFalso(proposta(ferramenta="consultar_pedido"), proposta(resposta="status_pedido"))
    r = agente_com(cliente).responder("c1", "status do pedido 4 final 3456", "eval")
    assert r.acoes[0]["ferramenta"] == "consultar_pedido" and r.acoes[0]["estado"] == "ok"
    assert "Pedido 4" in r.texto
    prompt_enviado = cliente.chamadas[0]["mensagens"][-1]["content"]
    assert "3456" not in prompt_enviado and "[final]" in prompt_enviado


def test_registro_sem_permissao_e_bloqueado_pelo_laco_e_vira_pergunta(sql):
    cliente = ClienteFalso(proposta(ferramenta="registrar_encaminhamento", tipo_registro="atendente", resumo="x"))
    r = agente_com(cliente).responder("c1", "oi, tudo bem?", "eval")
    assert r.contagens.get("bloqueio_sem_permissao") == 1 and "Posso registrar" in r.texto
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 0


def test_repeticao_de_ferramenta_no_turno_e_recusada():
    cliente = ClienteFalso(proposta(ferramenta="consultar_politica", temas=["horario"]))
    r = agente_com(cliente).responder("c1", "qual o horário de vocês?", "eval")
    assert r.contagens["proposta_invalida"] >= 1 and "09:00" in r.texto


def test_resposta_com_dado_pessoal_no_resumo_e_mascarada():
    cliente = ClienteFalso(proposta(ferramenta="consultar_politica", temas=["horario"]),
                           proposta(ferramenta="registrar_encaminhamento", tipo_registro="atendente",
                                    resumo="ligar para (67) 99812-3456 ou joao@x.com"),
                           proposta(resposta="chamado_registrado"))
    agente = agente_com(cliente)
    r = agente.responder("c1", "quero falar com um atendente", "eval")
    assert "Registrei o seu chamado" in r.texto
    import sqlite3
    resumo = sqlite3.connect(config.caminho_banco()).execute("SELECT resumo FROM chamados").fetchone()[0]
    assert "99812" not in resumo and "joao@x.com" not in resumo


def test_trace_guarda_proposta_bruta_tokens_latencia_origem_e_sem_pii():
    nome, tel, mail = "Lucas Mendes da Silva", "(67) 99812-3456", "lucas.mendes@jmail.com"
    eco = proposta(ferramenta="consultar_pedido", resumo=f"{nome} {tel} {mail} final 3456")
    cliente = ClienteFalso(eco, proposta(resposta="status_pedido"))
    agente_com(cliente).responder("c1", f"sou {nome}, meu telefone é {tel}, email {mail}. pedido 4 final 3456", "demo")
    (t,) = trace_do_turno()
    assert t["origem"] == "demo" and t["modelo"] == "falso:1b" and t["tokens"] > 0
    bruto = json.dumps(t, ensure_ascii=False)
    for pii in ("Lucas", "Mendes", "99812", "jmail", "lucas.mendes", "3456"):
        assert pii not in bruto, pii
    primeira = t["telemetria_modelo"][0]
    assert "[nome]" in primeira["proposta_bruta"] and "[final]" in primeira["proposta_bruta"]
    assert primeira["latencia_ms"] == 5 and primeira["prompt_hash"] == llm_decisor.prompt()[1]


def test_decisor_falso_comum_continua_funcionando_no_laco():
    class Fixo:
        def decidir(self, estado, mensagem):
            return Acao(tipo="responder", resposta="nao_entendi")

    r = Agente(Fixo()).responder("c1", "oi", "eval")
    assert "Não entendi" in r.texto and r.contagens.get("proposta_invalida", 0) == 0


# --- Redator --------------------------------------------------------------------------------------

def _redigir(cliente_saida, mensagem="qual o horário de vocês?", concisao=False):
    cliente = ClienteFalso(proposta(ferramenta="consultar_politica", temas=["horario"]), proposta(resposta="horario"))
    redator = Redator("falso:1b", ClienteFalso(cliente_saida))
    return agente_com(cliente, redator, concisao).responder("c1", mensagem, "eval")


def test_redacao_aceita_abertura_e_fechamento_curtos_ao_redor_do_bloco():
    r = _redigir({"abertura": "Claro, já te passo.", "fechamento": "Qualquer coisa é só falar."})
    linhas = r.texto.splitlines()
    assert linhas[0] == "Claro, já te passo." and linhas[-1] == "Qualquer coisa é só falar."
    assert "09:00 às 18:00" in r.texto and "redacao_descartada" not in r.contagens


@pytest.mark.parametrize("livre,motivo", [
    ({"abertura": "Funcionamos das 9h às 18h.", "fechamento": None}, "digito"),
    ({"abertura": "Custa uns cem reais.", "fechamento": None}, "moeda"),
    ({"abertura": "Fica por R$ pouco.", "fechamento": None}, "moeda"),
    ({"abertura": "Já transferi você para a equipe.", "fechamento": None}, "verbo"),
    ({"abertura": "Reservei o Takamine para você.", "fechamento": None}, "verbo"),
    ({"abertura": "Aprovei sua devolução.", "fechamento": None}, "verbo"),
    ({"abertura": "Cancelei o pedido.", "fechamento": None}, "verbo"),
    ({"abertura": "O Takamine GD20 é ótimo.", "fechamento": None}, "produto"),
    ({"abertura": "Uma. Duas. Três frases.", "fechamento": None}, "frases"),
    ({"abertura": "Quer ajuda?", "fechamento": "Posso mais algo?"}, "perguntas"),
    ({"abertura": "x" * 300, "fechamento": None}, "longo"),
    ("não é json", "formato"),
    ({"abertura": 5, "fechamento": None}, "formato"),
])
def test_redacao_reprovada_descarta_o_texto_livre_e_conta(livre, motivo):
    r = _redigir(livre)
    assert "09:00 às 18:00" in r.texto and r.contagens["redacao_descartada"] == 1
    for pedaco in ("transferi", "Reservei", "Aprovei", "Cancelei", "Takamine", "frases", "R$ pouco"):
        assert pedaco not in r.texto
    assert r.texto.splitlines()[0].startswith("Nosso horário")  # só o bloco controlado


def test_redacao_nao_aceita_pergunta_quando_o_bloco_ja_pergunta():
    cliente = ClienteFalso(proposta(ferramenta="buscar_produtos", categoria="violao", preco_max=100000),
                           proposta(resposta="busca"))
    redator = Redator("falso:1b", ClienteFalso({"abertura": "Olha só?", "fechamento": None}))
    r = Agente(LlmDecisor("falso:1b", cliente), redator).responder("c1", "violões até R$ 1000", "eval")
    assert r.contagens["redacao_descartada"] == 1 and not r.texto.startswith("Olha")


def test_redacao_so_com_fechamento_proibido_em_pergunta_de_confirmacao():
    cliente = ClienteFalso(proposta(resposta="reclamacao_empatia", propor_registro=True, tipo_registro="reclamacao",
                                    resumo="cliente insatisfeito"))
    redator = Redator("falso:1b", ClienteFalso({"abertura": "Poxa.", "fechamento": "Conte comigo."}))
    r = Agente(LlmDecisor("falso:1b", cliente), redator).responder("c1", "estou muito insatisfeito com o atendimento", "eval")
    assert r.texto.startswith("Poxa.") and "Conte comigo" not in r.texto


def test_redacao_timeout_usa_so_o_bloco():
    r = _redigir(TimeoutModelo("lento"))
    assert r.contagens["timeout"] == 1 and r.texto.startswith("Nosso horário")


def test_redator_guarda_texto_bruto_antes_da_checagem_no_trace():
    _redigir({"abertura": "Funcionamos das 9h.", "fechamento": None})
    (t,) = trace_do_turno()
    red = [x for x in t["telemetria_modelo"] if x["componente"] == "redacao"][0]
    assert "Funcionamos das 9h" in red["texto_bruto"] and red["resultado"] == "descartada:digito"
    assert t["contagens"]["redacao_descartada"] == 1


def test_saudacao_nao_recebe_redacao():
    cliente = ClienteFalso(proposta(ferramenta="consultar_politica", temas=["empresa", "horario"]),
                           proposta(resposta="saudacao"))
    redator = Redator("falso:1b", ClienteFalso({"abertura": "Olá!", "fechamento": None}))
    r = Agente(LlmDecisor("falso:1b", cliente), redator).responder("c1", "oi", "eval")
    assert r.texto.startswith("Oi! Sou a Lia") and redator.cliente.chamadas == []


def test_fabrica_regras_decidem_e_modelo_so_redige(monkeypatch):
    from emporio.agente.fabrica import criar_agente
    from emporio.agente.regras import RegrasDecisor

    monkeypatch.setenv("EMPORIO_REDACAO", "1")
    monkeypatch.setenv("EMPORIO_DECISOR", "regras")
    ag = criar_agente("falso:1b", ClienteFalso({"abertura": "Claro.", "fechamento": None}))
    assert isinstance(ag.decisor, RegrasDecisor) and ag.redator is not None and ag.concisao
    assert ag.responder("c1", "qual o horário de vocês?", "eval").texto.startswith("Claro.")
    monkeypatch.delenv("EMPORIO_DECISOR")
    assert isinstance(criar_agente("falso:1b", ClienteFalso({})).decisor, LlmDecisor)
