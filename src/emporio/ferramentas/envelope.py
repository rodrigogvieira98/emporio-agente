"""Envelope comum das ferramentas e decorator que garante o contrato.

Exceção interna vira `falha`; entrada inválida vira `falha` com motivo
`entrada_invalida`. Nada sobe ao laço.
"""
from __future__ import annotations

import functools
import inspect
import logging
import uuid
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

log = logging.getLogger("emporio.ferramentas")

Estado = Literal["ok", "vazio", "ambiguo", "negado", "falha"]


class Fonte(BaseModel):
    tipo: str  # banco, manual, calculo
    referencia: str
    versao: str | None = None


class Fato(BaseModel):
    entidade_tipo: str
    entidade_id: str | int
    atributo: str
    valor: Any
    condicao: str | None = None
    fonte: Fonte


class Resultado(BaseModel):
    estado: Estado
    dados: dict[str, Any] = {}
    fontes: list[Fonte] = []
    motivo: str | None = None
    id_consulta: str

    @property
    def ok(self) -> bool:
        return self.estado == "ok"


def novo_id() -> str:
    return uuid.uuid4().hex[:12]


def resultado(estado: Estado, dados: dict[str, Any] | None = None, fontes: list[Fonte] | None = None,
              motivo: str | None = None) -> Resultado:
    return Resultado(estado=estado, dados=dados or {}, fontes=fontes or [], motivo=motivo, id_consulta=novo_id())


class EntradaBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def ferramenta(modelo: type[EntradaBase]) -> Callable:
    """Valida a entrada com o modelo e protege a função contra exceções."""

    def decorador(func: Callable[..., Resultado]) -> Callable[..., Resultado]:
        campos = list(modelo.model_fields)

        @functools.wraps(func)
        def envolvida(*args: Any, **kwargs: Any) -> Resultado:
            try:
                if len(args) > len(campos):
                    return resultado("falha", motivo="entrada_invalida")
                bruto = dict(zip(campos, args))
                repetidos = set(bruto) & set(kwargs)
                if repetidos:
                    return resultado("falha", motivo="entrada_invalida")
                bruto.update(kwargs)
                entrada = modelo.model_validate(bruto)
            except ValidationError:
                return resultado("falha", motivo="entrada_invalida")
            try:
                saida = func(entrada)
                if not isinstance(saida, Resultado):
                    raise TypeError("ferramenta devolveu algo que nao e Resultado")
                return saida
            except LookupError:  # chave ausente no manual: o dado de loja não existe
                log.exception("dado ausente em %s", func.__name__)
                return resultado("falha", motivo="dado_ausente")
            except Exception:  # noqa: BLE001 - a fronteira existe para isso
                log.exception("falha interna em %s", func.__name__)
                return resultado("falha", motivo="erro_interno")

        envolvida.modelo_entrada = modelo  # type: ignore[attr-defined]
        envolvida.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
        return envolvida

    return decorador
