"""Esquema SQLite e conexão. Dinheiro sempre em centavos INTEGER."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import config

ESQUEMA = """
CREATE TABLE categorias (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    descricao TEXT
);
CREATE TABLE produtos (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos > 0),
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    descricao TEXT,
    estoque INTEGER NOT NULL CHECK (estoque >= 0),
    status TEXT NOT NULL,
    specs_json TEXT NOT NULL,
    criado_em TEXT
);
CREATE TABLE promocoes (
    id INTEGER PRIMARY KEY,
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    percentual INTEGER NOT NULL CHECK (percentual BETWEEN 1 AND 100),
    descricao TEXT,
    ativa INTEGER NOT NULL CHECK (ativa IN (0, 1))
);
CREATE TABLE clientes (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    telefone TEXT NOT NULL,
    email TEXT,
    cidade TEXT
);
CREATE TABLE pedidos (
    id INTEGER PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    data_pedido TEXT NOT NULL,
    status TEXT NOT NULL,
    total_centavos INTEGER NOT NULL CHECK (total_centavos > 0),
    forma_pagamento TEXT NOT NULL,
    rastreio TEXT,
    previsao_entrega TEXT,
    nota TEXT
);
CREATE TABLE itens_pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0)
);
CREATE TABLE tentativas_pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id TEXT NOT NULL,
    pedido_id INTEGER,
    sucesso INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE chamados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo TEXT NOT NULL UNIQUE,
    conversa_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    resumo TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('registrado', 'encaminhamento_pendente', 'atendimento_iniciado')),
    chave_idempotencia TEXT NOT NULL UNIQUE,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE conversas (
    id TEXT PRIMARY KEY,
    estado_json TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE mensagens_exibidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id TEXT NOT NULL,
    turno INTEGER NOT NULL,
    texto TEXT NOT NULL,
    origem TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id TEXT NOT NULL,
    turno INTEGER NOT NULL,
    passo INTEGER NOT NULL,
    ferramenta TEXT NOT NULL,
    entrada_json TEXT NOT NULL,
    estado TEXT NOT NULL,
    id_consulta TEXT NOT NULL,
    latencia_ms INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE INDEX ix_tentativas_conversa ON tentativas_pedido(conversa_id);
CREATE INDEX ix_promocoes_produto ON promocoes(produto_id);
"""


def conectar(caminho: Path | str | None = None) -> sqlite3.Connection:
    destino = Path(caminho) if caminho else config.caminho_banco()
    conn = sqlite3.connect(destino)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_esquema(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA)
