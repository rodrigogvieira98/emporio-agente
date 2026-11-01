"""Laço do agente: percebe, atualiza estado, decide, valida, executa e interpreta, até 3 passos."""
from __future__ import annotations

import logging
import re
import time
from collections import Counter
from typing import Any

from pydantic import ValidationError

from .. import config
from ..dados import banco
from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.encaminhamento import registrar_encaminhamento
from ..ferramentas.envelope import Fato, Resultado
from ..ferramentas.frete import estimar_frete
from ..ferramentas.pedido_demo import consultar_pedido_demo
from ..ferramentas.pedidos import consultar_pedido
from ..ferramentas.politica import consultar_politica
from ..ferramentas.promocoes import listar_promocoes
from ..ferramentas.produtos import buscar_produtos, ver_produto
from . import links as links_mod
from . import respostas, trace
from .concisao import deduplicar_frases, registrar_entregas, respostas_anteriores
from .redacao import Redator
from .reserva import EXECUTA, Reserva
from .decisor import Decisor
from .estado import ORIGENS, Acao, Estado, Passo, Resposta, carregar_estado, para_json, salvar_estado
from .fatos import fatos_do_resultado
from .percepcao import aplicar_rotulo, perceber
from .regras import REGRA_POR_INTENCAO, RegrasDecisor

log = logging.getLogger("emporio.agente")

MAX_PASSOS = 3
FERRAMENTAS = {f.__name__: f for f in (buscar_produtos, ver_produto, calcular_condicoes, consultar_pedido,
                                       consultar_politica, registrar_encaminhamento, listar_promocoes,
                                       consultar_pedido_demo, estimar_frete)}
# só o caminho "encaminhar" (com permissão) pode gravar chamado
SO_ENCAMINHAR = {"registrar_encaminhamento"}
NECESSITA_CONVERSA = {"consultar_pedido", "consultar_pedido_demo", "registrar_encaminhamento"}
LIMPAR_AO_CONCLUIR = ("proposta", "regra", "relato", "registro_explicito", "opcoes", "referencia", "cidade",
                      "valor_pedido", "forma", "parcelas", "cep", "uf", "compra", "qualificacao", "qualificada")
# Respostas sobre produto em que a compra, uma vez pedida, vale até o fim do assunto.
INTENCOES_DE_COMPRA = ("preco_produto", "disponibilidade")


