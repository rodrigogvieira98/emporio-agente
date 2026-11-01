"""LlmDecisor: o modelo propõe a próxima Acao por saída estruturada; o laço valida e executa.

Proposta inválida, timeout ou erro de conexão caem no RegrasDecisor, com contagem visível.
O prompt vive em arquivo versionado (prompt_decisor.md) e seu hash vai para o trace.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..ferramentas.encaminhamento import TIPOS, mascarar_dado_pessoal
from . import llm, respostas
from .estado import Acao, Estado
from .regras import RegrasDecisor

CAMINHO_PROMPT = Path(__file__).with_name("prompt_decisor.md")
NOMES_FERRAMENTAS = ["buscar_produtos", "ver_produto", "calcular_condicoes", "consultar_pedido",
                     "consultar_politica", "listar_promocoes", "registrar_encaminhamento"]
TEMAS = ["horario", "endereco", "contato", "pagamento", "frete", "garantia", "escopo", "empresa",
         "arrependimento", "defeito", "troca_preferencia", "trocas"]
CHAVES = sorted(respostas.TEXTOS)
FORMAS = ["pix", "debito", "credito", "boleto"]

# resposta -> o que o cliente deve informar em seguida
AGUARDA = {"pedir_pedido": "pedido", "pedido_negado": "pedido", "pedir_dados_posvenda": "dados_posvenda",
           "pedir_categoria": "categoria", "pedir_produto": "referencia_produto",
           "produto_nao_encontrado": "referencia_produto", "escolha_produto": "escolha_produto",
           "pedir_valor_pedido": "valor_pedido", "frete_info": "cidade", "pedir_relato": "relato"}
# respostas que sempre terminam oferecendo registro, e o tipo padrão do chamado
PROPOR_SEMPRE = {"reclamacao_empatia": "reclamacao", "propor_posvenda": "atendente", "sem_dado": "sem_dado",
                 "pedido_negado_limite": "atendente", "nao_entendi_de_novo": "sem_dado",
                 "preco_promocao_conflitante": "duvida_politica"}
PROPOR_OPCIONAL = {"preco", "frete_calculado", "status_pedido", "falha_ferramenta"}

_PROPRIEDADES: dict[str, Any] = {
        "ferramenta": {"type": ["string", "null"], "enum": [*NOMES_FERRAMENTAS, None]},
        "resposta": {"type": ["string", "null"], "enum": [*CHAVES, None]},
        "temas": {"type": ["array", "null"], "items": {"type": "string", "enum": TEMAS}},
        "categoria": {"type": ["string", "null"]},
        "termo": {"type": ["string", "null"]},
        "referencia": {"type": ["string", "null"]},
        "produto_id": {"type": ["integer", "null"]},
        "preco_min": {"type": ["integer", "null"]},
        "preco_max": {"type": ["integer", "null"]},
        "limite": {"type": ["integer", "null"]},
        "forma": {"type": ["string", "null"], "enum": [*FORMAS, None]},
        "parcelas": {"type": ["integer", "null"]},
        "cidade": {"type": ["string", "null"]},
        "valor": {"type": ["integer", "null"]},
        "valor_pedido": {"type": ["integer", "null"]},
        "termo_promocao": {"type": ["string", "null"]},
        "tipo_registro": {"type": ["string", "null"], "enum": [*TIPOS, None]},
        "resumo": {"type": ["string", "null"]},
        "propor_registro": {"type": ["boolean", "null"]},
}
SCHEMA: dict[str, Any] = {"type": "object", "properties": _PROPRIEDADES, "required": list(_PROPRIEDADES)}


class PropostaInvalida(Exception):
    pass


def prompt() -> tuple[str, str]:
    texto = CAMINHO_PROMPT.read_text(encoding="utf-8").replace("\r\n", "\n")
    return texto, hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _ok(e: Estado, nome: str, *aceitos: str) -> bool:
    return any(p.ferramenta == nome and p.resultado.estado in (aceitos or ("ok",)) for p in e.passos)


REQUISITOS = {
    "saudacao": lambda e: _ok(e, "consultar_politica"), "horario": lambda e: _ok(e, "consultar_politica"),
    "endereco": lambda e: _ok(e, "consultar_politica"), "contato": lambda e: _ok(e, "consultar_politica"),
    "pagamento": lambda e: _ok(e, "consultar_politica"), "garantia_info": lambda e: _ok(e, "consultar_politica"),
    "trocas_info": lambda e: _ok(e, "consultar_politica"),
    "fora_escopo": lambda e: _ok(e, "consultar_politica"), "fora_escopo_geral": lambda e: _ok(e, "consultar_politica"),
    "frete_info": lambda e: _ok(e, "consultar_politica"),
    "busca": lambda e: _ok(e, "buscar_produtos", "ok", "vazio"),
    "preco": lambda e: _ok(e, "calcular_condicoes"),
    "disponibilidade": lambda e: _ok(e, "ver_produto"),
    "produto_indisponivel": lambda e: _ok(e, "ver_produto") and _ok(e, "buscar_produtos", "ok", "vazio"),
    "promocoes": lambda e: _ok(e, "listar_promocoes", "ok", "vazio"),
    "frete_calculado": lambda e: _ok(e, "calcular_condicoes"),
    "status_pedido": lambda e: bool(e.coletados.get("pedido")),
    "pedido_negado": lambda e: _ok(e, "consultar_pedido", "negado"),
    "pedir_dados_posvenda": lambda e: bool(e.coletados.get("pedido") and e.coletados.get("regra")),
    "propor_posvenda": lambda e: bool(e.coletados.get("pedido") and e.coletados.get("regra")
                                      and not _faltam_dados(e)),
    "escolha_produto": lambda e: _ok(e, "ver_produto", "ambiguo"),
    "produto_nao_encontrado": lambda e: _ok(e, "ver_produto", "vazio"),
    "chamado_registrado": lambda e: _ok(e, "registrar_encaminhamento"),
    # respostas ligadas a um fato que a percepção já estabeleceu
    "preco_promocao_conflitante": lambda e: _ok(e, "calcular_condicoes", "ambiguo"),
    "nao_entendi": lambda e: e.intencao == "desconhecido",
    "nao_entendi_de_novo": lambda e: e.intencao == "desconhecido" and e.incompreensoes >= 1,
    "pedido_negado_limite": lambda e: _ok(e, "consultar_pedido", "negado") and e.falhas_seguidas >= 3,
    "ok_sem_retomar": lambda e: e.intencao == "retomada_recusada",
    "registro_cancelado": lambda e: bool(e.slots.get("cancelou")),
    "negacao_reclamacao": lambda e: bool(e.slots.get("nega_reclamacao")),
    "negacao_atendente": lambda e: bool(e.slots.get("nega_atendente")),
    "recusa_dado_de_terceiro": lambda e: e.intencao == "dado_de_terceiro",
    "recusa_manipulacao": lambda e: e.intencao == "tentativa_manipulacao" and _ok(e, "consultar_politica"),
    "reclamacao_empatia": lambda e: e.intencao == "reclamacao",
    "pedir_relato": lambda e: e.intencao == "reclamacao",
    "falha_ferramenta": lambda e: any(p.resultado.estado == "falha" for p in e.passos) or e.falhas_seguidas > 0,
}


def _faltam_dados(estado: Estado) -> list[str]:
    regra = estado.coletados.get("regra")
    if not regra:
        return []
    return [c for c in regra["valor"]["dados_necessarios"] if estado.declarado(c) is None]


DICAS = {
    "preco": "Rode antes ver_produto e calcular_condicoes.", "busca": "Rode antes buscar_produtos.",
    "disponibilidade": "Rode antes ver_produto.",
    "produto_indisponivel": "Rode antes ver_produto e buscar_produtos (categoria do produto, limite 3).",
    "promocoes": "Rode antes listar_promocoes.", "frete_calculado": "Rode antes calcular_condicoes com cidade e valor.",
    "status_pedido": "Rode antes consultar_pedido.", "pedido_negado": "Só se consultar_pedido deu negado.",
    "pedir_dados_posvenda": "Rode antes consultar_pedido e consultar_politica.",
    "propor_posvenda": "Só quando faltam_dados estiver vazio, depois de consultar_pedido e consultar_politica.",
    "escolha_produto": "Só se ver_produto deu ambiguo.", "produto_nao_encontrado": "Só se ver_produto deu vazio.",
    "chamado_registrado": "Rode antes registrar_encaminhamento.",
    "saudacao": "Rode antes consultar_politica.", "horario": "Rode antes consultar_politica horario.",
    "endereco": "Rode antes consultar_politica endereco.", "contato": "Rode antes consultar_politica contato.",
    "pagamento": "Rode antes consultar_politica pagamento.", "garantia_info": "Rode antes consultar_politica garantia.",
    "trocas_info": "Rode antes consultar_politica trocas e garantia (pergunta geral, sem pedido).",
    "fora_escopo": "Rode antes consultar_politica escopo.", "fora_escopo_geral": "Rode antes consultar_politica escopo.",
    "frete_info": "Rode antes consultar_politica frete.", "recusa_manipulacao": "Rode antes consultar_politica pagamento.",
}


def resumir(estado: Estado, mensagem: str) -> dict[str, Any]:
    """Estado resumido para o prompt: sem catálogo, sem manual e sem dado pessoal."""
    s = estado.slots
    ocultos = {"final_telefone", "texto_limpo", "datas", "datas_soltas", "palavras", "nova"}
    slots = {k: v for k, v in s.items() if k not in ocultos and v not in (False, None, "", [])}
    if s.get("final_telefone"):
        slots["final_informado"] = True
    texto = mascarar_dado_pessoal(mensagem)
    if s.get("final_telefone"):
        texto = texto.replace(s["final_telefone"], "[final]")
    passos = []
    for i, p in enumerate(estado.passos, start=1):
        r = p.resultado
        resumo: dict[str, Any] = {"passo": i, "ferramenta": p.ferramenta, "estado": r.estado}
        if r.motivo:
            resumo["motivo"] = r.motivo
        d = r.dados
        if p.ferramenta == "buscar_produtos":
            resumo["total"] = d.get("total_encontrado")
        elif p.ferramenta == "ver_produto" and r.estado == "ok":
            resumo.update(situacao_venda=d["situacao_venda"], categoria=d["categoria"], produto_id=d["id"])
        elif p.ferramenta == "ver_produto" and r.estado == "ambiguo":
            resumo["opcoes"] = len(d["opcoes"])
        elif p.ferramenta == "calcular_condicoes" and r.estado == "ok":
            resumo.update(permitido=d["permitido"], frete=d.get("frete", {}).get("situacao"))
        elif p.ferramenta == "listar_promocoes":
            resumo["total"] = d.get("total", 0)
        elif p.ferramenta == "registrar_encaminhamento" and r.estado == "ok":
            resumo["protocolo_gerado"] = True
        passos.append(resumo)
    return {
        "mensagem": texto,
        "percepcao": {"intencao": estado.intencao, "objetivo": estado.objetivo, "aguardando": estado.aguardando,
                      "slots": slots},
        "estado": {"pedido_validado": bool(estado.coletados.get("pedido")),
                   "regra_coletada": bool(estado.coletados.get("regra")),
                   "faltam_dados": _faltam_dados(estado),
                   "relato_presente": bool(estado.coletados.get("relato")),
                   "registro_explicito": bool(estado.coletados.get("registro_explicito")),
                   "proposta_pendente": estado.coletados.get("proposta"),
                   "permissao_registro": estado.permissao_registro,
                   "falhas_seguidas": estado.falhas_seguidas, "incompreensoes": estado.incompreensoes},
        "ja_executadas": [p.ferramenta for p in estado.passos],
        "neste_turno": passos,
    }


class LlmDecisor:
    def __init__(self, modelo: str, cliente: Any = None, regras: RegrasDecisor | None = None) -> None:
        self.modelo = modelo
        self.cliente = cliente or llm
        self.regras = regras or RegrasDecisor()
        self.contagens: Counter[str] = Counter()
        self.telemetria: list[dict[str, Any]] = []

    # --- API do Protocol ---------------------------------------------------------------

    def decidir(self, estado: Estado, mensagem: str) -> Acao:
        sistema, hash_prompt = prompt()
        entrada = json.dumps(resumir(estado, mensagem), ensure_ascii=False)
        conversa = llm.mensagens_do_modelo(self.modelo, sistema, entrada)
        ultimo_motivo = ""
        for tentativa in (1, 2):  # cada nova tentativa recebe o motivo da recusa anterior
            reg: dict[str, Any] = {"componente": "decisor", "modelo": self.modelo, "prompt_hash": hash_prompt,
                                   "tentativa": tentativa}
            try:
                r = self.cliente.conversar(self.modelo, conversa, formato=SCHEMA)
            except llm.TimeoutModelo as erro:
                return self._cair("timeout", reg, estado, mensagem, str(erro))
            except llm.ErroModelo as erro:
                return self._cair("erro_modelo", reg, estado, mensagem, str(erro))
            reg.update(proposta_bruta=r.conteudo, tokens_prompt=r.tokens_prompt, tokens_resposta=r.tokens_resposta,
                       latencia_ms=r.latencia_ms, num_ctx=getattr(r, "num_ctx", None))
            try:
                acao = self._montar(estado, mensagem, json.loads(r.conteudo))
            except (PropostaInvalida, ValueError, ValidationError, KeyError, TypeError) as erro:
                self.contagens["proposta_invalida"] += 1
                ultimo_motivo = str(erro)[:160]
                reg.update(resultado="recusada", detalhe=ultimo_motivo)
                self.telemetria.append(reg)
                conversa = conversa + [
                    {"role": "assistant", "content": r.conteudo},
                    {"role": "user", "content": json.dumps(
                        {"erro": ultimo_motivo, "corrija": "Releia o roteiro e proponha outra ação (ferramenta ou resposta)."},
                        ensure_ascii=False)}]
                continue
            reg["resultado"] = "aceita" if tentativa == 1 else "aceita_apos_correcao"
            if tentativa > 1:
                self.contagens["correcao_aceita"] += 1
            self.telemetria.append(reg)
            return acao
        self.contagens["fallback_regras"] += 1
        return self.regras.decidir(estado, mensagem)

    def _cair(self, motivo: str, reg: dict[str, Any], estado: Estado, mensagem: str, detalhe: str) -> Acao:
        self.contagens[motivo] += 1
        self.contagens["fallback_regras"] += 1
        reg.update(resultado=f"fallback_regras:{motivo}", detalhe=detalhe)
        self.telemetria.append(reg)
        return self.regras.decidir(estado, mensagem)

    # --- da proposta para a Acao -------------------------------------------------------

    def _montar(self, estado: Estado, mensagem: str, p: dict[str, Any]) -> Acao:
        if not isinstance(p, dict):
            raise PropostaInvalida("proposta nao e objeto")
        # ou uma ferramenta, ou uma resposta; o tipo da Acao sai do que foi escolhido
        if p.get("ferramenta") and p.get("resposta"):
            raise PropostaInvalida("proponha ferramenta ou resposta, nao os dois")
        if p.get("ferramenta"):
            tipo = "encaminhar" if p["ferramenta"] == "registrar_encaminhamento" else "ferramenta"
            return self._montar_ferramenta(estado, tipo, p)
        if p.get("resposta"):
            return self._montar_terminal(estado, mensagem, p)
        raise PropostaInvalida("sem ferramenta e sem resposta")

    def _montar_ferramenta(self, estado: Estado, tipo: str, p: dict[str, Any]) -> Acao:
        from .laco import FERRAMENTAS, completar_args  # import tardio: laco importa este módulo

        nome = p.get("ferramenta")
        if nome not in FERRAMENTAS or (tipo == "encaminhar") != (nome == "registrar_encaminhamento"):
            raise PropostaInvalida(f"ferramenta/tipo incoerentes: {tipo}/{nome}")
        args = self._args(nome, p, estado)
        acao = Acao(tipo=tipo, ferramenta=nome, args=args)
        FERRAMENTAS[nome].modelo_entrada.model_validate(completar_args(acao, "validacao"))
        # cada ferramenta roda uma vez por turno (a política pode ser consultada com temas diferentes)
        if any(ps.ferramenta == nome and (nome != "consultar_politica" or ps.args == args) for ps in estado.passos):
            raise PropostaInvalida("ferramenta repetida no turno")
        return acao

    @staticmethod
    def _args(nome: str, p: dict[str, Any], estado: Estado) -> dict[str, Any]:
        pegar = lambda *campos: {c: p[c] for c in campos if p.get(c) is not None}  # noqa: E731
        if nome == "buscar_produtos":
            return pegar("categoria", "termo", "preco_min", "preco_max", "limite")
        if nome == "ver_produto":
            ref = p.get("produto_id") if p.get("produto_id") is not None else p.get("referencia")
            if ref is None:
                raise PropostaInvalida("ver_produto sem referencia")
            return {"referencia": ref}
        if nome == "calcular_condicoes":
            args = pegar("produto_id", "valor", "forma", "parcelas", "cidade", "valor_pedido")
            args.setdefault("forma", "pix")
            return args
        if nome == "consultar_pedido":  # número e final saem do código, nunca do modelo
            pid, final = estado.declarado("pedido_id"), estado.slots.get("final_telefone")
            if pid is None or final is None:
                raise PropostaInvalida("faltam numero do pedido ou final")
            return {"pedido_id": pid, "final_telefone": final}
        if nome == "consultar_politica":
            return {"temas": p.get("temas") or []}
        if nome == "listar_promocoes":
            return {"termo": p["termo_promocao"]} if p.get("termo_promocao") else {}
        if p.get("tipo_registro") not in TIPOS:
            raise PropostaInvalida("registro sem tipo valido")
        n = sum(1 for a in estado.acoes_concluidas if a.startswith("chamado:"))
        resumo = mascarar_dado_pessoal(p.get("resumo") or "").strip() or "Cliente precisa de atendimento da equipe."
        return {"tipo": p["tipo_registro"], "resumo": resumo[:300], "chave_idempotencia": f"{estado.objetivo}:{n}"}

    def _montar_terminal(self, estado: Estado, mensagem: str, p: dict[str, Any]) -> Acao:
        chave = p.get("resposta")
        if chave not in respostas.TEXTOS:
            raise PropostaInvalida(f"resposta desconhecida: {chave!r}")
        exige = REQUISITOS.get(chave)
        if exige is not None and not exige(estado):
            raise PropostaInvalida(f"{chave} ainda nao pode ser a resposta. {DICAS.get(chave, 'Faltam dados do turno.')}")
        ref = self.regras.decidir(estado.model_copy(deep=True), mensagem)
        if ref.tipo in ("responder", "perguntar") and ref.resposta == chave:
            acao = ref  # mesma escolha das regras: os parâmetros vêm prontos
        else:
            acao = self._construir_terminal(estado, chave, p)
        texto = respostas.renderizar(chave, estado.model_copy(deep=True), acao.parametros)
        pergunta_de_registro = "Responda sim ou não" in texto
        if pergunta_de_registro and not acao.parametros.get("propor_registro"):
            tipo = p.get("tipo_registro") if p.get("tipo_registro") in TIPOS else PROPOR_SEMPRE.get(chave, "duvida_politica")
            acao.parametros["propor_registro"] = {"tipo": tipo, "resumo": self._resumo_proposta(estado, p)}
        if acao.parametros.get("propor_registro") and not pergunta_de_registro:
            raise PropostaInvalida("propor_registro em texto que nao pergunta")
        return acao

    def _construir_terminal(self, estado: Estado, chave: str, p: dict[str, Any]) -> Acao:
        params: dict[str, Any] = {}
        if chave in AGUARDA:
            params["aguardando"] = AGUARDA[chave]
        if chave == "pedir_pedido":
            params["tem_pedido"] = estado.declarado("pedido_id") is not None
            params["tem_final"] = bool(estado.slots.get("final_telefone"))
        if chave == "pedir_dados_posvenda":
            regra = estado.coletados["regra"]
            faltam = [c for c in regra["valor"]["dados_necessarios"] if estado.declarado(c) is None]
            if not faltam:
                raise PropostaInvalida("pedir_dados_posvenda sem dado faltando")
            params["campos"] = faltam
        if chave in PROPOR_SEMPRE or (p.get("propor_registro") and chave in PROPOR_OPCIONAL):
            tipo = p.get("tipo_registro") if p.get("tipo_registro") in TIPOS else PROPOR_SEMPRE.get(chave, "duvida_politica")
            params["propor_registro"] = {"tipo": tipo, "resumo": self._resumo_proposta(estado, p)}
        return Acao(tipo="perguntar" if chave in AGUARDA else "responder", resposta=chave, parametros=params)

    def _resumo_proposta(self, estado: Estado, p: dict[str, Any]) -> str:
        resumo = mascarar_dado_pessoal(p.get("resumo") or "").strip()
        return (resumo or f"Cliente precisa de ajuda da equipe sobre {estado.objetivo or 'o atendimento'}.")[:300]

    # --- telemetria ----------------------------------------------------------------------

    def drenar(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        t, c = self.telemetria, dict(self.contagens)
        self.telemetria, self.contagens = [], Counter()
        return t, c
