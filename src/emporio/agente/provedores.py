"""Provedor `anthropic`: SDK oficial, importado só quando escolhido.

Chave lida pelo próprio SDK (ANTHROPIC_API_KEY ou perfil do `ant auth login`); nada é gravado aqui.
Sem temperature, top_p nem top_k. Erros do SDK viram ErroModelo.
"""
from __future__ import annotations

import copy
import time
from typing import Any

from . import llm

MODELO_ANTHROPIC_PADRAO = "claude-haiku-5-5"

_cliente: Any = None  # criado sob demanda; os testes injetam um falso por usar_cliente()


def usar_cliente(cliente: Any) -> None:
    """Injeta o cliente (testes). None volta a criar o cliente real na próxima chamada."""
    global _cliente
    _cliente = cliente


def _sdk() -> Any:
    try:
        import anthropic
    except ImportError as erro:
        raise llm.ErroModelo("pacote 'anthropic' ausente: pip install -r requirements-api.txt") from erro
    return anthropic


def _obter_cliente() -> Any:
    global _cliente
    if _cliente is None:
        sdk = _sdk()
        try:
            _cliente = sdk.Anthropic()
        except Exception as erro:  # sem credencial, configuração inválida
            raise llm.ErroModelo(f"cliente anthropic indisponivel: {erro}") from erro
    return _cliente


def _esquema_estrito(esquema: Any) -> Any:
    """Cópia do esquema com additionalProperties=false em todo objeto, como a API exige."""
    novo = copy.deepcopy(esquema)

    def visitar(no: Any) -> None:
        if isinstance(no, dict):
            if no.get("type") == "object" and "additionalProperties" not in no:
                no["additionalProperties"] = False
            for valor in no.values():
                visitar(valor)
        elif isinstance(no, list):
            for item in no:
                visitar(item)

    visitar(novo)
    return novo


def conferir_modelo(modelo: str) -> None:
    """Não chama a API (custo e latência no /saude): só garante que o cliente pode ser criado."""
    if not modelo:
        raise llm.ErroModelo("modelo anthropic nao informado")
    _obter_cliente()


def conversar(modelo: str, mensagens: list[dict[str, str]], formato: dict[str, Any] | None,
              limite: float, maximo_tokens: int) -> llm.RespostaLlm:
    sdk = _sdk()
    cliente = _obter_cliente()
    sistema = "\n\n".join(m["content"] for m in mensagens if m["role"] == "system")
    conversa = [{"role": m["role"], "content": m["content"]} for m in mensagens if m["role"] != "system"]
    config: dict[str, Any] = {"effort": "low"}
    if formato is not None:
        config["format"] = {"type": "json_schema", "schema": _esquema_estrito(formato)}
    args: dict[str, Any] = {"model": modelo, "max_tokens": maximo_tokens, "messages": conversa,
                            "output_config": config, "timeout": limite}
    if sistema:
        args["system"] = sistema
    inicio = time.perf_counter()
    try:
        resposta = cliente.messages.create(**args)
    except sdk.APITimeoutError as erro:
        raise llm.TimeoutModelo(f"timeout de {limite}s na API anthropic") from erro
    except sdk.APIConnectionError as erro:
        raise llm.ErroModelo(f"sem conexao com a API anthropic: {erro}") from erro
    except sdk.RateLimitError as erro:
        raise llm.ErroModelo(f"limite de uso da API anthropic: {erro}") from erro
    except sdk.APIStatusError as erro:
        raise llm.ErroModelo(f"HTTP {getattr(erro, 'status_code', '?')} da API anthropic: {erro}") from erro
    try:
        texto = "".join(b.text for b in resposta.content if b.type == "text")
        entrada = int(resposta.usage.input_tokens or 0)
        saida = int(resposta.usage.output_tokens or 0)
    except (AttributeError, TypeError) as erro:
        raise llm.ErroModelo("resposta anthropic sem conteudo ou uso") from erro
    return llm.RespostaLlm(conteudo=texto, tokens_prompt=entrada, tokens_resposta=saida,
                           latencia_ms=int((time.perf_counter() - inicio) * 1000))