class Agente:
    """decisor: quem propõe as ações (padrão: regras). redator: texto livre curto ao redor dos blocos
    (opcional). concisao: liga a supressão de avisos repetidos, saudação única e frases repetidas."""

    def __init__(self, decisor: Decisor | None = None, redator: Redator | None = None,
                 concisao: bool = False, reserva: Reserva | None = None) -> None:
        self.decisor: Decisor = decisor or RegrasDecisor()
        self.redator = redator
        self.concisao = concisao
        # o modelo só escolhe a intenção quando as regras não acham; só vale com o decisor de regras
        self.reserva = reserva if isinstance(self.decisor, RegrasDecisor) else None

    def responder(self, conversa_id: str, mensagem: str, origem: str) -> Resposta:
        if origem not in ORIGENS:
            raise ValueError(f"origem precisa ser uma de {ORIGENS}, recebi {origem!r}")
        inicio = time.perf_counter()
        estado = carregar_estado(conversa_id)
        antes = estado.resumo_curto()
        estado.concisao = self.concisao
        perceber(estado, mensagem)
        mensagem_limpa = limpar_pii(mensagem, estado, mensagem)
        if self.reserva is not None and estado.intencao == "desconhecido":
            rotulo = self.reserva.escolher(mensagem_limpa)
            if rotulo in EXECUTA:  # o código valida: só rótulo da lista fechada vira intenção
                aplicar_rotulo(estado, rotulo)
        if estado.objetivo and estado.objetivo != "pedir_atendente":
            estado.ultimo_assunto = estado.objetivo
        completar_datas(estado)
        if estado.slots.get("cidade"):
            estado.coletados["cidade_cliente"] = estado.slots["cidade"]  # a cidade dita antes vale nos turnos seguintes
        if estado.slots.get("compra") and estado.intencao in INTENCOES_DE_COMPRA:
            estado.coletados["compra"] = True  # vale também depois da escolha numerada entre modelos parecidos
        contagens: Counter[str] = Counter()
        telemetria: list[dict[str, Any]] = []

        acoes: list[dict[str, Any]] = []
        passos_trace: list[dict[str, Any]] = []
        fatos: list[Fato] = []
        texto: str | None = None
        chave_final: str | None = None
        motivo_saida = "ok"
        concluiu = False
        links: list[dict[str, Any]] = []
        etapa_lead: str | None = None

        partes: list[str] = []  # respostas já prontas de perguntas anteriores da mesma mensagem
        dupla = estado.slots.get("secundaria") or estado.slots.get("pix_e_parcelas")
        for numero in range(1, MAX_PASSOS * (2 if dupla else 1) + 1):
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
                    contagens[f"bloqueio_{bloqueio}"] += 1
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
            acao = limitar_repeticao(acao, estado)
            chave_final = acao.resposta
            try:
                texto = respostas.renderizar(chave_final, estado, acao.parametros)
            except Exception:  # noqa: BLE001 - decisor propôs resposta que não renderiza: nunca chega ao cliente
                log.exception("resposta nao renderiza: %s", chave_final)
                contagens["resposta_nao_renderiza"] += 1
                chave_final, acao = "falha_ferramenta", Acao(tipo="responder", resposta="falha_ferramenta")
                texto = respostas.renderizar(chave_final, estado, {})
            segunda = estado.slots.get("secundaria")
            if segunda and acao.tipo == "responder" and not acao.parametros.get("propor_registro"):
                # duas perguntas na mesma mensagem: guarda esta resposta e segue para a outra intenção conhecida
                partes.append(texto)
                estado.slots["secundaria"] = None
                estado.intencao = estado.objetivo = segunda
                estado.aguardando = None
                contagens["pergunta_secundaria"] += 1
                continue
            if partes:
                texto = chr(10).join([*partes, "", texto])
            texto, oferecer = ajustar_tom(estado, acao, chave_final, texto)
            if (self.redator is not None and chave_final not in SEM_REDACAO and not partes
                    and not acao.parametros.get("compra")  # resposta de compra: sem texto livre do modelo
                    and estado.sentimento == "neutro"):
                permitir = acao.tipo == "responder" and not acao.parametros.get("propor_registro")
                texto = self.redator.envolver(estado, mensagem_limpa, texto, permitir,
                                              respostas_anteriores(conversa_id) if self.concisao else [])
            if not partes:
                links = links_mod.gerar(estado, chave_final, acao.parametros,
                                        bool(estado.coletados.get("compra")))
                etapa_lead = links_mod.etapa_do_lead(chave_final, acao.parametros, links)
            texto, concluiu = fechar_turno(estado, acao, texto)
            if concluiu and not partes:
                texto = fechamento_cordial(estado, acao, chave_final, texto)
            if oferecer and estado.aguardando is None:  # no máximo uma pergunta por turno
                texto, concluiu = oferecer_humano(estado, texto), False
            if chave_final == "saudacao":
                estado.ja_saudou = True
            if self.concisao:
                # só dentro do turno: o bloco factual de uma pergunta repetida precisa sair inteiro
                texto, removidas = deduplicar_frases(texto, [])
                contagens["frases_removidas"] += removidas
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

        contagens.update(registrar_entregas(estado, texto, fatos))
        for fonte in (self.decisor, self.redator, self.reserva):
            if fonte is not None and hasattr(fonte, "drenar"):
                t, c = fonte.drenar()
                telemetria += [limpar_pii(x, estado, mensagem) for x in t]
                contagens.update(c)
        salvar_estado(conversa_id, estado)
        gravar_mensagem(conversa_id, estado.turno, texto, origem)
        latencia = int((time.perf_counter() - inicio) * 1000)
        estado_resposta = classificar_estado(estado, acoes, concluiu, motivo_saida)
        try:
            trace.registrar_turno({
                "ts": config.agora().isoformat(), "conversa": conversa_id, "turno": estado.turno, "origem": origem,
                "intencao": estado.intencao, "sentimento": estado.sentimento, "resposta": chave_final, "motivo_saida": motivo_saida,
                "estado_antes": antes, "estado_depois": estado.resumo_curto(), "passos": passos_trace,
                "acoes": acoes, "estado_resposta": estado_resposta, "latencia_ms": latencia,
                "modelo": getattr(self.decisor, "modelo", None), "concisao": self.concisao,
                "etapa_lead": etapa_lead, "links": [x.get("href") or x.get("acao") for x in links],
                "contagens": dict(contagens), "telemetria_modelo": telemetria,
                "tokens": sum(x.get("tokens_prompt", 0) + x.get("tokens_resposta", 0) for x in telemetria)})
        except OSError:
            log.exception("nao foi possivel gravar o trace")
        return Resposta(texto=texto, acoes=acoes, fatos=fatos, estado=estado_resposta, contagens=dict(contagens),
                        links=links)


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
    if r.estado in ("falha", "negado") and nome in ("consultar_pedido", "consultar_pedido_demo", "buscar_produtos", "ver_produto",
                                                    "calcular_condicoes", "consultar_politica",
                                                    "registrar_encaminhamento", "listar_promocoes", "estimar_frete"):
        estado.falhas_seguidas += 1
    elif r.estado == "ok":
        estado.falhas_seguidas = 0
    if nome == "consultar_pedido":
        if r.estado == "ok":
            estado.coletados["pedido"] = r.dados
        elif r.estado == "negado":
            estado.declarados.pop("pedido_id", None)  # pede de novo os dois dados
    elif nome == "consultar_pedido_demo":  # pedido PED-: mesma conversa, sem telefone
        if r.estado == "ok":
            estado.coletados["pedido_demo"] = r.dados
        elif r.estado == "negado":
            estado.declarados.pop("pedido_demo", None)
    elif nome == "buscar_produtos" and r.estado == "ok" and passo.args.get("limite") != 1:
        # a lista mostrada ao cliente: base do "qual o mais barato?" e do "tem em estoque?" sem produto
        base = {k: v for k, v in passo.args.items() if k not in ("limite", "deslocamento")}
        estado.coletados["ultima_busca"] = {"args": base, "ids": [i["id"] for i in r.dados["itens"]],
                                            "total": r.dados["total_encontrado"]}
    elif nome == "ver_produto":
        if r.estado == "ok":
            estado.coletados["ultimo_produto"] = r.dados["id"]
            recentes = [i for i in estado.coletados.get("ultimos_produtos", []) if i != r.dados["id"]]
            estado.coletados["ultimos_produtos"] = [*recentes, r.dados["id"]][-2:]  # base do "os dois"
            estado.coletados.pop("recomendado", None)  # o produto consultado agora é o foco
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
                                                 "ambiguidades": [a["descricao"] for a in s["ambiguidades"]],
                                                 "ambiguidades_ids": [a["id"] for a in s["ambiguidades"]]}
        completar_datas(estado)
    elif nome == "registrar_encaminhamento" and r.estado == "ok":
        estado.coletados["protocolo"] = r.dados["protocolo"]
        if not r.dados.get("repetido"):
            estado.acoes_concluidas.append(f"chamado:{r.dados['protocolo']}")
            estado.chamados_assunto[estado.ultimo_assunto or "geral"] = r.dados["protocolo"]


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

