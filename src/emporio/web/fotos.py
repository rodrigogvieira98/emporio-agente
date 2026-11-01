"""Fotos de instrumentos: um único módulo decide qual foto cada produto e cada categoria usa.

As fotos são de licença livre (Wikimedia Commons: domínio público, CC0, CC BY ou CC BY-SA), guardadas em
`static/fotos/` como WebP. Autor, licença e link de cada uma ficam em `static/fotos/creditos.json`, que alimenta
`/creditos` e `docs/CREDITOS_IMAGENS.md`. O mapeamento usa palavras do nome e da categoria do produto, nunca o id
de um produto específico: produto novo cai na foto do seu tipo.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..texto import normalizar

PASTA = Path(__file__).resolve().parent / "static" / "fotos"
URL_BASE = "/static/fotos/"


@lru_cache(maxsize=1)
def creditos() -> dict[str, dict[str, Any]]:
    """Chave da foto -> metadados e crédito."""
    try:
        lista = json.loads((PASTA / "creditos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {f["chave"]: f for f in lista}


def _por_prefixo(prefixo: str) -> list[str]:
    return sorted(c for c in creditos() if c.startswith(prefixo))


def _escolher(prefixo: str, produto_id: int) -> str | None:
    opcoes = _por_prefixo(prefixo)
    return opcoes[produto_id % len(opcoes)] if opcoes else None


def _chave_do_produto(produto_id: int, nome: str, categoria: str | None) -> str | None:
    n, c = normalizar(nome), normalizar(categoria or "")
    if "violo" in c or "violao" in n:
        if "eletric" in n or "eletro" in n:
            return _escolher("violao-eletroacustico", produto_id)
        if "nylon" in n or "classic" in n:
            return _escolher("violao-nylon", produto_id)
        return _escolher("violao-folk", produto_id)
    if "ukulele" in c or "ukulele" in n:
        # o tamanho no nome decide: soprano usa a foto de soprano; os maiores usam a de corpo maior
        if "soprano" in n and "ukulele-1" in creditos():
            return "ukulele-1"
        if any(t in n for t in ("concert", "tenor", "baritono")) and "ukulele-2" in creditos():
            return "ukulele-2"
        return _escolher("ukulele", produto_id)
    if "guitarra" in c:
        # formato conhecido pelo nome: a foto do mesmo formato, quando o catálogo de fotos tem
        for trecho, chave in (("telecaster", "guitarra-telecaster"), ("les paul", "guitarra-les-paul"),
                              ("stratocaster", "guitarra-stratocaster")):
            if trecho in n and chave in creditos():
                return chave
        return _escolher("guitarra-corpo", produto_id) or _escolher("guitarra", produto_id)
    if "baix" in c:
        # Precision e Jazz Bass têm foto do formato quando existe; os demais variam entre as fotos de baixo
        if "precision" in n and "baixo-2" in creditos():
            return "baixo-2"
        if "ibanez" in n and "baixo-1" in creditos():
            return "baixo-1"
        return _escolher("baixo", produto_id)
    if "bateria" in c or "percussao" in c:
        return _escolher("bateria", produto_id)
    if "tecla" in c or "piano" in c:
        return _escolher("teclado", produto_id)
    if "sopro" in c:
        return _escolher("sopro", produto_id)
    if "corda" in c:
        return _escolher("cordas", produto_id)
    return None


def _ficha(chave: str | None) -> dict[str, Any] | None:
    f = creditos().get(chave or "")
    if not f:
        return None
    return {"chave": f["chave"], "src": URL_BASE + f["arquivo"], "alt": f["alt"], "largura": f["largura"],
            "altura": f["altura"]}


def foto_do_produto(produto_id: int, nome: str, categoria: str | None) -> dict[str, Any] | None:
    """Foto do tipo do produto, com variedade entre produtos do mesmo tipo; None se o catálogo não tem foto do tipo."""
    return _ficha(_chave_do_produto(produto_id, nome, categoria))


# categoria -> prefixo da foto que a representa
_CATEGORIAS = (("violo", "violao-nylon"), ("ukulele", "ukulele"), ("guitarra", "guitarra-corpo"), ("baix", "baixo"),
               ("bateria", "bateria"), ("tecla", "teclado"), ("sopro", "sopro"), ("corda", "cordas"))


def foto_da_categoria(categoria: str | None) -> dict[str, Any] | None:
    c = normalizar(categoria or "")
    for trecho, prefixo in _CATEGORIAS:
        if trecho in c:
            opcoes = _por_prefixo(prefixo)
            return _ficha(opcoes[0]) if opcoes else None
    return None


def foto_de_abertura() -> dict[str, Any] | None:
    return _ficha("abertura")


# banner da home: a abertura (violão) e mais quatro instrumentos, nesta ordem
CHAVES_DO_BANNER = ("abertura", "banner-guitarra", "banner-baixo", "banner-teclado", "banner-bateria")


def fotos_do_banner() -> list[dict[str, Any]]:
    """As fotos do banner que existem em `creditos.json`, na ordem de exibição (a primeira carrega de imediato)."""
    return [f for f in (_ficha(c) for c in CHAVES_DO_BANNER) if f]
