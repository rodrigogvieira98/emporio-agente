"""Normalização de texto para comparação."""
from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def tokens(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalizar(texto))


def radical(token: str) -> str:
    """Tira plural simples (violoes -> violao, guitarras -> guitarra)."""
    if len(token) > 4 and token.endswith(("oes", "aes")):
        return token[:-3] + "ao"
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token