# Sem redação do modelo: recusa e escopo (o texto livre não pode abrir brecha), e respostas curtas já completas.
SEM_REDACAO = {"saudacao", "recusa_manipulacao", "recusa_dado_de_terceiro", "recusa_instrucoes", "fora_escopo",
               "fora_escopo_geral", "identidade", "encerramento", "confirmacao_solta",
               # toda recusa fica sem texto livre do modelo: ele não pode abrir brecha nem suavizar o "não"
               "pedido_negado", "pedido_negado_limite", "pedido_demo_negado", "item_nao_elegivel",
               "preco_promocao_conflitante", "cupom_inexistente", "endereco_pedido_privado", "acolhimento", "so_portugues",
               "comparacao", "frete_cotacao_individual", "frete_cep_indisponivel", "registro_falhou",
               "sem_dado", "sem_info", "dado_recusado",
               # lead: a resposta de objeção e a de "vou pensar" não ganham convite do modelo
               "objecao_preco", "vou_pensar"}

# Respostas que já cuidam do tom ou que são o próprio atendimento: sem frase de reconhecimento nem oferta.
SEM_AJUSTE_DE_TOM = {"acolhimento", "so_portugues", "saudacao", "reclamacao_empatia", "pedir_relato", "chamado_registrado", "atendente_ja_registrado",
                     "confirmar_registro", "registro_cancelado", "registro_falhou", "perguntas_repetidas",
                     "nao_entendi_de_novo", "falha_ferramenta", "negacao_atendente", "negacao_reclamacao", "dado_recusado",
                     "encerramento", "identidade", "confirmacao_solta"}
