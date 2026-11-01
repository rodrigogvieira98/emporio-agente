"""Laço do agente: percebe, atualiza estado, decide, valida, executa e interpreta, até 3 passos."""
from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import ValidationError

from .. import config
from ..dados import banco
from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.encaminhamento import registrar_encaminhamento
from ..ferramentas.envelope import Fato, Resultado
from ..ferramentas.pedidos import consultar_pedido
from ..ferramentas.politica import consultar_politica
from ..ferramentas.promocoes import listar_promocoes
from ..ferramentas.produtos import buscar_produtos, ver_produto
from . import respostas, trace
from .decisor import Decisor
from .estado import ORIGENS, Acao, Estado, Passo, Resposta, carregar_estado, para_json, salvar_estado
from .fatos import fatos_do_resultado
from .percepcao import perceber
from .regras import REGRA_POR_INTENCAO, RegrasDecisor

log = logging.getLogger("emporio.agente")

MAX_PASSOS = 3
FERRAMENTAS = {f.__name__: f for f in (buscar_produtos, ver_produto, calcular_condicoes, consultar_pedido,
                                       consultar_politica, registrar_encaminhamento, listar_promocoes)}
# só o caminho "encaminhar" (com permissão) pode gravar chamado
SO_ENCAMINHAR = {"registrar_encaminhamento"}
NECESSITA_CONVERSA = {"consultar_pedido", "registrar_encaminhamento"}
LIMPAR_AO_CONCLUIR = ("proposta", "regra", "relato", "registro_explicito", "opcoes", "referencia", "cidade",
                      "valor_pedido", "forma", "parcelas")


class Agente:
    def __init__(self, decisor: Decisor | None = None) -> None:
        self.decisor: Decisor = decisor or RegrasDecisor()

    def responder(self, conversa_id: str, mensagem: str, origem: str) -> Resposta:
        if origem not in ORIGENS:
            raise ValueError(f"origem precisa ser uma de {ORIGENS}, recebi {origem!r}")
        inicio = time.perf_counter()
        estado = carregar_estado(conversa_id)
        antes = estado.resumo_curto()
        perceber(estado, mensagem)
        completar_datas(estado)

        acoes: list[dict[str, Any]] = []
        passos_trace: list[dict[str, Any]] = []
        fatos: list[Fato] = []
        texto: str | None = None
        chave_final: str | None = None
        motivo_saida = "ok"
        concluiu = False

        for numero in range(1, MAX_PASSOS + 1):
            try:
                acao = self.decisor.decidir(estado, mensagem)
            except Exception:  # noqa: BLE001 - decisor com defeito não derruba o atendimento
                log.exception("decisor falhou")
                motivo_saida = "decisor_falhou"
                break
            if acao.tipo in ("ferramenta", "encaminhar"):
                bloqueio = validar(acao, estado)
                if bloqueio:
                    passos_trace.append({"passo": numero, "tipo": acao.tipo, "ferramenta": acao.ferramenta,
                                         "bloqueado": bloqueio})
                    if bloqueio == "sem_permissao":
                        acao = pedir_permissao(estado, acao)
                    else:
                        motivo_saida = bloqueio
                        break
                else:
                    passo = executar(acao, estado, conversa_id, numero)
                    estado.passos.append(passo)
                    integrar(estado, passo)
                    fatos += fatos_do_resultado(passo.ferramenta, passo.args, passo.resultado)
                    r = passo.resultado
                    acoes.append({"tipo": acao.tipo, "ferramenta": passo.ferramenta, "estado": r.estado,
                                  "id_consulta": r.id_consulta, "motivo": r.motivo,
                                  "args": trace.sanitizar_args(passo.args)})
                    passos_trace.append({"passo": numero, "tipo": acao.tipo, "ferramenta": passo.ferramenta,
                                         "estado": r.estado, "motivo": r.motivo, "id_consulta": r.id_consulta,
                                         "args": trace.sanitizar_args(passo.args)})
                    continue
            # responder ou perguntar: fecha o turno
            chave_final = acao.resposta
            texto = respostas.renderizar(chave_final, estado, acao.parametros)
            texto, concluiu = fechar_turno(estado, acao, texto)
            acoes.append({"tipo": acao.tipo, "resposta": chave_final})
            passos_trace.append({"passo": numero, "tipo": acao.tipo, "resposta": chave_final})
            break
        else:
            motivo_saida = "limite_de_passos"

        if texto is None:  # saída sem resposta: nunca deixa o cliente no vazio nem inventa
            estado.falhas_seguidas += 1
            chave_final = "falha_ferramenta"
            texto = respostas.renderizar(chave_final, estado, {})
            motivo_saida = motivo_saida if motivo_saida != "ok" else "sem_resposta"

        salvar_estado(conversa_id, estado)
        gravar_mensagem(conversa_id, estado.turno, texto, origem)
        latencia = int((time.perf_counter() - inicio) * 1000)
        estado_resposta = classificar_estado(estado, acoes, concluiu, motivo_saida)
        try:
            trace.registrar_turno({
                "ts": config.agora().isoformat(), "conversa": conversa_id, "turno": estado.turno, "origem": origem,
                "intencao": estado.intencao, "resposta": chave_final, "motivo_saida": motivo_saida,
                "estado_antes": antes, "estado_depois": estado.resumo_curto(), "passos": passos_trace,
                "acoes": acoes, "estado_resposta": estado_resposta, "latencia_ms": latencia})
        except OSError:
            log.exception("nao foi possivel gravar o trace")
        return Resposta(texto=texto, acoes=acoes, fatos=fatos, estado=estado_resposta)


