"""Carrega o YAML do manual. Única fonte de fatos de loja fora do banco."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .. import config
from ..ferramentas.envelope import Fato, Fonte


class ManualErro(Exception):
    pass


class Condicao(BaseModel):
    chave: str
    valor: Any
    unidade: str | None = None
    base: str | None = None


class Secao(BaseModel):
    id: str
    titulo: str
    pagina: int
    temas: list[str]
    publico: bool
    texto: str
    condicoes: list[Condicao]
    versao: str
    hash: str


class Ambiguidade(BaseModel):
    id: str
    descricao: str
    secoes: list[str]
    temas: list[str]
    tratamento: str


class Manual(BaseModel):
    versao: str
    titulo: str
    secoes: list[Secao]
    ambiguidades: list[Ambiguidade]

    def secao(self, id_: str) -> Secao | None:
        return next((s for s in self.secoes if s.id == id_), None)

    def temas_conhecidos(self) -> set[str]:
        return {t for s in self.secoes for t in s.temas}

    def condicao(self, chave: str) -> tuple[Secao, Condicao] | None:
        for s in self.secoes:
            for c in s.condicoes:
                if c.chave == chave:
                    return s, c
        return None

    def ambiguidades_da_secao(self, id_: str) -> list[Ambiguidade]:
        return [a for a in self.ambiguidades if id_ in a.secoes]


def _hash(secao: dict) -> str:
    canonico = json.dumps({k: secao.get(k) for k in ("id", "titulo", "texto", "condicoes")},
                          sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@lru_cache(maxsize=8)
def _ler(caminho: str, mtime_ns: int) -> Manual:
    bruto = yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))
    try:
        versao = str(bruto["manual"]["versao"])
        secoes = []
        for s in bruto["secoes"]:
            secoes.append(Secao(id=str(s["id"]), titulo=s["titulo"], pagina=s["pagina"], temas=s["temas"],
                                publico=bool(s["publico"]), texto=(s.get("texto") or "").strip(),
                                condicoes=[Condicao(**c) for c in (s.get("condicoes") or [])],
                                versao=versao, hash=_hash({**s, "id": str(s["id"])})))
        ambiguidades = [Ambiguidade(**{**a, "secoes": [str(x) for x in a["secoes"]]})
                        for a in bruto.get("ambiguidades", [])]
        return Manual(versao=versao, titulo=bruto["manual"]["titulo"], secoes=secoes, ambiguidades=ambiguidades)
    except (KeyError, TypeError, ValueError) as erro:
        raise ManualErro(f"manual invalido em {caminho}: {erro}") from erro


def carregar_manual() -> Manual:
    """Relê o arquivo quando ele muda (o teste de troca de YAML depende disso)."""
    caminho = config.caminho_manual()
    return _ler(str(caminho), caminho.stat().st_mtime_ns)


def fonte_da_secao(secao: Secao) -> Fonte:
    return Fonte(tipo="manual", referencia=f"secao {secao.id}", versao=secao.versao)


def fato(chave: str) -> Fato | None:
    """Resposta rápida da mesma fonte: o valor de uma condição, com sua origem."""
    achado = carregar_manual().condicao(chave)
    if achado is None:
        return None
    secao, cond = achado
    return Fato(entidade_tipo="politica", entidade_id=secao.id, atributo=cond.chave, valor=cond.valor,
                condicao=cond.unidade, fonte=fonte_da_secao(secao))


def valor(chave: str) -> Any:
    """Valor de uma condição; levanta KeyError se a chave não existir no manual."""
    f = fato(chave)
    if f is None:
        raise KeyError(f"manual sem a chave {chave}")
    return f.valor