FECHO_DISPENSAVEL = re.compile(r"^(Se quiser|Se precisar|Se estiver|Posso ajudar)")


def _encurtar(texto: str) -> str:
    """Tira só o fecho de cortesia sem pergunta, no fim; fato, número e pergunta ficam."""
    linhas = texto.split("\n")
    if len(linhas) > 1 and FECHO_DISPENSAVEL.match(linhas[-1]) and "?" not in linhas[-1]:
        linhas.pop()
    return "\n".join(linhas)


def _deve_oferecer(estado: Estado, acao: Acao) -> bool:
    s = estado.sentimentos
    insistente = estado.sentimento == "irritado" or (
        estado.sentimento == "frustrado" and len(s) >= 2 and s[-2] == "frustrado")
    espacada = estado.turno_oferta == 0 or estado.turno - estado.turno_oferta > 1
    ja_ha_chamado = any(a.startswith("chamado:") for a in estado.acoes_concluidas)
    return (insistente and espacada and acao.tipo == "responder" and not acao.parametros.get("propor_registro")
            and not estado.pendentes and estado.oferta_humano != "recusada" and not ja_ha_chamado)


def ajustar_tom(estado: Estado, acao: Acao, chave: str, texto: str) -> tuple[str, bool]:
    """Sentimento muda só o tom: reconhecimento curto antes do bloco, fecho de cortesia a menos e, se couber,
    oferta de atendente. O bloco factual não é alterado."""
    if estado.sentimento == "neutro" or chave in SEM_AJUSTE_DE_TOM:
        return texto, False
    texto = _encurtar(texto)
    frase = respostas.reconhecimento(estado)
    if frase:
        texto = f"{frase}\n{texto}"
    return texto, _deve_oferecer(estado, acao)


def oferecer_humano(estado: Estado, texto: str) -> str:
    """Pergunta de sim ou não; o chamado só nasce com o 'sim' explícito, pelo caminho de sempre."""
    estado.coletados["proposta"] = {"tipo": "atendente", "origem": "sentimento",
                                    "resumo": "Cliente demonstrou frustracao e aceitou atendimento humano."}
    estado.aguardando = "confirmacao_registro"
    estado.oferta_humano = "feita"
    estado.turno_oferta = estado.turno
    return f"{texto}\n{respostas.OFERTA_HUMANO}"


# Respostas que informam e encerram o assunto: ali o manual (7.2, passo 5) manda confirmar se o cliente precisa de
# mais alguma coisa. Nunca em recusa, oferta, pergunta, encerramento do cliente ou cliente irritado.
COM_FECHAMENTO = {"contato", "pagamento", "frete_calculado", "frete_produto", "frete_prazo", "frete_estimado",
                  "frete_cidade_base", "frete_outra_cidade", "frete_modalidade", "frete_grande_porte", "garantia_info",
                  "reembolso_prazo", "previsao_entrega", "status_pedido", "status_pedido_demo", "devolucao_frete",
                  "devolucao_loja_fisica", "rain_check", "rastreio_como", "privacidade", "empresa_dados",
                  "garantia_excluida", "trocas_detalhe", "disponibilidade"}
INTERVALO_FECHAMENTO = 3  # turnos entre dois fechamentos: perguntar a cada resposta cansa


def fechamento_cordial(estado: Estado, acao: Acao, chave: str | None, texto: str) -> str:
    """Pergunta se precisa de mais alguma coisa ao fim de uma resposta informativa, uma pergunta só por resposta."""
    if (chave not in COM_FECHAMENTO or acao.tipo != "responder" or "?" in texto or estado.sentimento != "neutro"
            or estado.aguardando or acao.parametros.get("propor_registro")
            or estado.turno - estado.turno_fechamento <= INTERVALO_FECHAMENTO and estado.turno_fechamento):
        return texto
    estado.turno_fechamento = estado.turno
    return texto + chr(10) + respostas.FECHAMENTO


