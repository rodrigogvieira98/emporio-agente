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

# Compra de demonstração (incremento 1). Tabelas à parte: os dados originais e `pedidos` não mudam.
# IF NOT EXISTS porque `garantir_tabelas_demo` também as cria em bancos gerados antes do incremento.
ESQUEMA_DEMO = """
CREATE TABLE IF NOT EXISTS carrinhos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao TEXT NOT NULL,
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    quantidade INTEGER NOT NULL CHECK (quantidade BETWEEN 1 AND 3),
    criado_em TEXT NOT NULL,
    UNIQUE (sessao, produto_id)
);
CREATE TABLE IF NOT EXISTS pedidos_demo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL UNIQUE,
    sessao TEXT NOT NULL,
    forma TEXT NOT NULL,
    parcelas INTEGER NOT NULL,
    cidade TEXT NOT NULL,
    frete_situacao TEXT NOT NULL,
    frete_centavos INTEGER,
    total_centavos INTEGER NOT NULL CHECK (total_centavos > 0),
    parcela_centavos INTEGER,
    aviso TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS itens_pedido_demo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL REFERENCES pedidos_demo(id),
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    nome TEXT NOT NULL,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    original_unit_centavos INTEGER NOT NULL,
    final_unit_centavos INTEGER NOT NULL,
    percentual INTEGER,
    pix_aplicado INTEGER NOT NULL,
    subtotal_centavos INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_carrinhos_sessao ON carrinhos(sessao);
CREATE INDEX IF NOT EXISTS ix_pedidos_demo_sessao ON pedidos_demo(sessao);
"""


def conectar(caminho: Path | str | None = None) -> sqlite3.Connection:
    destino = Path(caminho) if caminho else config.caminho_banco()
    conn = sqlite3.connect(destino)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_esquema(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA)
    conn.executescript(ESQUEMA_DEMO)


def garantir_tabelas_demo(conn: sqlite3.Connection) -> None:
    """Cria as tabelas da compra de demonstração em bancos antigos; não toca nas demais."""
    conn.executescript(ESQUEMA_DEMO)


# Fale Conosco (etapa 6c). Criada sob demanda, como as tabelas da compra.
ESQUEMA_CONTATO = """
CREATE TABLE IF NOT EXISTS mensagens_contato (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    contato TEXT NOT NULL,
    assunto TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    enviada_por_email INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL
);
"""


def garantir_tabela_contato(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA_CONTATO)