# --- validação e execução ------------------------------------------------------------------

def validar(acao: Acao, estado: Estado) -> str | None:
    """Esquema, dados e permissão. Devolve o motivo do bloqueio, ou None."""
    nome = acao.ferramenta
    if nome not in FERRAMENTAS:
        return "ferramenta_desconhecida"
    if (acao.tipo == "encaminhar") != (nome in SO_ENCAMINHAR):
        return "caminho_errado"
    args = completar_args(acao, "conversa-validacao")
    try:
        FERRAMENTAS[nome].modelo_entrada.model_validate(args)
    except ValidationError:
        return "entrada_invalida"
    if acao.tipo == "encaminhar" and not estado.permissao_registro:
        return "sem_permissao"
    return None


def completar_args(acao: Acao, conversa_id: str) -> dict[str, Any]:
    args = dict(acao.args)
    if acao.ferramenta in NECESSITA_CONVERSA:
        args["conversa_id"] = conversa_id
    if acao.ferramenta == "registrar_encaminhamento" and "chave_idempotencia" in args:
        args["chave_idempotencia"] = f"{conversa_id}:{args['chave_idempotencia']}"
    return args


def pedir_permissao(estado: Estado, acao: Acao) -> Acao:
    """Registro sem confirmação do cliente vira pergunta."""
    estado.coletados["proposta"] = {"tipo": acao.args.get("tipo"), "resumo": acao.args.get("resumo")}
    return Acao(tipo="perguntar", resposta="confirmar_registro",
                parametros={"aguardando": "confirmacao_registro"})


def executar(acao: Acao, estado: Estado, conversa_id: str, numero: int) -> Passo:
    nome = acao.ferramenta
    args = completar_args(acao, conversa_id)
    inicio = time.perf_counter()
    resultado: Resultado = FERRAMENTAS[nome](**args)
    ms = int((time.perf_counter() - inicio) * 1000)
    try:
        conn = banco.conectar()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO execucoes (conversa_id, turno, passo, ferramenta, entrada_json, estado, id_consulta, "
                    "latencia_ms, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
                    (conversa_id, estado.turno, numero, nome, para_json(trace.sanitizar_args(args)),
                     resultado.estado, resultado.id_consulta, ms, config.agora().isoformat()))
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - observabilidade não pode derrubar o atendimento
        log.exception("nao foi possivel gravar a execucao")
    return Passo(ferramenta=nome, args={k: v for k, v in acao.args.items()}, resultado=resultado)


