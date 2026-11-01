"""RegrasDecisor: o controle determinístico. Um decisor com LLM implementa o mesmo Protocol."""
from __future__ import annotations

from typing import Any

from ..ferramentas.envelope import Resultado
from .estado import Acao, Estado

REGRA_POR_INTENCAO = {"devolucao": "arrependimento", "troca_preferencia": "preferencia", "defeito": "defeito"}
TEMA_POR_INTENCAO = {"devolucao": "arrependimento", "troca_preferencia": "troca_preferencia", "defeito": "defeito"}
TENTATIVAS_ANTES_DE_OFERECER_ATENDENTE = 3  # alinhado ao limite de consultar_pedido


def ferramenta(nome: str, **args: Any) -> Acao:
    return Acao(tipo="ferramenta", ferramenta=nome, args=args)


def responder(chave: str, **parametros: Any) -> Acao:
    return Acao(tipo="responder", resposta=chave, parametros=parametros)


def perguntar(chave: str, aguardando: str, **parametros: Any) -> Acao:
    return Acao(tipo="perguntar", resposta=chave, parametros={"aguardando": aguardando, **parametros})


def propor(chave: str, tipo: str, resumo: str, **parametros: Any) -> Acao:
    return Acao(tipo="responder", resposta=chave,
                parametros={"propor_registro": {"tipo": tipo, "resumo": resumo}, **parametros})


def _trecho_excluido(r: Resultado, texto: str) -> str | None:
    """Linha do manual que exclui da troca o item citado, se o cliente citou algum (casamento por palavras
    distintivas de cada item da lista, nunca por palavra genérica)."""
    from ..texto import radical, tokens

    genericas = {"instrumentos", "instrumento", "produtos", "produto", "adquiridos", "com", "sob", "de", "do", "da"}
    msg = {radical(t) for t in tokens(texto)}
    for s in r.dados["secoes"]:
        itens = [c["valor"] for c in s["condicoes"] if c["chave"] == "trocas.itens_nao_elegiveis"]
        for lista in itens:
            for item in lista:
                distintivas = {radical(t) for t in tokens(item) if len(t) >= 5 and t not in genericas}
                if distintivas and len(distintivas & msg) / len(distintivas) >= 0.4:
                    achado = next((ln.strip(" •\t") for ln in (s["texto"] or "").splitlines()
                                   if distintivas & {radical(t) for t in tokens(ln)} & msg), None)
                    return (achado or item).rstrip(".")
    return None


def resultado_de(estado: Estado, nome: str, **args: Any) -> Resultado | None:
    for p in reversed(estado.passos):
        if p.ferramenta == nome and all(p.args.get(k) == v for k, v in args.items()):
            return p.resultado
    return None