MAX_REPETICOES_PERGUNTA = 2  # a mesma pergunta de dado, no máximo 2 vezes seguidas


def _assinatura(acao: Acao) -> dict[str, Any]:
    sig = {"chave": acao.resposta, "campos": list(acao.parametros.get("campos", []))}
    if acao.resposta == "pedir_pedido":  # pedir só o que falta (número, depois o final) é avanço, não repetição
        sig["tem"] = [bool(acao.parametros.get("tem_pedido")), bool(acao.parametros.get("tem_final"))]
    return sig


def limitar_repeticao(acao: Acao, estado: Estado) -> Acao:
    """A terceira pergunta igual seguida vira oferta de registro para a equipe, em vez de outro laço."""
    if acao.tipo != "perguntar" or acao.parametros.get("aguardando") in ("detalhe_trocas",):
        return acao  # a oferta de detalhes é informação, não um dado que o cliente deixou de dar
    anterior = estado.ultima_pergunta
    assinatura = _assinatura(acao)
    if (anterior and anterior.get("vezes", 0) >= MAX_REPETICOES_PERGUNTA
            and {k: anterior.get(k) for k in assinatura} == assinatura):
        resumo = (f"Cliente nao conseguiu responder a mesma pergunta ({assinatura['chave']}) apos "
                  f"{MAX_REPETICOES_PERGUNTA} tentativas. Assunto: {estado.objetivo}.")
        pedido = estado.coletados.get("pedido")
        if pedido:
            resumo += f" Pedido consultado: {pedido['pedido_id']}."
        return Acao(tipo="responder", resposta="perguntas_repetidas",
                    parametros={"propor_registro": {"tipo": "atendente", "resumo": resumo}})
    return acao


def fechar_turno(estado: Estado, acao: Acao, texto: str) -> tuple[str, bool]:
    p = acao.parametros
    chave = acao.resposta
    estado.incompreensoes = estado.incompreensoes + 1 if chave == "nao_entendi" else 0
    if acao.tipo == "perguntar":
        assinatura = _assinatura(acao)
        igual = {k: estado.ultima_pergunta.get(k) for k in assinatura} == assinatura
        estado.ultima_pergunta = {**assinatura, "vezes": estado.ultima_pergunta.get("vezes", 0) + 1 if igual else 1}
        estado.aguardando = p["aguardando"]
        return texto, False
    estado.ultima_pergunta = {}
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
    if p.get("oferta_parcelas"):
        estado.aguardando = "parcelamento"  # a resposta termina em pergunta de sim ou não sobre as parcelas
    elif p.get("oferta_condicoes"):
        estado.aguardando = "condicoes"  # termina em "quer ver as condições dele?": o sim mostra o preço
    # uma pergunta por resposta: se o texto já termina em pergunta, o convite de retomar espera o próximo turno
    if estado.pendentes and not texto.rstrip().endswith("?"):
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


# --- dado pessoal fora do trace -------------------------------------------------------------

NOME_DITO = re.compile(r"(?:sou|me chamo|meu nome (?:e|é)|aqui (?:e|é))\s+([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+){0,3})", re.I)


def limpar_pii(valor: Any, estado: Estado, mensagem: str) -> Any:
    """Tira telefone, e-mail, final digitado e nome dito pelo cliente de qualquer texto que vá para o trace."""
    from ..ferramentas.encaminhamento import mascarar_dado_pessoal

    if isinstance(valor, dict):
        return {k: limpar_pii(v, estado, mensagem) for k, v in valor.items()}
    if isinstance(valor, list):
        return [limpar_pii(v, estado, mensagem) for v in valor]
    if not isinstance(valor, str):
        return valor
    texto = mascarar_dado_pessoal(valor)
    final = estado.slots.get("final_telefone")
    if final:
        texto = texto.replace(final, "[final]")
    for nome in NOME_DITO.findall(mensagem):
        texto = re.sub(re.escape(nome.strip()), "[nome]", texto, flags=re.I)
    return texto
