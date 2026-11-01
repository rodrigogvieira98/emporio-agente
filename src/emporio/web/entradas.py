"""Entradas do navegador: só dígitos ASCII, com limite de tamanho, antes de qualquer conversão ou consulta.

`int()` e `isdigit()` do Python aceitam dígitos de outros alfabetos e números gigantes, que estouram o banco.
Aqui um inteiro válido é `[0-9]` de 1 a 9 posições.
"""
from __future__ import annotations

import re

from .. import dinheiro

MAX_DIGITOS = 9  # limite do sistema, não é regra de loja
_INTEIRO = re.compile(r"[0-9]{1,%d}" % MAX_DIGITOS)
_MILHAR = re.compile(r"[0-9]{1,3}(\.[0-9]{3})+")
_REAIS = re.compile(r"[0-9]{1,%d}(\.[0-9]{1,2})?" % MAX_DIGITOS)

ERRO_PRECO = "Use apenas números nos campos de preço."
ERRO_PRECO_NEGATIVO = "O preço não pode ser negativo."


def inteiro(valor: str | None) -> int | None:
    """Inteiro não negativo escrito só com 0 a 9 e até 9 dígitos; qualquer outra coisa vira None."""
    v = valor or ""
    return int(v) if _INTEIRO.fullmatch(v) else None


def numero_de_pedido(valor: str | None) -> str | None:
    """Número de pedido do sistema legado (só dígitos ASCII, até 9)."""
    v = (valor or "").strip()
    return v if _INTEIRO.fullmatch(v) else None


def preco_em_centavos(texto: str | None) -> tuple[int | None, str | None]:
    """Centavos e erro. Aceita milhar com ponto, vírgula decimal e o prefixo da moeda; recusa negativo e lixo."""
    t = (texto or "").strip()
    if not t:
        return None, None
    t = re.sub(r"^R\$\s*", "", t, flags=re.IGNORECASE)
    if t.startswith("-"):
        return None, ERRO_PRECO_NEGATIVO
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif _MILHAR.fullmatch(t):
        t = t.replace(".", "")
    if not _REAIS.fullmatch(t):
        return None, ERRO_PRECO
    return dinheiro.para_centavos(t), None
