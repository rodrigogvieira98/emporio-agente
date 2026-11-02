"""Estado da conversa, ações e resposta. O estado persistido fica na tabela conversas."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from .. import config
from ..dados import banco
from ..ferramentas.envelope import Fato, Resultado

ORIGENS = ("real", "eval", "demo")


class Passo(BaseModel):
    """Resultado de uma ferramenta dentro do turno (não persistido)."""

    ferramenta: str
    args: dict[str, Any] = {}
    resultado: Resultado


class Acao(BaseModel):
    tipo: Literal["ferramenta", "encaminhar", "responder", "perguntar"]
    ferramenta: str | None = None
    args: dict[str, Any] = {}
    resposta: str | None = None  # chave do texto em respostas.py
    parametros: dict[str, Any] = {}


class Estado(BaseModel):
    objetivo: str | None = None
    coletados: dict[str, Any] = {}  # confirmados por ferramenta
    declarados: dict[str, dict[str, Any]] = {}  # ditos pelo cliente: {"valor": ..., "origem": "declarado"}
    pendentes: list[dict[str, Any]] = []  # assuntos guardados por troca de assunto
    falhas_seguidas: int = 0
    incompreensoes: int = 0
    acoes_concluidas: list[str] = []
    aguardando: str | None = None
    turno: int = 0
    # Última pergunta de dado feita ao cliente: {"chave", "campos", "vezes"}. Vazio se o último turno não perguntou.
    ultima_pergunta: dict[str, Any] = {}
    # Sentimento (só o rótulo por turno, nunca o texto), assinatura da última mensagem, oferta de humano e frases
    # de reconhecimento já usadas na conversa.
    sentimentos: list[str] = []
    assinatura_ultima_mensagem: str = ""
    oferta_humano: str = ""  # "", "feita" ou "recusada"
    turno_oferta: int = 0
    reconhecimentos_usados: list[str] = []
    # Chamados por assunto: pedir atendente de novo sobre o MESMO assunto informa o protocolo; outro assunto abre outro.
    ultimo_assunto: str = ""
    chamados_assunto: dict[str, str] = {}

    # Transitórios do turno: nunca persistidos (inclui o final de telefone digitado).
    intencao: str | None = Field(default=None, exclude=True)
    slots: dict[str, Any] = Field(default_factory=dict, exclude=True)
    passos: list[Passo] = Field(default_factory=list, exclude=True)
    permissao_registro: bool = Field(default=False, exclude=True)
    concisao: bool = Field(default=False, exclude=True)
    avisos_turno: list[dict[str, Any]] = Field(default_factory=list, exclude=True)

    # Concisão: o que já foi entregue na conversa. chave -> {"valor": ..., "intencao": ...}
    ja_informados: dict[str, dict[str, str]] = {}
    ja_saudou: bool = False
    # Condições de valor já citadas ao cliente (uma por vez): "frete_gratis", "parcelas".
    valores_citados: list[str] = []
    # Assuntos para os quais a Lia já ofereceu retomar: no máximo um convite por assunto na conversa.
    convites_retomar: list[str] = []
    turno_fechamento: int = 0  # último turno em que a Lia fechou perguntando se precisa de mais alguma coisa

    @property
    def sentimento(self) -> str:
        return self.sentimentos[-1] if self.sentimentos else "neutro"

    def declarar(self, campo: str, valor: Any) -> None:
        self.declarados[campo] = {"valor": valor, "origem": "declarado"}

    def declarado(self, campo: str) -> Any:
        item = self.declarados.get(campo)
        return item["valor"] if item else None

    def ultimo(self, ferramenta: str) -> Resultado | None:
        for p in reversed(self.passos):
            if p.ferramenta == ferramenta:
                return p.resultado
        return None

    def resumo_curto(self) -> dict[str, Any]:
        return {"objetivo": self.objetivo, "aguardando": self.aguardando, "falhas_seguidas": self.falhas_seguidas,
                "pendentes": len(self.pendentes)}


class Resposta(BaseModel):
    texto: str
    acoes: list[dict[str, Any]] = []
    fatos: list[Fato] = []
    estado: str = "em_andamento"
    contagens: dict[str, int] = {}
    # Links e botão de carrinho da resposta: gerados só por código (links.py), nunca pelo modelo. No máximo 2.
    links: list[dict[str, Any]] = []

    def texto_terminal(self) -> str:
        """O texto com os endereços como texto simples, para quem não tem página (terminal)."""
        extra = [f"{x['rotulo']}: {x['href']}" for x in self.links if x.get("tipo") == "link"]
        carrinho = [x for x in self.links if x.get("tipo") == "carrinho"]
        extra += [f"{x['rotulo']}: use o site, em /produto/{x['produto_id']}" for x in carrinho]
        return self.texto + (chr(10) + chr(10).join(extra) if extra else "")


def carregar_estado(conversa_id: str) -> Estado:
    conn = banco.conectar()
    try:
        linha = conn.execute("SELECT estado_json FROM conversas WHERE id = ?", (conversa_id,)).fetchone()
    finally:
        conn.close()
    return Estado.model_validate_json(linha["estado_json"]) if linha else Estado()


def salvar_estado(conversa_id: str, estado: Estado) -> None:
    agora = config.agora().isoformat()
    conn = banco.conectar()
    try:
        with conn:
            conn.execute(
                "INSERT INTO conversas (id, estado_json, criado_em, atualizado_em) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET estado_json = excluded.estado_json, atualizado_em = excluded.atualizado_em",
                (conversa_id, estado.model_dump_json(), agora, agora))
    finally:
        conn.close()


def para_json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)
