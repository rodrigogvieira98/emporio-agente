"""Fale Conosco: canais, validação do formulário, gravação e envio opcional por SMTP.

Os valores de contato vêm do manual por `fato()`. Um canal só vira link quando a variável de ambiente
correspondente traz o endereço verificado (EMPORIO_WHATSAPP_URL, EMPORIO_TELEFONE_LINK, EMPORIO_EMAIL_LINK);
sem ela, o valor aparece como texto com ícone. Mensagem só sai por e-mail com EMPORIO_SMTP_HOST configurado.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import sqlite3
from email.message import EmailMessage
from typing import Any

from .. import config
from ..dados import banco
from ..politicas.manual import fato

log = logging.getLogger("emporio.web.contato")

LIMITES = {"assunto": 120, "mensagem": 2000, "contato": 120}
PADRAO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PADRAO_TELEFONE = re.compile(r"^\+?[\d\s().-]{8,20}$")
PREFIXO_PROTOCOLO = "FC-"


def _valor(chave: str) -> str:
    f = fato(chave)
    return str(f.valor) if f else ""


def canais() -> list[dict[str, Any]]:
    """Conversar, Ligar e Escrever: texto do manual e, se verificado, o link vindo do ambiente."""
    definicao = (
        ("conversar", "Conversar", "whatsapp", "contato.whatsapp_secao_7", "EMPORIO_WHATSAPP_URL"),
        ("ligar", "Ligar", "telefone", "contato.telefone_capa", "EMPORIO_TELEFONE_LINK"),
        ("escrever", "Escrever", "email", "contato.email_capa", "EMPORIO_EMAIL_LINK"),
    )
    saida = []
    for chave, rotulo, icone, fato_chave, variavel in definicao:
        valor = _valor(fato_chave)
        if not valor:
            continue
        link = (os.environ.get(variavel) or "").strip() or None
        saida.append({"chave": chave, "rotulo": rotulo, "icone": icone, "valor": valor, "link": link})
    return saida


def validar(campos: dict[str, str]) -> dict[str, str]:
    """Mapa campo -> mensagem de erro; vazio quando válido."""
    erros: dict[str, str] = {}
    assunto, mensagem, contato = (campos.get(k, "").strip() for k in ("assunto", "mensagem", "contato"))
    if not assunto:
        erros["assunto"] = "Diga o assunto em poucas palavras."
    elif len(assunto) > LIMITES["assunto"]:
        erros["assunto"] = f"Use até {LIMITES['assunto']} caracteres no assunto."
    if len(mensagem) < 10:
        erros["mensagem"] = "Escreva a mensagem com pelo menos 10 caracteres."
    elif len(mensagem) > LIMITES["mensagem"]:
        erros["mensagem"] = f"Use até {LIMITES['mensagem']} caracteres na mensagem."
    if not (PADRAO_EMAIL.match(contato) or PADRAO_TELEFONE.match(contato)):
        erros["contato"] = "Informe um e-mail ou telefone válido para o retorno."
    return erros


def _enviar_email(protocolo: str, c: dict[str, str]) -> bool:
    """Envia só com EMPORIO_SMTP_* configurado. Devolve True apenas se o servidor aceitou a mensagem."""
    host = (os.environ.get("EMPORIO_SMTP_HOST") or "").strip()
    destino = (os.environ.get("EMPORIO_SMTP_PARA") or "").strip()
    if not host or not destino:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[{protocolo}] {c['assunto']}"
        msg["From"] = os.environ.get("EMPORIO_SMTP_DE") or destino
        msg["To"] = destino
        msg.set_content(f"Retorno para: {c['contato']}\n\n{c['mensagem']}")
        with smtplib.SMTP(host, int(os.environ.get("EMPORIO_SMTP_PORTA", "587")), timeout=10) as s:
            if os.environ.get("EMPORIO_SMTP_USUARIO"):
                s.starttls()
                s.login(os.environ["EMPORIO_SMTP_USUARIO"], os.environ.get("EMPORIO_SMTP_SENHA", ""))
            s.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException, ValueError):
        log.exception("falha no envio SMTP do contato")
        return False


def gravar(campos: dict[str, str]) -> str:
    """Grava a mensagem já validada e devolve o protocolo FC-NNNN. Nunca diz que enviou por e-mail."""
    c = {k: campos.get(k, "").strip() for k in ("assunto", "mensagem", "contato", "nome")}
    c["nome"] = c["nome"] or "-"
    conn = banco.conectar()
    try:
        banco.garantir_tabela_contato(conn)
        with conn:
            cur = conn.execute(
                "INSERT INTO mensagens_contato (protocolo, nome, contato, assunto, mensagem, criado_em) "
                "VALUES ('pendente', ?, ?, ?, ?, ?)",
                (c["nome"], c["contato"], c["assunto"], c["mensagem"], config.agora().isoformat()))
            protocolo = f"{PREFIXO_PROTOCOLO}{cur.lastrowid:04d}"
            conn.execute("UPDATE mensagens_contato SET protocolo = ? WHERE id = ?", (protocolo, cur.lastrowid))
        if _enviar_email(protocolo, c):
            with conn:
                conn.execute("UPDATE mensagens_contato SET enviada_por_email = 1 WHERE protocolo = ?", (protocolo,))
        return protocolo
    except sqlite3.Error:
        log.exception("falha ao gravar mensagem de contato")
        raise
    finally:
        conn.close()
