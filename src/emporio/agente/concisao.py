"""Concisão e redundância: o que já foi dito não volta sem pedido do cliente.

Blocos factuais necessários à resposta atual nunca são removidos. Só avisos, saudação e frases
repetidas (sem número) saem. A contagem de reapresentação vale também para o controle, que não
suprime nada.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from ..dados import banco
from ..dinheiro import formatar
from ..ferramentas.envelope import Fato
from ..texto import normalizar
from .estado import Estado

LIMIAR_FRASE_REPETIDA = 0.88
SAUDACAO = re.compile(r"\b(oi|ola|bom dia|boa tarde|boa noite)\b")


def renderizacoes(f: Fato) -> list[str]:
    """Como o valor de um fato aparece num texto ao cliente."""
    v = f.valor
    if isinstance(v, bool) or v is None:
        return []
    if isinstance(v, int):
        if f.atributo.endswith("_centavos"):
            return [formatar(v)]
        if f.atributo.startswith("percentual") or f.atributo.endswith("percentual"):
            return [f"{v}%"]
        return []
    if isinstance(v, str) and len(v) >= 4:
        return [normalizar(v)]
    return []


def _entregue(f: Fato, texto_norm: str, texto: str) -> bool:
    return any((r in texto) if r.startswith("R$") or r.endswith("%") else (r in texto_norm) for r in renderizacoes(f))


def registrar_entregas(estado: Estado, texto: str, fatos: list[Fato]) -> dict[str, int]:
    """Atualiza ja_informados com o que o texto mostrou e devolve as contagens do turno."""
    contagem = {"avisos_exibidos": 0, "avisos_reapresentados": 0, "fatos_exibidos": 0, "fatos_reapresentados": 0}
    intencao = estado.intencao or ""
    for a in estado.avisos_turno:
        if a["omitido"]:
            continue
        contagem["avisos_exibidos"] += 1
        contagem["avisos_reapresentados"] += int(a["reapresentado"])
        estado.ja_informados[a["chave"]] = {"valor": a["valor"], "intencao": intencao}
    norm = normalizar(texto)
    nomeadas = _entidades_pedidas(estado)
    vistos: set[str] = set()
    for f in fatos:
        chave = f"fato:{f.entidade_tipo}:{f.entidade_id}:{f.atributo}"
        if chave in vistos or not _entregue(f, norm, texto):
            continue
        vistos.add(chave)
        valor = str(f.valor)
        anterior = estado.ja_informados.get(chave)
        contagem["fatos_exibidos"] += 1
        # "sem pedido" = o fato já foi entregue, o assunto do turno é outro e o cliente não citou a entidade
        if (anterior is not None and anterior["valor"] == valor and anterior["intencao"] != intencao
                and str(f.entidade_id) not in nomeadas):
            contagem["fatos_reapresentados"] += 1
        estado.ja_informados[chave] = {"valor": valor, "intencao": intencao}
    return contagem


def _entidades_pedidas(estado: Estado) -> set[str]:
    """Produto ou pedido que o próprio cliente citou neste turno (resolvido por ferramenta)."""
    ids: set[str] = set()
    for p in estado.passos:
        d = p.resultado.dados
        if p.ferramenta == "ver_produto" and p.resultado.estado == "ok":
            ids.add(str(d["id"]))
        elif p.ferramenta == "consultar_pedido" and p.resultado.estado == "ok":
            ids.add(str(d["pedido_id"]))
    return ids


def _frases(linha: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", linha) if p]


def _protegida(frase: str) -> bool:
    return bool(re.search(r"\d|R\$|\?|Responda", frase)) or frase.lstrip().startswith("-")


def _parecida(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= LIMIAR_FRASE_REPETIDA


def deduplicar_frases(texto: str, anteriores: list[str]) -> tuple[str, int]:
    """Remove frase repetida ou quase igual, dentro do turno e frente às respostas anteriores."""
    vistas = [normalizar(f) for t in anteriores for ln in t.splitlines() for f in _frases(ln)]
    removidas = 0
    saida: list[str] = []
    for linha in texto.splitlines():
        mantidas: list[str] = []
        for frase in _frases(linha):
            n = normalizar(frase)
            if not _protegida(frase) and any(_parecida(n, v) for v in vistas):
                removidas += 1
                continue
            mantidas.append(frase)
            vistas.append(n)
        if mantidas:
            saida.append(" ".join(mantidas))
        elif not linha.strip():
            saida.append(linha)
    return "\n".join(saida).strip(), removidas


def respostas_anteriores(conversa_id: str, limite: int = 8) -> list[str]:
    conn = banco.conectar()
    try:
        linhas = conn.execute("SELECT texto FROM mensagens_exibidas WHERE conversa_id = ? ORDER BY id DESC LIMIT ?",
                              (conversa_id, limite)).fetchall()
    finally:
        conn.close()
    return [r["texto"] for r in reversed(linhas)]


def tem_saudacao(texto: str) -> bool:
    return bool(SAUDACAO.search(normalizar(texto)))


def resumo_contagens(*parciais: dict[str, Any]) -> dict[str, int]:
    total: dict[str, int] = {}
    for p in parciais:
        for k, v in p.items():
            total[k] = total.get(k, 0) + int(v)
    return total
