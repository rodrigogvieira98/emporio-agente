"""registrar_encaminhamento e as funções próprias de transição de estado do chamado."""
from __future__ import annotations

import re
import sqlite3
from typing import Literal

from pydantic import field_validator

from .. import config
from ..dados import banco
from .envelope import EntradaBase, Fonte, Resultado, ferramenta, resultado

TIPOS = ("reclamacao", "atendente", "duvida_politica", "sem_dado", "falhas")
ESTADOS = ("registrado", "encaminhamento_pendente", "atendimento_iniciado")
TRANSICOES = {"registrado": "encaminhamento_pendente", "encaminhamento_pendente": "atendimento_iniciado"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_TELEFONE = re.compile(r"(?<!\d)(?:\+?55[\s-]?)?(?:\(?\d{2}\)?[\s-]?)?9?\d{4}[\s-]?\d{4}(?!\d)")


def tem_dado_pessoal(texto: str) -> bool:
    return bool(_EMAIL.search(texto) or _TELEFONE.search(texto))


def mascarar_dado_pessoal(texto: str) -> str:
    return _TELEFONE.sub("[telefone removido]", _EMAIL.sub("[e-mail removido]", texto))


class EntradaEncaminhamento(EntradaBase):
    conversa_id: str
    tipo: Literal["reclamacao", "atendente", "duvida_politica", "sem_dado", "falhas"]
    resumo: str
    chave_idempotencia: str

    @field_validator("conversa_id", "resumo", "chave_idempotencia")
    @classmethod
    def _nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("vazio")
        return v


def _dados(linha: sqlite3.Row, repetido: bool) -> dict:
    dados = {"protocolo": linha["protocolo"], "tipo": linha["tipo"], "status": linha["status"],
             "repetido": repetido}
    if linha["tipo"] == "reclamacao":
        from ..politicas import manual  # prazo vem do manual, não do código

        fato = manual.fato("atendimento.prazo_retorno_reclamacao_horas_uteis")
        if fato is not None:
            dados["prazo_retorno_horas_uteis"] = fato.valor
    return dados


@ferramenta(EntradaEncaminhamento)
def registrar_encaminhamento(e: EntradaEncaminhamento) -> Resultado:
    if tem_dado_pessoal(e.resumo):
        return resultado("negado", motivo="resumo_com_dado_pessoal")
    conn = banco.conectar()
    try:
        existente = conn.execute("SELECT * FROM chamados WHERE chave_idempotencia = ?",
                                 (e.chave_idempotencia,)).fetchone()
        if existente:
            return resultado("ok", _dados(existente, True),
                             [Fonte(tipo="banco", referencia=f"chamados/{existente['protocolo']}")])
        agora = config.agora().isoformat()
        with conn:  # erro de gravação sobe e o decorator devolve falha
            cur = conn.execute(
                "INSERT INTO chamados (protocolo, conversa_id, tipo, resumo, status, chave_idempotencia, "
                "criado_em, atualizado_em) VALUES ('', ?, ?, ?, 'registrado', ?, ?, ?)",
                (e.conversa_id, e.tipo, e.resumo.strip(), e.chave_idempotencia, agora, agora))
            protocolo = f"EM-{cur.lastrowid:06d}"
            conn.execute("UPDATE chamados SET protocolo = ? WHERE id = ?", (protocolo, cur.lastrowid))
        linha = conn.execute("SELECT * FROM chamados WHERE id = ?", (cur.lastrowid,)).fetchone()
        return resultado("ok", _dados(linha, False), [Fonte(tipo="banco", referencia=f"chamados/{protocolo}")])
    finally:
        conn.close()


def _transitar(protocolo: str, destino: str) -> Resultado:
    conn = banco.conectar()
    try:
        linha = conn.execute("SELECT * FROM chamados WHERE protocolo = ?", (protocolo,)).fetchone()
        if not linha:
            return resultado("vazio", motivo="protocolo_inexistente")
        if TRANSICOES.get(linha["status"]) != destino:
            return resultado("negado", motivo="transicao_invalida")
        with conn:
            conn.execute("UPDATE chamados SET status = ?, atualizado_em = ? WHERE id = ?",
                         (destino, config.agora().isoformat(), linha["id"]))
        linha = conn.execute("SELECT * FROM chamados WHERE id = ?", (linha["id"],)).fetchone()
        return resultado("ok", {"protocolo": protocolo, "status": linha["status"]},
                         [Fonte(tipo="banco", referencia=f"chamados/{protocolo}")])
    except Exception:  # noqa: BLE001
        return resultado("falha", motivo="erro_interno")
    finally:
        conn.close()


def marcar_encaminhamento_pendente(protocolo: str) -> Resultado:
    return _transitar(protocolo, "encaminhamento_pendente")


def iniciar_atendimento(protocolo: str) -> Resultado:
    return _transitar(protocolo, "atendimento_iniciado")
