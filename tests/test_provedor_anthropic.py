"""Provedor anthropic com cliente e SDK falsos: sem rede, sem chave, sem o pacote instalado."""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from emporio.agente import llm, provedores


class _ErroBase(Exception):
    pass


class APIConnectionError(_ErroBase):
    pass


class APITimeoutError(APIConnectionError):
    pass


class RateLimitError(_ErroBase):
    pass


class APIStatusError(_ErroBase):
    status_code = 500


@pytest.fixture
def sdk(monkeypatch):
    modulo = types.ModuleType("anthropic")
    for classe in (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError):
        setattr(modulo, classe.__name__, classe)
    modulo.Anthropic = lambda: (_ for _ in ()).throw(AssertionError("cliente real nao pode ser criado"))
    monkeypatch.setitem(sys.modules, "anthropic", modulo)
    monkeypatch.setenv("EMPORIO_PROVEDOR", "anthropic")
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    yield modulo
    provedores.usar_cliente(None)


class Falso:
    def __init__(self, resposta=None, erro=None):
        self.chamadas = []
        self.resposta = resposta
        self.erro = erro
        self.messages = self

    def create(self, **kw):
        self.chamadas.append(kw)
        if self.erro:
            raise self.erro
        return self.resposta


def _resp(blocos, entrada=11, saida=4):
    return SimpleNamespace(content=blocos, usage=SimpleNamespace(input_tokens=entrada, output_tokens=saida))


def _texto(t):
    return SimpleNamespace(type="text", text=t)


MSGS = [{"role": "system", "content": "sis"}, {"role": "user", "content": "oi"}]


def test_padrao_continua_ollama(monkeypatch):
    monkeypatch.delenv("EMPORIO_PROVEDOR", raising=False)
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    assert llm.provedor() == "ollama"
    assert llm.modelo_padrao() is None


def test_provedor_desconhecido_e_erro(monkeypatch):
    monkeypatch.setenv("EMPORIO_PROVEDOR", "xyz")
    with pytest.raises(llm.ErroModelo):
        llm.provedor()


def test_modelo_padrao_e_override(sdk, monkeypatch):
    assert llm.modelo_padrao() == "claude-haiku-5-5"
    monkeypatch.setenv("EMPORIO_MODELO", "claude-sonnet-5-5")
    assert llm.modelo_padrao() == "claude-sonnet-5-5"


def test_chamada_sem_parametros_proibidos_e_com_uso(sdk):
    falso = Falso(_resp([SimpleNamespace(type="thinking", thinking="x"), _texto('{"a":'), _texto("1}")]))
    provedores.usar_cliente(falso)
    r = llm.conversar("claude-haiku-5-5", MSGS, maximo_tokens=77, limite=9)
    kw = falso.chamadas[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["max_tokens"] == 77
    assert kw["system"] == "sis" and kw["messages"] == [{"role": "user", "content": "oi"}]
    assert kw["output_config"] == {"effort": "low"}
    for proibido in ("temperature", "top_p", "top_k"):
        assert proibido not in kw
    assert (r.conteudo, r.tokens_prompt, r.tokens_resposta) == ('{"a":1}', 11, 4)


def test_formato_json_vai_em_output_config_format(sdk):
    falso = Falso(_resp([_texto("{}")]))
    provedores.usar_cliente(falso)
    esquema = {"type": "object", "properties": {"x": {"type": "object", "properties": {}}}, "required": ["x"]}
    llm.conversar("claude-haiku-5-5", MSGS, formato=esquema)
    fmt = falso.chamadas[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False
    assert fmt["schema"]["properties"]["x"]["additionalProperties"] is False
    assert "additionalProperties" not in esquema  # o original não é alterado


@pytest.mark.parametrize("erro,esperado", [
    (APIConnectionError("rede"), llm.ErroModelo), (RateLimitError("429"), llm.ErroModelo),
    (APIStatusError("500"), llm.ErroModelo), (APITimeoutError("t"), llm.TimeoutModelo)])
def test_erros_do_sdk_viram_erro_modelo(sdk, erro, esperado):
    provedores.usar_cliente(Falso(erro=erro))
    with pytest.raises(esperado):
        llm.conversar("claude-haiku-5-5", MSGS)


def test_resposta_malformada_vira_erro_modelo(sdk):
    provedores.usar_cliente(Falso(SimpleNamespace(content=None, usage=None)))
    with pytest.raises(llm.ErroModelo):
        llm.conversar("claude-haiku-5-5", MSGS)


def test_conferir_modelo_nao_chama_a_api(sdk):
    falso = Falso(_resp([_texto("x")]))
    provedores.usar_cliente(falso)
    llm.conferir_modelo("claude-haiku-5-5")
    assert falso.chamadas == []


def test_cliente_sem_credencial_vira_erro_modelo(sdk):
    provedores.usar_cliente(None)  # o Anthropic() falso levanta
    with pytest.raises(llm.ErroModelo):
        llm.conferir_modelo("claude-haiku-5-5")


def test_saude_informa_provedor_e_modelo(sdk):
    from fastapi.testclient import TestClient
    from emporio.web.app import criar_app
    provedores.usar_cliente(Falso(_resp([_texto("x")])))
    corpo = TestClient(criar_app()).get("/saude").json()
    assert corpo["provedor"] == "anthropic" and corpo["nome_modelo"] == "claude-haiku-5-5"