def gravar_mensagem(conversa_id: str, turno: int, texto: str, origem: str) -> None:
    try:
        conn = banco.conectar()
        try:
            with conn:
                conn.execute("INSERT INTO mensagens_exibidas (conversa_id, turno, texto, origem, criado_em) "
                             "VALUES (?,?,?,?,?)", (conversa_id, turno, texto, origem, config.agora().isoformat()))
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        log.exception("nao foi possivel gravar a mensagem exibida")


# --- interpretação do resultado ------------------------------------------------------------

def integrar(estado: Estado, passo: Passo) -> None:
    r, nome = passo.resultado, passo.ferramenta
    if r.estado in ("falha", "negado") and nome in ("consultar_pedido", "buscar_produtos", "ver_produto",
                                                    "calcular_condicoes", "consultar_politica",
                                                    "registrar_encaminhamento", "listar_promocoes"):
        estado.falhas_seguidas += 1
    elif r.estado == "ok":
        estado.falhas_seguidas = 0
    if nome == "consultar_pedido":
        if r.estado == "ok":
            estado.coletados["pedido"] = r.dados
        elif r.estado == "negado":
            estado.declarados.pop("pedido_id", None)  # pede de novo os dois dados
    elif nome == "ver_produto":
        if r.estado == "ambiguo":
            estado.coletados["opcoes"] = r.dados["opcoes"]
        else:
            estado.coletados.pop("opcoes", None)
    elif nome == "consultar_politica" and r.estado == "ok":
        chave = f"regra.{REGRA_POR_INTENCAO.get(estado.objetivo or '', '')}"
        for s in r.dados["secoes"]:
            for c in s["condicoes"]:
                if c["chave"] == chave:
                    estado.coletados["regra"] = {"objetivo": estado.objetivo, "chave": chave, "valor": c["valor"],
                                                 "ambiguidades": [a["descricao"] for a in s["ambiguidades"]]}
        completar_datas(estado)
    elif nome == "registrar_encaminhamento" and r.estado == "ok":
        estado.coletados["protocolo"] = r.dados["protocolo"]
        if not r.dados.get("repetido"):
            estado.acoes_concluidas.append(f"chamado:{r.dados['protocolo']}")


def completar_datas(estado: Estado) -> None:
    """Data sem rótulo ('foi dia 15/12') vai para a primeira data que a regra ainda pede."""
    regra = estado.coletados.get("regra")
    soltas = estado.slots.get("datas_soltas")
    if not regra or not soltas:
        return
    for campo in regra["valor"]["dados_necessarios"]:
        if campo.startswith("data_") and estado.declarado(campo) is None and soltas:
            estado.declarar(campo, soltas.pop(0))


# --- fechamento do turno --------------------------------------------------------------------

def fechar_turno(estado: Estado, acao: Acao, texto: str) -> tuple[str, bool]:
    p = acao.parametros
    chave = acao.resposta
    estado.incompreensoes = estado.incompreensoes + 1 if chave == "nao_entendi" else 0
    if acao.tipo == "perguntar":
        estado.aguardando = p["aguardando"]
        return texto, False
    if p.get("propor_registro"):
        estado.coletados["proposta"] = p["propor_registro"]
        estado.aguardando = "confirmacao_registro"
        return texto, False
    # resposta que conclui o assunto
    estado.objetivo = None
    estado.aguardando = None
    for k in LIMPAR_AO_CONCLUIR:
        estado.coletados.pop(k, None)
    estado.declarados = {k: v for k, v in estado.declarados.items() if k == "pedido_id"}
    if estado.pendentes:
        assunto = estado.pendentes[-1]["objetivo"]
        estado.aguardando = "retomar"
        texto = f"{texto}\n\n{respostas.retomar(estado, {'assunto': assunto})}"
    return texto, True


def classificar_estado(estado: Estado, acoes: list[dict[str, Any]], concluiu: bool, motivo: str) -> str:
    if motivo not in ("ok",):
        return "falha"
    if any(a.get("ferramenta") == "registrar_encaminhamento" and a.get("estado") == "ok" for a in acoes):
        return "encaminhado"
    if estado.aguardando:
        return f"aguardando:{estado.aguardando}"
    return "concluido" if concluiu else "em_andamento"
