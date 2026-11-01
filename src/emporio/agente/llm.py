"""Cliente do Ollama só com a stdlib. Temperatura 0, semente 42, raciocínio desligado.

Ambiente: OLLAMA_HOST (padrão http://localhost:11434), EMPORIO_MODELO (modelo padrão),
EMPORIO_LLM_TIMEOUT (segundos, padrão 120).
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

SEMENTE = 42


class ErroModelo(Exception):
    """Conexão, HTTP ou corpo inválido."""


class TimeoutModelo(ErroModelo):
    pass


@dataclass
class RespostaLlm:
    conteudo: str
    tokens_prompt: int
    tokens_resposta: int
    latencia_ms: int


def host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def modelo_padrao() -> str | None:
    return os.environ.get("EMPORIO_MODELO") or None


def timeout_s() -> float:
    try:
        return float(os.environ.get("EMPORIO_LLM_TIMEOUT", "120"))
    except ValueError:
        return 120.0


def _requisitar(caminho: str, corpo: dict[str, Any] | None, limite: float) -> dict[str, Any]:
    url = host() + caminho
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json"},
                                 method="POST" if dados is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=limite) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (socket.timeout, TimeoutError) as erro:
        raise TimeoutModelo(f"timeout de {limite}s em {caminho}") from erro
    except urllib.error.HTTPError as erro:
        corpo_erro = erro.read().decode("utf-8", "replace")[:200]
        raise ErroModelo(f"HTTP {erro.code} em {url}: {corpo_erro}") from erro
    except urllib.error.URLError as erro:
        if isinstance(erro.reason, (socket.timeout, TimeoutError)):
            raise TimeoutModelo(f"timeout de {limite}s em {caminho}") from erro
        raise ErroModelo(f"sem conexao com {url}: {erro.reason}") from erro
    except (OSError, ValueError) as erro:
        raise ErroModelo(f"resposta invalida de {url}: {erro}") from erro


def modelos_instalados() -> list[str]:
    return [m["name"] for m in _requisitar("/api/tags", None, 5).get("models", [])]


def conferir_modelo(modelo: str) -> None:
    """Levanta ErroModelo se o Ollama não responde ou não tem o modelo."""
    instalados = modelos_instalados()
    if modelo not in instalados and f"{modelo}:latest" not in instalados:
        raise ErroModelo(f"modelo {modelo!r} nao esta instalado no Ollama")


def conversar(modelo: str, mensagens: list[dict[str, str]], formato: dict[str, Any] | None = None,
              limite: float | None = None, maximo_tokens: int = 400) -> RespostaLlm:
    corpo: dict[str, Any] = {
        "model": modelo, "messages": mensagens, "stream": False, "think": False,
        "options": {"temperature": 0, "seed": SEMENTE, "num_predict": maximo_tokens},
    }
    if formato is not None:
        corpo["format"] = formato
    inicio = time.perf_counter()
    bruto = _requisitar("/api/chat", corpo, limite or timeout_s())
    try:
        conteudo = bruto["message"]["content"]
    except (KeyError, TypeError) as erro:
        raise ErroModelo("resposta sem message.content") from erro
    return RespostaLlm(conteudo=conteudo, tokens_prompt=int(bruto.get("prompt_eval_count") or 0),
                       tokens_resposta=int(bruto.get("eval_count") or 0),
                       latencia_ms=int((time.perf_counter() - inicio) * 1000))


def aquecer(modelo: str, limite: float = 900.0) -> int:
    """Carrega o modelo na memória antes da medição; devolve a latência da carga em ms."""
    return conversar(modelo, [{"role": "user", "content": "ok"}], limite=limite, maximo_tokens=1).latencia_ms


def mensagens_do_modelo(modelo: str, sistema: str, usuario: str) -> list[dict[str, str]]:
    if modelo.startswith("qwen3"):
        sistema += "\n/no_think"  # reforço: o think:false do servidor nem sempre vale para esta família
    return [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
