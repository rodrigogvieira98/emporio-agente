"""Redação delimitada: o modelo só escreve abertura ou fechamento curtos em volta do bloco factual.

O bloco vem de respostas.py e nunca é alterado. O texto livre só passa se não tiver dígito, moeda,
nome de produto fora do bloco, verbo de ação não confirmada, mais de 2 frases ou mais de 1 pergunta.
Reprovado, o texto livre é descartado e a resposta é só o bloco controlado.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from ..texto import normalizar, tokens
from . import catalogo, llm, persona
from . import vocabulario as v
from .concisao import deduplicar_frases, tem_saudacao
from .estado import Estado

SISTEMA = (
    "Escreva uma abertura curta e/ou um fechamento "
    "curto em volta do texto da loja que será mostrado ao cliente. Regras: no máximo 2 frases no total e no máximo "
    "1 pergunta; informal e educado; sem números, sem valores, sem nomes de produto, sem prometer nem dizer que fez "
    "algo (transferir, reservar, cancelar, aprovar). Se não houver nada útil a acrescentar, devolva null nos dois "
    "campos. Responda só com o JSON pedido."
)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"abertura": {"type": ["string", "null"]}, "fechamento": {"type": ["string", "null"]}},
    "required": ["abertura", "fechamento"],
}
VERBOS_NAO_CONFIRMADOS = re.compile(
    r"\b(transferi|reservei|cancelei|aprovei|estornei|reembolsei|enviei|agendei|liberei|registrei|encaminhei|"
    r"confirmei|devolvi|garanto|garantimos|prometo|vou reservar|vou transferir|vou cancelar)\b")
MOEDA = re.compile(r"R\$|\breais?\b|\bcentavos?\b|%")
# Rótulos do prompt (chaves do JSON de entrada e campos da saída) que o modelo às vezes devolve como texto.
ECO_DE_ROTULO = re.compile(
    r"\b(texto[ _]da[ _]loja|mensagem[ _]do[ _]cliente)\b|(?:^|\n)\s*(?:abertura|fechamento)\s*[:=-]|[{}]", re.I)
LIMIAR_REPETE_BLOCO = 0.8
MAX_FRASES = 2
MAX_PERGUNTAS = 1
MAX_CARACTERES = 220


def sistema() -> str:
    """Instruções de cada turno redigido: a persona primeiro, depois as regras da redação."""
    return f"{persona.instrucoes()} {SISTEMA}"


def _frases(texto: str) -> list[str]:
    return [f for f in re.split(r"(?<=[.!?])\s+", texto.strip()) if f]


def repete_o_bloco(frase: str, bloco: str) -> bool:
    """Frase do modelo que só repete, com outras palavras ou por inteiro, o que o bloco factual já diz."""
    n = normalizar(frase)
    palavras = len(n.split())
    for linha in bloco.splitlines():
        for parte in _frases(linha):
            b = normalizar(parte)
            if not b:
                continue
            if palavras >= 3 and (n in b or (len(b.split()) >= 3 and b in n)):
                return True
            if SequenceMatcher(None, n, b).ratio() >= LIMIAR_REPETE_BLOCO:
                return True
    return False


def validar(livre: str, bloco: str, estado: Estado) -> str | None:
    """Devolve o motivo da reprovação, ou None se o texto livre pode ser exibido."""
    norm = normalizar(livre)
    if ECO_DE_ROTULO.search(normalizar(livre)) or ECO_DE_ROTULO.search(livre):
        return "eco_de_rotulo"
    if re.search(r"\d", livre):
        return "digito"
    if MOEDA.search(livre):
        return "moeda"
    if VERBOS_NAO_CONFIRMADOS.search(norm):
        return "verbo_de_acao"
    if len(livre) > MAX_CARACTERES:
        return "longo"
    if len(_frases(livre)) > MAX_FRASES:
        return "frases"
    if livre.count("?") + bloco.count("?") > MAX_PERGUNTAS:
        return "perguntas"
    if estado.ja_saudou and tem_saudacao(livre):
        return "saudacao_repetida"
    voc = catalogo.vocabulario()
    do_bloco = set(tokens(bloco))
    for t in tokens(livre):
        identifica = t in voc.df and (voc.df[t] <= 4 or re.search(r"\d", t)) and t not in v.PALAVRAS_SOLTAS
        if identifica and t not in do_bloco:
            return "produto_fora_do_bloco"
    return None


class Redator:
    def __init__(self, modelo: str, cliente: Any = None) -> None:
        self.modelo = modelo
        self.cliente = cliente or llm
        self.telemetria: list[dict[str, Any]] = []
        self.contagens: dict[str, int] = {}

    def _contar(self, chave: str) -> None:
        self.contagens[chave] = self.contagens.get(chave, 0) + 1

    def envolver(self, estado: Estado, mensagem: str, bloco: str, permitir_fechamento: bool,
                 anteriores: list[str] | None = None) -> str:
        reg: dict[str, Any] = {"componente": "redacao", "modelo": self.modelo}
        entrada = json.dumps({"mensagem_do_cliente": mensagem[:300], "texto_da_loja": bloco}, ensure_ascii=False)
        self._contar("redacao_tentada")  # denominador dos descartes: só turno com chamada ao modelo
        try:
            r = self.cliente.conversar(self.modelo, llm.mensagens_do_modelo(self.modelo, sistema(), entrada),
                                       formato=SCHEMA, maximo_tokens=120)
        except llm.TimeoutModelo as erro:
            self._contar("timeout")
            reg.update(resultado="bloco_apenas:timeout", detalhe=str(erro))
            self.telemetria.append(reg)
            return bloco
        except llm.ErroModelo as erro:
            self._contar("erro_modelo")
            reg.update(resultado="bloco_apenas:erro_modelo", detalhe=str(erro))
            self.telemetria.append(reg)
            return bloco
        reg.update(texto_bruto=r.conteudo, tokens_prompt=r.tokens_prompt, tokens_resposta=r.tokens_resposta,
                   latencia_ms=r.latencia_ms, num_ctx=getattr(r, "num_ctx", None))
        try:
            dados = json.loads(r.conteudo)
            abertura = (dados.get("abertura") or "").strip()
            fechamento = (dados.get("fechamento") or "").strip() if permitir_fechamento else ""
            if not isinstance(dados.get("abertura"), (str, type(None))) or not isinstance(dados.get("fechamento"), (str, type(None))):
                raise ValueError("campos com tipo errado")
        except (ValueError, AttributeError):
            self._contar("redacao_descartada")
            reg.update(resultado="descartada:formato")
            self.telemetria.append(reg)
            return bloco
        # frase do modelo que repete o bloco sai; o bloco nunca é alterado
        abertura = " ".join(f for f in _frases(abertura) if not repete_o_bloco(f, bloco))
        fechamento = " ".join(f for f in _frases(fechamento) if not repete_o_bloco(f, bloco))
        if anteriores:  # frase livre já dita antes não se repete (o bloco factual nunca passa por aqui)
            abertura, _ = deduplicar_frases(abertura, anteriores)
            fechamento, _ = deduplicar_frases(fechamento, anteriores)
        livre = " ".join(x for x in (abertura, fechamento) if x)
        if not livre:
            reg.update(resultado="vazia")
            self.telemetria.append(reg)
            return bloco
        motivo = validar(livre, bloco, estado)
        if motivo:
            self._contar("redacao_descartada")
            reg.update(resultado=f"descartada:{motivo}")
            self.telemetria.append(reg)
            return bloco
        reg["resultado"] = "aceita"
        self._contar("redacao_exibida")
        self.telemetria.append(reg)
        partes = [abertura, bloco, fechamento]
        return "\n".join(p for p in partes if p)

    def drenar(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        t, c = self.telemetria, self.contagens
        self.telemetria, self.contagens = [], {}
        return t, c