class RegrasDecisor:
    def decidir(self, estado: Estado, mensagem: str) -> Acao:
        s = estado.slots
        if s.get("cancelou"):
            return responder("registro_cancelado")
        proposta = estado.coletados.get("proposta")
        if estado.permissao_registro and proposta:
            return self._registrar(estado, proposta["tipo"], proposta["resumo"])
        metodo = getattr(self, f"_i_{estado.intencao}", None) or self._i_desconhecido
        return metodo(estado)

    # --- apoio -----------------------------------------------------------------------

    def _info(self, estado: Estado, temas: list[str], chave: str, **parametros: Any) -> Acao:
        r = resultado_de(estado, "consultar_politica", temas=temas)
        if r is None:
            return ferramenta("consultar_politica", temas=temas)
        if r.estado != "ok":
            return self._erro(estado, r)
        return responder(chave, **parametros)

    def _erro(self, estado: Estado, r: Resultado) -> Acao:
        if r.estado == "vazio":
            return propor("sem_dado", "sem_dado",
                          f"Cliente perguntou sobre {estado.objetivo} e o sistema nao tem a informacao.")
        if estado.falhas_seguidas >= 2:
            return propor("falha_ferramenta", "falhas",
                          f"Falhas repetidas ao consultar o sistema durante {estado.objetivo}.")
        return responder("falha_ferramenta")

    def _registrar(self, estado: Estado, tipo: str, resumo: str) -> Acao:
        if resultado_de(estado, "consultar_politica", temas=["horario"]) is None:
            return ferramenta("consultar_politica", temas=["horario"])  # para informar o retorno fora do expediente
        r = resultado_de(estado, "registrar_encaminhamento")
        if r is None:
            n = sum(1 for a in estado.acoes_concluidas if a.startswith("chamado:"))
            return Acao(tipo="encaminhar", ferramenta="registrar_encaminhamento",
                        args={"tipo": tipo, "resumo": resumo, "chave_idempotencia": f"{estado.objetivo}:{n}"})
        if r.estado == "ok":
            return responder("chamado_registrado")
        return responder("registro_falhou")

    # --- pedido ----------------------------------------------------------------------

    def _pedido(self, estado: Estado) -> tuple[Acao | None, dict[str, Any] | None]:
        pedido = estado.coletados.get("pedido")
        if pedido:
            return None, pedido
        pid, final = estado.declarado("pedido_id"), estado.slots.get("final_telefone")
        r = estado.ultimo("consultar_pedido")  # resultado deste turno, se houve
        if r is not None:
            if r.estado == "negado":
                if estado.falhas_seguidas >= TENTATIVAS_ANTES_DE_OFERECER_ATENDENTE:
                    return propor("pedido_negado_limite", "atendente",
                                  "Cliente nao conseguiu identificar o pedido apos varias tentativas."), None
                return perguntar("pedido_negado", "pedido"), None
            return self._erro(estado, r), None
        if pid is None or final is None:
            return perguntar("pedir_pedido", "pedido", tem_pedido=pid is not None, tem_final=final is not None), None
        return ferramenta("consultar_pedido", pedido_id=pid, final_telefone=final), None

    def _i_status_pedido(self, estado: Estado) -> Acao:
        demo = estado.declarado("pedido_demo")
        r = estado.ultimo("consultar_pedido_demo")
        if demo or r is not None:  # pedido de demonstração: nunca cai na consulta dos pedidos dos dados
            if r is None:
                return ferramenta("consultar_pedido_demo", numero=demo)
            return responder("status_pedido_demo") if r.estado == "ok" else (
                responder("pedido_demo_negado") if r.estado == "negado" else self._erro(estado, r))
        acao, pedido = self._pedido(estado)
        if acao:
            return acao
        if pedido["previsao_vencida"]:
            return propor("status_pedido", "atendente",
                          f"Cliente consultou o pedido {pedido['pedido_id']} e a previsao de entrega ja passou.",
                          oferta="previsao_vencida")
        return responder("status_pedido")

    # --- pós-venda -------------------------------------------------------------------

    def _item_nao_elegivel(self, estado: Estado) -> Acao | None:
        """Cliente fala de item que o manual exclui de troca (ex.: boquilha): responde a exceção, sem pedir pedido."""
        if estado.objetivo not in ("devolucao", "troca_preferencia"):
            return None
        r = resultado_de(estado, "consultar_politica", temas=["itens_nao_elegiveis"])
        if r is None:
            return ferramenta("consultar_politica", temas=["itens_nao_elegiveis"])
        if r.estado != "ok":
            return None
        trecho = _trecho_excluido(r, estado.slots.get("texto_limpo", ""))
        return responder("item_nao_elegivel", trecho=trecho) if trecho else None

    def _posvenda(self, estado: Estado) -> Acao:
        regra = estado.coletados.get("regra")
        if not estado.coletados.get("pedido") and (not regra or regra.get("objetivo") != estado.objetivo):
            acao = self._item_nao_elegivel(estado)
            if acao:
                return acao
        acao, pedido = self._pedido_com_regra(estado)
        if acao:
            return acao
        intencao = estado.objetivo
        regra = estado.coletados.get("regra")
        if not regra or regra.get("objetivo") != intencao:
            return self._info_regra(estado, intencao)
        faltam = [c for c in regra["valor"]["dados_necessarios"] if estado.declarado(c) is None]
        if faltam:
            return perguntar("pedir_dados_posvenda", "dados_posvenda", campos=faltam)
        resumo = self._resumo_posvenda(estado, pedido, regra)
        return propor("propor_posvenda", "atendente", resumo)

    def _pedido_com_regra(self, estado: Estado) -> tuple[Acao | None, dict[str, Any] | None]:
        """Antes de pedir o pedido pela primeira vez, diz a regra do manual (o cliente já sabe o prazo)."""
        pedido = estado.coletados.get("pedido")
        sem_dados = estado.declarado("pedido_id") is None and estado.slots.get("final_telefone") is None
        regra = estado.coletados.get("regra")
        if (not pedido and sem_dados and estado.objetivo in ("devolucao", "troca_preferencia", "defeito")
                and (not regra or regra.get("objetivo") != estado.objetivo)):
            return self._info_regra(estado, estado.objetivo), None
        acao, pedido = self._pedido(estado)
        if acao and acao.resposta == "pedir_pedido" and regra and regra.get("objetivo") == estado.objetivo and sem_dados:
            acao.parametros["com_regra"] = True
        return acao, pedido

    def _info_regra(self, estado: Estado, intencao: str) -> Acao:
        temas = [TEMA_POR_INTENCAO[intencao]]
        r = resultado_de(estado, "consultar_politica", temas=temas)
        if r is None:
            return ferramenta("consultar_politica", temas=temas)
        return self._erro(estado, r)  # ok já foi integrado em coletados["regra"]; qualquer outro estado é erro

    def _resumo_posvenda(self, estado: Estado, pedido: dict[str, Any], regra: dict[str, Any]) -> str:
        rotulos = {"devolucao": "devolucao (arrependimento)", "troca_preferencia": "troca por preferencia",
                   "defeito": "troca por defeito"}
        decl = "; ".join(f"{c}: {estado.declarado(c)}" for c in regra["valor"]["dados_necessarios"])
        return (f"Solicitacao de {rotulos[estado.objetivo]} do pedido {pedido['pedido_id']}. "
                f"Declarado pelo cliente, nao verificado: {decl}. Elegibilidade a confirmar pela equipe.")

    _i_devolucao = _i_troca_preferencia = _i_defeito = _posvenda

    def _i_info_trocas(self, estado: Estado) -> Acao:
        r = resultado_de(estado, "consultar_politica", temas=["trocas", "garantia"])
        if r is None:
            return ferramenta("consultar_politica", temas=["trocas", "garantia"])
        if r.estado != "ok":
            return self._erro(estado, r)
        return perguntar("trocas_info", "detalhe_trocas")  # uma pergunta só: detalhar exclusões e garantia

    def _i_detalhe_trocas(self, estado: Estado) -> Acao:
        return self._info(estado, ["trocas", "garantia"], "trocas_detalhe")

    def _i_garantia(self, estado: Estado) -> Acao:
        return self._info(estado, ["garantia"], "garantia_info", oferta="solicitacao")

    # --- informativos ----------------------------------------------------------------

    def _i_saudacao(self, estado: Estado) -> Acao:
        return self._info(estado, ["empresa", "horario"], "saudacao")

    def _i_horario(self, estado: Estado) -> Acao:
        return self._info(estado, ["horario"], "horario")

    def _i_endereco(self, estado: Estado) -> Acao:
        return self._info(estado, ["endereco"], "endereco")

    def _i_contato(self, estado: Estado) -> Acao:
        return self._info(estado, ["contato"], "contato")

    def _i_pagamento(self, estado: Estado) -> Acao:
        return self._info(estado, ["pagamento"], "pagamento")

    def _i_fora_escopo(self, estado: Estado) -> Acao:
        chave = "fora_escopo_geral" if estado.slots.get("assunto_geral") else "fora_escopo"
        return self._info(estado, ["escopo"], chave)

    def _i_dado_recusado(self, estado: Estado) -> Acao:
        return responder("dado_recusado")

    def _i_retomada_recusada(self, estado: Estado) -> Acao:
        return responder("ok_sem_retomar")

    def _i_frete(self, estado: Estado) -> Acao:
        s = estado.slots
        cidade = s.get("cidade") or estado.coletados.get("cidade")
        valor = s.get("valor") or estado.coletados.get("valor_pedido")
        if cidade:
            estado.coletados["cidade"] = cidade
        if cidade and valor:
            estado.coletados["valor_pedido"] = valor
            r = resultado_de(estado, "calcular_condicoes", cidade=cidade)
            if r is None:
                return ferramenta("calcular_condicoes", valor=valor, forma="boleto", cidade=cidade, valor_pedido=valor)
            if r.estado != "ok":
                return self._erro(estado, r)
            if r.dados["frete"]["situacao"] == "requer_confirmacao":
                return propor("frete_calculado", "duvida_politica",
                              "Cliente perguntou frete de pedido exatamente no valor limite do manual.")
            return responder("frete_calculado")
        if cidade and s.get("pergunta_prazo"):
            r = resultado_de(estado, "consultar_politica", temas=["frete"])
            if r is None:
                return ferramenta("consultar_politica", temas=["frete"])
            if r.estado != "ok":
                return self._erro(estado, r)
            return perguntar("frete_prazo", "valor_pedido", cidade=cidade)
        if cidade:
            return perguntar("pedir_valor_pedido", "valor_pedido")
        r = resultado_de(estado, "consultar_politica", temas=["frete"])
        if r is None:
            return ferramenta("consultar_politica", temas=["frete"])
        if r.estado != "ok":
            return self._erro(estado, r)
        return perguntar("frete_info", "cidade")

    # --- produtos --------------------------------------------------------------------

    def _i_busca_produto(self, estado: Estado) -> Acao:
        s = estado.slots
        args: dict[str, Any] = {}
        if s.get("categoria"):
            args["categoria"] = s["categoria"]
        if s.get("termo"):
            args["termo"] = s["termo"]
        for k in ("preco_min", "preco_max"):
            if s.get(k) is not None:
                args[k] = s[k]
        if not args:
            return perguntar("pedir_categoria", "categoria")
        r = resultado_de(estado, "buscar_produtos", **args)
        if r is None:
            return ferramenta("buscar_produtos", **args)
        if r.estado == "falha":
            return self._erro(estado, r)
        return responder("busca")

    def _produto(self, estado: Estado) -> tuple[Acao | None, dict[str, Any] | None]:
        s = estado.slots
        ref = s.get("produto_id") or s.get("referencia") or estado.coletados.get("referencia")
        if ref is None:
            return perguntar("pedir_produto", "referencia_produto"), None
        r = resultado_de(estado, "ver_produto", referencia=ref)
        if r is None:
            return ferramenta("ver_produto", referencia=ref), None
        if r.estado == "ok":
            return None, r.dados
        if r.estado == "ambiguo":
            return perguntar("escolha_produto", "escolha_produto"), None
        if r.estado == "vazio":
            return perguntar("produto_nao_encontrado", "referencia_produto"), None
        return self._erro(estado, r), None

    def _i_disponibilidade(self, estado: Estado) -> Acao:
        acao, produto = self._produto(estado)
        if acao:
            return acao
        if produto["situacao_venda"] != "disponivel":
            return self._indisponivel(estado, produto)
        return responder("disponibilidade")

    def _indisponivel(self, estado: Estado, produto: dict[str, Any]) -> Acao:
        """Esgotado, descontinuado ou em breve: sem condições de pagamento, com alternativas da categoria."""
        args = {"categoria": produto["categoria"], "limite": 3}
        r = resultado_de(estado, "buscar_produtos", **args)
        if r is None:
            return ferramenta("buscar_produtos", **args)
        if r.estado == "falha":
            estado.coletados["parecidas"] = {"produto_id": produto["id"], "categoria": produto["categoria"]}
            return perguntar("produto_indisponivel", "retentar_parecidas")
        return responder("produto_indisponivel")

    def _i_retentar_parecidas(self, estado: Estado) -> Acao:
        """O "sim" à oferta de opções parecidas: nova consulta real, na mesma categoria."""
        alvo = estado.coletados.get("parecidas")
        if not alvo:
            return responder("nao_entendi")
        produto = resultado_de(estado, "ver_produto", referencia=alvo["produto_id"])
        if produto is None:
            return ferramenta("ver_produto", referencia=alvo["produto_id"])
        if produto.estado != "ok":
            return self._erro(estado, produto)
        args = {"categoria": alvo["categoria"], "limite": 3}
        r = resultado_de(estado, "buscar_produtos", **args)
        if r is None:
            return ferramenta("buscar_produtos", **args)
        if r.estado == "falha":
            return perguntar("produto_indisponivel", "retentar_parecidas")
        estado.coletados.pop("parecidas", None)
        return responder("produto_indisponivel")

    def _i_promocao(self, estado: Estado) -> Acao:
        args = {"termo": estado.slots["termo_promocao"]} if estado.slots.get("termo_promocao") else {}
        r = resultado_de(estado, "listar_promocoes", **args)
        if r is None:
            return ferramenta("listar_promocoes", **args)
        if r.estado == "falha":
            return self._erro(estado, r)
        return responder("promocoes")

    def _i_tentativa_manipulacao(self, estado: Estado) -> Acao:
        return self._info(estado, ["pagamento"], "recusa_manipulacao")

    def _i_dado_de_terceiro(self, estado: Estado) -> Acao:
        return responder("recusa_dado_de_terceiro")

    def _i_preco_produto(self, estado: Estado) -> Acao:
        acao, produto = self._produto(estado)
        if acao:
            return acao
        if produto["situacao_venda"] != "disponivel":
            return self._indisponivel(estado, produto)
        forma = estado.slots.get("forma") or estado.coletados.get("forma") or "pix"
        parcelas = estado.slots.get("parcelas") or estado.coletados.get("parcelas") or 1
        args = {"produto_id": produto["id"], "forma": forma, "parcelas": parcelas}
        r = resultado_de(estado, "calcular_condicoes", **args)
        if r is None:
            return ferramenta("calcular_condicoes", **args)
        if r.estado == "ambiguo":
            return propor("preco_promocao_conflitante", "duvida_politica",
                          f"Produto {produto['id']} com mais de uma promocao ativa; cliente pediu o preco.")
        if r.estado != "ok":
            return self._erro(estado, r)
        if r.dados.get("permitido") == "requer_confirmacao":
            return propor("preco", "duvida_politica",
                          f"Cliente perguntou parcelamento em {parcelas}x do produto {produto['id']}; "
                          "as duas leituras da parcela minima do manual divergem.")
        return responder("preco")

    # --- reclamação e atendente ------------------------------------------------------

    def _i_reclamacao(self, estado: Estado) -> Acao:
        s = estado.slots
        if s.get("nega_reclamacao"):
            return responder("negacao_reclamacao")
        relato = s.get("relato") or estado.coletados.get("relato")
        if not relato and s["palavras"] >= 7:
            relato = s["texto_limpo"]
        if relato:
            estado.coletados["relato"] = relato
        explicito = estado.coletados.get("registro_explicito")
        if not relato:
            return perguntar("pedir_relato", "relato", explicito=bool(explicito))
        resumo = f"Reclamacao do cliente: {relato}"
        if explicito and estado.permissao_registro:
            return self._registrar(estado, "reclamacao", resumo)
        return propor("reclamacao_empatia", "reclamacao", resumo)

    def _i_pedir_atendente(self, estado: Estado) -> Acao:
        if estado.slots.get("nega_atendente"):
            return responder("negacao_atendente")
        aberto = [a.split(":", 1)[1] for a in estado.acoes_concluidas if a.startswith("chamado:")]
        if aberto and resultado_de(estado, "registrar_encaminhamento") is None:  # já há chamado em aberto: não abre outro
            if resultado_de(estado, "consultar_politica", temas=["horario"]) is None:
                return ferramenta("consultar_politica", temas=["horario"])
            return responder("atendente_ja_registrado", protocolo=aberto[-1])
        resumo = "Cliente pediu atendimento humano."
        if estado.pendentes:
            resumo += f" Assunto anterior: {estado.pendentes[-1]['objetivo']}."
        pedido = estado.coletados.get("pedido")
        if pedido:
            resumo += f" Pedido consultado: {pedido['pedido_id']}."
        return self._registrar(estado, "atendente", resumo)

    def _i_desconhecido(self, estado: Estado) -> Acao:
        if estado.incompreensoes >= 1:
            return propor("nao_entendi_de_novo", "sem_dado",
                          "Cliente fez uma pergunta que o assistente nao conseguiu entender.")
        return responder("nao_entendi")
