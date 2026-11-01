"""Sentimento do turno: neutro, frustrado ou irritado, por regras. Muda só o tom, nunca fatos nem permissões.

Cada sinal soma pontos; frustrado a partir de LIMIAR_FRUSTRADO, irritado a partir de LIMIAR_IRRITADO. Um sinal sozinho
e fraco (caixa alta ou pontuação isolada) fica neutro. Palavra de emoção negada ("não estou bravo") não conta.
Ironia não é tentada. O rótulo vai para o estado e para o trace; o texto do cliente não.
"""
from __future__ import annotations

import hashlib
import re

from ..texto import normalizar
from .estado import Estado

NEUTRO, FRUSTRADO, IRRITADO = "neutro", "frustrado", "irritado"
LIMIAR_FRUSTRADO = 4
LIMIAR_IRRITADO = 8

PONTOS_FORTE = 8  # ofensa ou raiva explícita
PONTOS_MEDIO = 4  # frustração explícita
PONTOS_CAIXA_ALTA = 2
PONTOS_PONTUACAO = 2
PONTOS_REPETIDA = 3
PONTOS_FALHAS = 4

FORTE = re.compile(
    r"\b(absurdo|ridicul\w*|lixo|porcaria|palhacada|incompetent\w*|vergonha|vergonhos\w*|pessim\w*|horrivel|horriveis|"
    r"odio|inutil|inuteis|merda|procon|processar|nunca mais|furios\w*|puto|puta|revoltad\w*|indignad\w*|idiota\w*|"
    r"burr\w*|estupid\w*|desrespeit\w*)\b")
MEDIO = re.compile(
    r"\b(de novo|ninguem (me )?(responde|ajuda|resolve|atende|explica)|ja (falei|disse|expliquei|perguntei)|cansei|"
    r"cansad\w*|irritante|irritad\w*|bravo|brava|chatead\w*|chato|nervos\w*|decepcionad\w*|sem resposta|"
    r"ate agora nada|nao resolve\w*|nao (me )?entende\w*|que demora|demora demais|sempre a mesma coisa|"
    r"de novo isso|estressad\w*)\b")
NEGACAO = {"nao", "nem", "sem", "nunca", "jamais"}
PONTUACAO_REPETIDA = re.compile(r"(!{2,}|\?{2,}|\?!|!\?)")


def _negada(norm: str, inicio: int) -> bool:
    antes = norm[:inicio].split()[-3:]
    return any(t in NEGACAO for t in antes)


def _pontos_lexico(norm: str) -> int:
    pontos = 0
    for padrao, valor in ((FORTE, PONTOS_FORTE), (MEDIO, PONTOS_MEDIO)):
        for m in padrao.finditer(norm):
            if m.group(0).startswith("nunca"):  # "nunca mais" é a própria expressão, não uma negação
                pontos = max(pontos, valor)
            elif not _negada(norm, m.start()):
                pontos = max(pontos, valor)
    return pontos


def _caixa_alta(mensagem: str) -> bool:
    letras = [c for c in mensagem if c.isalpha()]
    return len(letras) >= 8 and sum(c.isupper() for c in letras) / len(letras) >= 0.6


def assinatura(mensagem: str) -> str:
    """Resumo da mensagem para detectar repetição sem guardar o texto do cliente."""
    return hashlib.sha1(normalizar(mensagem).encode("utf-8")).hexdigest()[:16]


def detectar(mensagem: str, estado: Estado) -> str:
    norm = normalizar(mensagem)
    pontos = _pontos_lexico(norm)
    if _caixa_alta(mensagem):
        pontos += PONTOS_CAIXA_ALTA
    if PONTUACAO_REPETIDA.search(mensagem):
        pontos += PONTOS_PONTUACAO
    if pontos > 0 and len(norm) >= 12 and estado.assinatura_ultima_mensagem == assinatura(mensagem):
        pontos += PONTOS_REPETIDA  # repetir a mesma pergunta só pesa junto de outro sinal; calmo, não é frustração
    if estado.falhas_seguidas >= 2:
        pontos += PONTOS_FALHAS
    if pontos >= LIMIAR_IRRITADO:
        return IRRITADO
    return FRUSTRADO if pontos >= LIMIAR_FRUSTRADO else NEUTRO


def registrar(estado: Estado, mensagem: str) -> str:
    """Detecta, guarda o rótulo do turno e a assinatura da mensagem. Chamado uma vez por turno."""
    rotulo = detectar(mensagem, estado)
    estado.sentimentos = (estado.sentimentos + [rotulo])[-6:]
    estado.assinatura_ultima_mensagem = assinatura(mensagem)
    return rotulo
