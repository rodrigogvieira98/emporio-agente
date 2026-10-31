"""Dinheiro: centavos inteiros no armazenamento, Decimal no cálculo."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("1")


def para_centavos(valor: str | int | Decimal) -> int:
    """Converte reais (texto ou Decimal) em centavos. Float é recusado."""
    if isinstance(valor, float):
        raise TypeError("float nao e aceito para dinheiro")
    return int((Decimal(str(valor)) * 100).quantize(CENTAVO, rounding=ROUND_HALF_UP))


def arredondar(valor: Decimal) -> int:
    return int(valor.quantize(CENTAVO, rounding=ROUND_HALF_UP))


def aplicar_desconto(centavos: int, percentual: int | Decimal) -> int:
    return arredondar(Decimal(centavos) * (Decimal(100) - Decimal(percentual)) / Decimal(100))


def dividir(centavos: int, partes: int) -> int:
    return arredondar(Decimal(centavos) / Decimal(partes))


def formatar(centavos: int) -> str:
    sinal = "-" if centavos < 0 else ""
    reais, cent = divmod(abs(centavos), 100)
    return f"{sinal}R$ {reais:,}".replace(",", ".") + f",{cent:02d}"
