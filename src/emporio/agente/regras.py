"""RegrasDecisor: o controle determinístico. Um decisor com LLM implementa o mesmo Protocol."""
from __future__ import annotations

from datetime import date
from typing import Any

from .. import config
from ..ferramentas.envelope import Resultado
from ..texto import normalizar
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


def categorias_com_produto() -> list[str]:
    """Categorias do cadastro em que a busca acha produto vendável (a consulta é a própria ferramenta de busca)."""
    from ..ferramentas.produtos import buscar_produtos
    from . import catalogo

    return [nome for nome in catalogo.vocabulario().categorias if buscar_produtos(categoria=nome, limite=1).estado == "ok"]


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
                acertos = distintivas & msg
                if distintivas and (len(acertos) / len(distintivas) >= 0.4 or len(acertos) >= 2):
                    achado = next((ln.strip(" •\t") for ln in (s["texto"] or "").splitlines()
                                   if distintivas & {radical(t) for t in tokens(ln)} & msg), None)
                    return (achado or item).rstrip(".")
    return None


def _condicao(r: Resultado, chave: str) -> Any:
    """Valor de uma condição do manual dentro de um resultado de consultar_politica."""
    for sec in r.dados["secoes"]:
        for c in sec["condicoes"]:
            if c["chave"] == chave:
                return c["valor"]
    return None


def resultado_de(estado: Estado, nome: str, **args: Any) -> Resultado | None:
    for p in reversed(estado.passos):
        if p.ferramenta == nome and all(p.args.get(k) == v for k, v in args.items()):
            return p.resultado
    return None


def busca_exata(estado: Estado, args: dict[str, Any]) -> Resultado | None:
    """Resultado de buscar_produtos com exatamente estes argumentos (a consulta de apoio tem argumentos a mais)."""
    for p in reversed(estado.passos):
        if p.ferramenta == "buscar_produtos" and p.args == args:
            return p.resultado
    return None


def recusada(estado: Estado, oferta: str) -> bool:
    return oferta in (estado.coletados.get("ofertas_recusadas") or [])


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
        if resultado_de(estado, "consultar_politica", temas=["horario", "contato"]) is None:
            return ferramenta("consultar_politica", temas=["horario", "contato"])  # retorno fora do expediente e canais
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

    def _prazo_defeito(self, estado: Estado) -> int | None:
        regra = estado.coletados.get("regra")
        if regra and regra.get("objetivo") == "defeito":
            return int(regra["valor"]["prazo_dias"])
        return None

    def _defeito_fora_do_prazo(self, estado: Estado, dias: int) -> Acao | None:
        """Defeito depois do prazo de troca (4.2): a garantia é com o fabricante e a loja pode intermediar."""
        # a resposta cita o fabricante do manual: a consulta tem de estar neste turno, mesmo com a regra já guardada
        r = resultado_de(estado, "consultar_politica", temas=["defeito"])
        if r is None:
            return ferramenta("consultar_politica", temas=["defeito"])
        if r.estado != "ok":
            return self._erro(estado, r)
        if dias > (self._prazo_defeito(estado) or dias):
            return propor("defeito_apos_prazo", "atendente",
                          "Cliente com defeito depois do prazo de troca pediu orientacao; a equipe pode intermediar "
                          "a garantia com o fabricante.", dias=dias)
        return None

    def _exclusao_garantia(self, estado: Estado) -> Acao | None:
        """Queda e mau uso (8.3) têm resposta própria, nunca a regra de troca por defeito ou preferência."""
        s = estado.slots
        if estado.objetivo not in ("defeito", "garantia") or not (s.get("mau_uso") or s.get("desgaste")):
            return None
        r = resultado_de(estado, "consultar_politica", temas=["garantia"])
        if r is None:
            return ferramenta("consultar_politica", temas=["garantia"])
        if r.estado != "ok":
            return self._erro(estado, r)
        return responder("garantia_excluida", desgaste=bool(s.get("desgaste")), mau_uso=bool(s.get("mau_uso")))

    def _avaria(self, estado: Estado) -> Acao | None:
        """Avaria no recebimento (5.2): recusar o recebimento e falar com a loja, sem a regra de defeito."""
        if estado.objetivo != "defeito" or not estado.slots.get("avaria") or estado.slots.get("pergunta_prazo"):
            return None  # quem pergunta o prazo de troca recebe a regra de defeito (variação v14 do eval)
        r = resultado_de(estado, "consultar_politica", temas=["frete"])
        if r is None:
            return ferramenta("consultar_politica", temas=["frete"])
        if r.estado != "ok":
            return self._erro(estado, r)
        if _condicao(r, "frete.avaria_recusar_recebimento") is not True:
            return None
        return propor("avaria_recebimento", "atendente",
                      "Cliente relatou avaria no recebimento; orientado a recusar o recebimento e falar com a loja.")

    def _devolucao_na_loja(self, estado: Estado) -> Acao | None:
        """Arrependimento é regra de compra online: na loja física explica e indica troca por defeito ou preferência."""
        loja = estado.slots.get("canal_compra") == "loja" or estado.declarado("canal_compra") == "loja"
        if estado.objetivo != "devolucao" or not loja:
            return None
        r = resultado_de(estado, "consultar_politica", temas=["trocas"])
        if r is None:
            return ferramenta("consultar_politica", temas=["trocas"])
        return responder("devolucao_loja_fisica") if r.estado == "ok" else self._erro(estado, r)

    def _reembolso_de_cancelado(self, estado: Estado) -> Acao | None:
        """Pedido já consultado e cancelado, com pagamento: devolver o dinheiro é reembolso, não abertura de devolução."""
        ped = estado.coletados.get("pedido")
        if estado.objetivo != "devolucao" or not ped or ped.get("status") != "cancelled":
            return None
        r = resultado_de(estado, "consultar_politica", temas=["arrependimento"])
        if r is None:
            return ferramenta("consultar_politica", temas=["arrependimento"])
        if r.estado != "ok":
            return self._erro(estado, r)
        return responder("reembolso_cancelado")

    def _i_motivo_cancelamento(self, estado: Estado) -> Acao:
        """"Por que foi cancelado?": a observação gravada no pedido já consultado; sem pedido, pede os dados."""
        if estado.coletados.get("pedido"):
            return responder("motivo_cancelamento")
        return self._i_status_pedido(estado)

    def _posvenda(self, estado: Estado) -> Acao:
        acao = self._reembolso_de_cancelado(estado)
        if acao:
            return acao
        for exclusao in (self._exclusao_garantia, self._avaria, self._devolucao_na_loja):
            acao = exclusao(estado)
            if acao:
                return acao
        dias = estado.slots.get("dias_desde_compra")
        if estado.objetivo == "defeito" and dias:
            acao = self._defeito_fora_do_prazo(estado, dias)
            if acao:
                return acao
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
        data_pedido = pedido.get("data_pedido")
        if intencao == "defeito" and data_pedido:  # o prazo conta da compra, e o sistema sabe a data do pedido
            dias_pedido = (config.hoje() - date.fromisoformat(data_pedido)).days
            if dias_pedido > int(regra["valor"]["prazo_dias"]):
                if resultado_de(estado, "consultar_politica", temas=["defeito"]) is None:
                    return ferramenta("consultar_politica", temas=["defeito"])  # a resposta cita o fabricante do manual
                return propor("defeito_apos_prazo", "atendente",
                              f"Cliente com defeito no pedido {pedido['pedido_id']}, feito depois do prazo de troca; "
                              "a equipe pode intermediar a garantia com o fabricante.")
        faltam = [c for c in regra["valor"]["dados_necessarios"]
                  if estado.declarado(c) is None and not (c == "data_compra" and data_pedido)]
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
        acao = self._exclusao_garantia(estado)
        if acao:
            return acao
        return self._info(estado, ["garantia"], "garantia_info", oferta="solicitacao")

    def _i_devolucao_frete(self, estado: Estado) -> Acao:
        return self._info(estado, ["arrependimento"], "devolucao_frete")

    def _i_rain_check(self, estado: Estado) -> Acao:
        return self._info(estado, ["promocoes"], "rain_check")

    def _i_rastreio_como(self, estado: Estado) -> Acao:
        return self._info(estado, ["rastreamento"], "rastreio_como")

    def _i_privacidade(self, estado: Estado) -> Acao:
        return self._info(estado, ["privacidade", "contato"], "privacidade")

    def _i_empresa_dados(self, estado: Estado) -> Acao:
        return self._info(estado, ["empresa"], "empresa_dados", foco=estado.slots.get("empresa_foco") or ["fundacao"])

    # --- informativos ----------------------------------------------------------------

    def _i_saudacao(self, estado: Estado) -> Acao:
        return self._info(estado, ["empresa", "horario"], "saudacao")

    def _i_identidade(self, estado: Estado) -> Acao:
        return self._info(estado, ["empresa"], "identidade")

    def _i_encerramento(self, estado: Estado) -> Acao:
        return responder("encerramento")

    def _i_confirmacao_solta(self, estado: Estado) -> Acao:
        """"sim" ou "não" sem pergunta pendente: resposta natural, nunca "não entendi"."""
        return responder("confirmacao_solta")

    def _i_pedido_instrucoes(self, estado: Estado) -> Acao:
        return responder("recusa_instrucoes")

    def _i_reembolso_prazo(self, estado: Estado) -> Acao:
        return self._info(estado, ["arrependimento"], "reembolso_prazo")

    def _i_previsao_entrega(self, estado: Estado) -> Acao:
        """"Quando chega?": usa o pedido já consultado; sem pedido, segue o fluxo de status (ou de frete, se há cidade)."""
        pedido = estado.coletados.get("pedido")
        if pedido:
            if pedido["status"] == "delivered" or not pedido.get("previsao_vencida"):
                return responder("previsao_entrega")
            return propor("previsao_entrega", "atendente",
                          f"Cliente perguntou quando o pedido {pedido['pedido_id']} chega e a previsao ja passou.",
                          oferta="previsao_vencida")
        if estado.slots.get("cidade") and not estado.slots.get("pedido_id"):
            return self._i_frete(estado)
        return self._i_status_pedido(estado)

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

    def _cidade_base(self, estado: Estado) -> str | None:
        r = resultado_de(estado, "consultar_politica", temas=["frete"])
        for sec in (r.dados["secoes"] if r is not None and r.estado == "ok" else []):
            for c in sec["condicoes"]:
                if c["chave"] == "frete.cidade_base":
                    return str(c["valor"])
        return None

    def _frete_por_cep(self, estado: Estado, cep: str) -> Acao:
        """Produto e CEP: estimativa (simulação) pela ferramenta única `estimar_frete`; o que faltar, pergunta."""
        acao, produto = self._produto(estado)
        if acao:
            return perguntar("frete_pedir_produto", "referencia_produto") if acao.resposta == "pedir_produto" else acao
        if produto["situacao_venda"] != "disponivel":
            return self._indisponivel(estado, produto)
        itens = [{"produto_id": produto["id"], "quantidade": 1}]
        r = resultado_de(estado, "estimar_frete", cep=cep)
        if r is None:
            return ferramenta("estimar_frete", itens=itens, cep=cep)
        if r.estado == "vazio" and r.motivo == "cep_inexistente":
            estado.coletados.pop("cep", None)
            return perguntar("frete_cep_nao_encontrado", "cep")
        if r.estado == "falha" and r.motivo == "cep_indisponivel":
            return responder("frete_cep_indisponivel")
        if r.estado != "ok":
            return self._erro(estado, r)
        if r.dados["situacao"] == "cidade_base":  # a regra da loja vale pelo preço do produto, antes do PIX
            return responder("frete_cidade_base")
        if r.dados["situacao"] == "cotacao_individual":
            return responder("frete_cotacao_individual", produto=produto["nome"])
        return responder("frete_estimado", produto=produto["nome"])

    def _frete_do_produto(self, estado: Estado, cidade: str) -> Acao | None:
        """Cidade e produto conhecidos (citado ou em foco): o frete sai do preço do produto, sem pedir o valor do pedido.
        Devolve None quando não há produto, e o fluxo antigo (cidade e valor do pedido) segue."""
        s = estado.slots
        if not (s.get("referencia") or s.get("produto_id") or estado.coletados.get("ultimo_produto")):
            return None
        acao, produto = self._produto(estado)
        if acao:
            # produto que não se resolve ("bateria acústica"): segue o fluxo da cidade, que cobre grande porte
            return acao if acao.tipo == "ferramenta" else None
        from ..politicas import manual

        base = str(manual.valor("frete.cidade_base"))  # sem consulta extra: o laço tem no máximo 3 passos
        estado.coletados["cidade"] = cidade
        uf = s.get("uf") or estado.coletados.get("uf")
        if normalizar(cidade) != normalizar(base):
            r = resultado_de(estado, "consultar_politica", temas=["frete"])
            if r is None:
                return ferramenta("consultar_politica", temas=["frete"])
            if r.estado != "ok":
                return self._erro(estado, r)
            grande = self._grande_porte(estado, f"{produto['nome']} {produto['categoria']}")
            if grande:
                return responder("frete_grande_porte", cidade=cidade, item=grande)
            estado.coletados["referencia"] = produto["id"]  # o CEP que vier agora usa este produto
            return perguntar("frete_outra_cidade", "cep", cidade=cidade, uf=uf, produto=produto["nome"])
        args = {"produto_id": produto["id"], "forma": "boleto", "cidade": cidade, **({"uf": uf} if uf else {})}
        c = resultado_de(estado, "calcular_condicoes", **args)
        if c is None:
            return ferramenta("calcular_condicoes", **args)
        if c.estado != "ok":
            return self._erro(estado, c)
        return responder("frete_produto", cidade=cidade)

    def _grande_porte(self, estado: Estado, extra: str = "") -> str | None:
        """Item de grande porte (5.2) citado pelo cliente, comparando as palavras da lista do manual com a mensagem."""
        from ..texto import radical, tokens

        r = resultado_de(estado, "consultar_politica", temas=["frete"])
        if r is None or r.estado != "ok":
            return None
        msg = {radical(t) for t in tokens(estado.slots.get("texto_limpo", "") + " " + extra)}
        for item in _condicao(r, "frete.grande_porte_cotacao_individual") or []:
            chaves = {radical(t) for t in tokens(item)}
            if chaves and chaves <= msg:
                return str(item)
        return None

    def _i_frete(self, estado: Estado) -> Acao:
        s = estado.slots
        cep = s.get("cep") or estado.coletados.get("cep")
        if s.get("modalidade") and not cep:  # "qual o prazo do PAC?": a modalidade tem prazo próprio no manual
            return self._info(estado, ["frete"], "frete_modalidade", modalidade=s["modalidade"])
        if cep:
            estado.coletados["cep"] = cep
            return self._frete_por_cep(estado, cep)
        cidade = s.get("cidade") or estado.coletados.get("cidade") or estado.coletados.get("cidade_cliente")
        valor = s.get("valor") or estado.coletados.get("valor_pedido")
        if cidade and not valor:
            acao = self._frete_do_produto(estado, cidade)
            if acao:
                return acao
        if not cidade and (s.get("referencia") or s.get("produto_id")):  # produto sem destino: pede o CEP
            estado.coletados["referencia"] = s.get("produto_id") or s["referencia"]
            return perguntar("frete_pedir_cep", "cep")
        if s.get("cidade"):
            estado.coletados["uf"] = s.get("uf")
        uf = estado.coletados.get("uf")
        if cidade:
            estado.coletados["cidade"] = cidade
            r = resultado_de(estado, "consultar_politica", temas=["frete"])
            if r is None:
                return ferramenta("consultar_politica", temas=["frete"])
            if r.estado != "ok":
                return self._erro(estado, r)
            base = self._cidade_base(estado)
            if base and normalizar(cidade) != normalizar(base):  # fora da base: a equipe calcula, sem pedir valor
                grande = self._grande_porte(estado)
                if grande:
                    return responder("frete_grande_porte", cidade=cidade, item=grande)
                return responder("frete_outra_cidade", cidade=cidade)
        if cidade and valor:
            estado.coletados["valor_pedido"] = valor
            r = resultado_de(estado, "calcular_condicoes", cidade=cidade)
            if r is None:  # com UF informada, a ferramenta compara cidade e UF: a cidade-base de outro estado não recebe a regra
                extra = {"uf": uf} if uf else {}
                return ferramenta("calcular_condicoes", valor=valor, forma="boleto", cidade=cidade, valor_pedido=valor,
                                  **extra)
            if r.estado != "ok":
                return self._erro(estado, r)
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
            return perguntar("pedir_categoria", "categoria", categorias=categorias_com_produto())
        r = busca_exata(estado, args)
        if r is None:
            return ferramenta("buscar_produtos", **args)
        if r.estado == "falha":
            return self._erro(estado, r)
        if r.estado != "ok":
            if set(args) == {"categoria"}:  # categoria sem produto à venda: diz isso e mostra o que há
                return responder("busca", sem_categoria=categorias_com_produto())
            return responder("busca")
        return self._aquecer_busca(estado, args, r)

    def _aquecer_busca(self, estado: Estado, args: dict[str, Any], r: Resultado) -> Acao:
        """Lead: qualifica uma busca ampla (uma pergunta, uma rodada por assunto) e, sabendo faixa ou nível, destaca
        uma opção com motivo verificável no dado. Cliente frustrado ou irritado só recebe a lista."""
        s = estado.slots
        itens, total = r.dados["itens"], r.dados["total_encontrado"]
        if estado.sentimento != "neutro" or len(itens) < 2:
            return responder("busca")
        faixa = args.get("preco_min") is not None or args.get("preco_max") is not None
        so_categoria = set(args) == {"categoria"}
        nivel, baixo = s.get("nivel"), bool(s.get("orcamento_baixo"))
        if (so_categoria and not nivel and not baixo and not estado.coletados.get("qualificada")
                and not s.get("secundaria")  # duas perguntas na mensagem: responde as duas, sem abrir uma terceira
                and not recusada(estado, f"qualificacao:{args['categoria']}")):
            estado.coletados["qualificacao"] = {"categoria": args["categoria"]}
            return perguntar("busca", "qualificacao", qualificar=True)
        if "termo" in args or not (faixa or nivel or baixo or s.get("qualificado")):
            return responder("busca")
        motivo, escolhido = None, None
        if nivel == "iniciante":
            extra = {**args, "termo": "iniciante", "limite": 1}  # o próprio catálogo diz "iniciantes" na descrição
            r2 = busca_exata(estado, extra)
            if r2 is None:
                return ferramenta("buscar_produtos", **extra)
            if r2.estado == "ok" and r2.dados["itens"][0]["id"] in {i["id"] for i in itens}:
                escolhido, motivo = r2.dados["itens"][0], "iniciante"
        if escolhido is None:
            promos = [i for i in itens if i["promocao"] and not i["promocao"].get("ambigua")]
            if promos:
                escolhido, motivo = max(promos, key=lambda i: i["promocao"]["percentual"]), "promocao"
            else:
                escolhido, motivo = itens[0], "menor_preco"
        estado.coletados["recomendado"] = escolhido["id"]
        recomendacao = {"id": escolhido["id"], "nome": escolhido["nome"], "motivo": motivo,
                        "orcamento": args.get("preco_max") is not None,
                        "percentual": (escolhido["promocao"] or {}).get("percentual")}
        oferta = not recusada(estado, f"condicoes:{escolhido['id']}")
        return responder("busca", recomendacao=recomendacao, oferta_condicoes=oferta, total=total)

    def _i_extremo_lista(self, estado: Estado) -> Acao:
        """"Qual o mais barato?" sobre a lista mostrada: nova consulta com a mesma busca, um item."""
        busca = estado.coletados.get("ultima_busca")
        if not busca or not busca.get("args"):
            if estado.coletados.get("ultimo_produto") and estado.slots.get("extremo") == "min":
                estado.slots["mais_barato"] = True  # "tem algo mais barato?" com um produto em foco
                return self._i_parecido(estado)
            return self._i_busca_produto(estado)
        extremo = estado.slots.get("extremo", "min")
        args = dict(busca["args"])
        args["limite"] = 1
        if extremo == "max":
            args["deslocamento"] = max(int(busca.get("total", 1)) - 1, 0)
        r = resultado_de(estado, "buscar_produtos", **args)
        if r is None:
            return ferramenta("buscar_produtos", **args)
        if r.estado != "ok":
            return self._erro(estado, r) if r.estado == "falha" else self._i_busca_produto(estado)
        estado.coletados["ultimo_produto"] = r.dados["itens"][0]["id"]
        return responder("extremo_lista", extremo=extremo)

    def _produto(self, estado: Estado) -> tuple[Acao | None, dict[str, Any] | None]:
        s = estado.slots
        ref = s.get("produto_id") or s.get("referencia") or estado.coletados.get("referencia")
        if ref is None and estado.aguardando == "escolha_produto" and estado.coletados.get("opcoes"):
            # "e em 12x" logo depois de uma lista de modelos parecidos: pede o modelo em uma frase, sem escolher por ele
            return perguntar("escolha_produto_curta", "escolha_produto"), None
        if ref is None and (s.get("compra") or estado.coletados.get("compra")) and not s.get("desconhecidas"):
            ref = estado.coletados.get("recomendado")  # "quero comprar" depois de uma sugestão da Lia
        # seguimento ("tá caro", "tem outro parecido?"): o produto em foco vale mesmo com palavras que o catálogo não conhece
        seguimento = estado.intencao in ("parecido", "objecao_preco", "vou_pensar", "extremo_lista", "frete")
        if ref is None and (seguimento or not s.get("desconhecidas")) and not s.get("tem_modelo"):
            # fala sem produto ("tem em estoque?", "quanto fica no pix?"): vale o produto em foco ou o primeiro da lista
            busca = estado.coletados.get("ultima_busca") or {}
            ref = estado.coletados.get("ultimo_produto") or (busca.get("ids") or [None])[0]
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

    def _i_parecido(self, estado: Estado) -> Acao:
        """"Tem outro parecido?": modelos da mesma categoria do produto em foco, em faixa próxima ou mais baratos."""
        acao, produto = self._produto(estado)
        if acao:
            return acao
        preco = produto["preco_centavos"]
        mais_barato = bool(estado.slots.get("mais_barato"))
        args = {"categoria": produto["categoria"], "preco_min": int(preco * 0.6),
                "preco_max": preco - 1 if mais_barato else int(preco * 1.4), "limite": 4}
        r = busca_exata(estado, args)
        if r is None:
            return ferramenta("buscar_produtos", **args)
        if r.estado == "falha":
            return self._erro(estado, r)
        return responder("parecidos", mais_barato=mais_barato)

    def _i_caracteristica(self, estado: Estado) -> Acao:
        """Característica técnica (captação, timbre, comparativo de som): o catálogo não traz ficha técnica."""
        return propor("sem_dado", "sem_dado", "Cliente perguntou uma caracteristica tecnica que o catalogo nao traz.")

    def _i_promocao(self, estado: Estado) -> Acao:
        args = {"termo": estado.slots["termo_promocao"]} if estado.slots.get("termo_promocao") else {}
        r = resultado_de(estado, "listar_promocoes", **args)
        if r is None:
            return ferramenta("listar_promocoes", **args)
        if r.estado == "falha":
            return self._erro(estado, r)
        return responder("promocoes", citado=estado.slots.get("desconto_citado"))

    def _i_endereco_pedido(self, estado: Estado) -> Acao:
        """Endereço de entrega é dado do cliente: não mostra e não responde com o endereço da loja."""
        return self._info(estado, ["contato"], "endereco_pedido_privado")

    def _i_cupom(self, estado: Estado) -> Acao:
        """Cupom: a loja só tem as promoções ativas e o desconto do PIX; qualquer código citado não existe."""
        return self._info(estado, ["pagamento"], "cupom_inexistente")

    def _i_tentativa_manipulacao(self, estado: Estado) -> Acao:
        return self._info(estado, ["pagamento"], "recusa_manipulacao")

    def _i_dado_de_terceiro(self, estado: Estado) -> Acao:
        return responder("recusa_dado_de_terceiro")

    def _soma_dos_dois(self, estado: Estado) -> Acao | None:
        """"Quanto fica os dois?": soma as condições dos dois últimos produtos citados (None se não houver dois)."""
        ids = estado.coletados.get("ultimos_produtos") or []
        if not estado.slots.get("os_dois") or len(ids) < 2 or estado.slots.get("referencia"):
            return None
        forma = estado.slots.get("forma") or estado.coletados.get("forma") or "pix"
        parcelas = estado.slots.get("parcelas") or estado.coletados.get("parcelas") or 1
        for pid in ids:
            args = {"produto_id": pid, "forma": forma, "parcelas": parcelas}
            r = resultado_de(estado, "calcular_condicoes", **args)
            if r is None:
                return ferramenta("calcular_condicoes", **args)
            if r.estado == "ambiguo":
                return propor("preco_promocao_conflitante", "duvida_politica",
                              f"Produto {pid} com mais de uma promocao ativa; cliente pediu a soma de dois produtos.")
            if r.estado != "ok":
                return self._erro(estado, r)
        return responder("soma_dois", ids=ids, forma=forma, parcelas=parcelas)

    def _i_preco_produto(self, estado: Estado) -> Acao:
        soma = self._soma_dos_dois(estado)
        if soma:
            return soma
        acao, produto = self._produto(estado)
        if acao:
            return acao
        if produto["situacao_venda"] != "disponivel":
            return self._indisponivel(estado, produto)
        forma = estado.slots.get("forma") or estado.coletados.get("forma") or "pix"
        parcelas = estado.slots.get("parcelas") or estado.coletados.get("parcelas") or 1
        args = {"produto_id": produto["id"], "forma": forma, "parcelas": parcelas}
        compra = bool(estado.slots.get("compra") or estado.coletados.get("compra"))
        # valor: o frete grátis na cidade-base entra como condição que ajuda, uma vez por conversa e só se o cliente
        # está sem frustração; a cidade vem do manual, e a ferramenta diz se o frete é grátis para este produto
        if "frete_gratis" not in estado.valores_citados:
            from ..politicas import manual

            args["cidade"] = str(manual.valor("frete.cidade_base"))
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
        extra: dict[str, Any] = {}
        if estado.slots.get("quantidade"):
            extra["quantidade"] = estado.slots["quantidade"]
        if estado.slots.get("pergunta_promocao"):
            extra["pergunta_promocao"] = True
        nome_promo = estado.slots.get("promo_nome")
        if nome_promo or estado.slots.get("desconto_citado"):
            from ..texto import radical, tokens

            promo = produto.get("promocao") or {}
            chaves = [radical(t) for t in tokens(nome_promo or "")]
            desc = normalizar(str(promo.get("descricao") or ""))
            ativa = bool(promo) and not promo.get("ambigua") and (not chaves or all(c in desc for c in chaves))
            if nome_promo and not ativa:
                extra["promo_inativa"] = nome_promo
            if estado.slots.get("desconto_citado") and promo.get("percentual") != estado.slots["desconto_citado"]:
                extra["desconto_citado"] = estado.slots["desconto_citado"]
        if compra:
            extra["compra"] = True  # o próximo passo é o botão de carrinho, não outra pergunta
        if (r.dados.get("frete") or {}).get("situacao") == "gratis" and estado.sentimento == "neutro":
            extra["valor_frete"] = args["cidade"]  # o fato é o mesmo para qualquer humor; só a oferta some
        if forma != "credito" and not compra and not recusada(estado, f"parcelas:{produto['id']}"):
            extra["oferta_parcelas"] = True  # próximo passo curto, de sim ou não: as parcelas do produto em foco
        return responder("preco", **extra)

    def _i_parcelamento_produto(self, estado: Estado) -> Acao:
        """O "sim" à oferta de parcelas: o parcelamento máximo do produto em foco, em duas consultas à ferramenta."""
        pid = estado.coletados.get("ultimo_produto")
        if not pid:
            return responder("nao_entendi")
        base = {"produto_id": pid, "forma": "credito"}
        r1 = resultado_de(estado, "calcular_condicoes", parcelas=1, **base)
        if r1 is None:
            return ferramenta("calcular_condicoes", parcelas=1, **base)
        if r1.estado != "ok":
            return self._erro(estado, r1)
        # a maior quantidade de parcelas que passa nas duas leituras da parcela mínima do manual, nunca 12x inválido
        from .. import dinheiro

        final, minimo = r1.dados["final_centavos"], r1.dados["minimo_tabela_centavos"]
        n = max([k for k in range(1, r1.dados["parcelas_max"] + 1) if dinheiro.dividir(final, k) >= minimo] or [1])
        if n == 1:
            return responder("preco")
        r2 = resultado_de(estado, "calcular_condicoes", parcelas=n, **base)
        if r2 is None:
            return ferramenta("calcular_condicoes", parcelas=n, **base)
        if r2.estado != "ok":
            return self._erro(estado, r2)
        if r2.dados.get("permitido") != "sim":
            return propor("preco", "duvida_politica",
                          f"Cliente pediu o parcelamento do produto {pid}; as duas leituras da parcela minima divergem.")
        return responder("preco")

    def _i_objecao_preco(self, estado: Estado) -> Acao:
        """"Tá caro": opção mais barata da categoria, promoção ativa ou parcelamento. Nunca desconto inventado."""
        acao, produto = self._produto(estado)
        if acao:
            return acao
        if produto["situacao_venda"] != "disponivel":
            return self._indisponivel(estado, produto)
        if estado.sentimento != "neutro":
            return responder("objecao_preco", sem_oferta=True)  # irritado ou frustrado não recebe oferta
        args = {"categoria": produto["categoria"], "preco_max": produto["preco_centavos"] - 1, "limite": 1}
        r = busca_exata(estado, args)
        if r is None:
            return ferramenta("buscar_produtos", **args)
        if r.estado == "falha":
            return self._erro(estado, r)
        promo = produto.get("promocao") or {}
        parcelas = not recusada(estado, f"parcelas:{produto['id']}")
        return responder("objecao_preco", oferta_parcelas=parcelas,
                         mais_barato=r.dados["itens"][0] if r.estado == "ok" else None,
                         percentual=None if promo.get("ambigua") else promo.get("percentual"),
                         produto=produto["nome"], categoria=produto["categoria"])

    def _i_vou_pensar(self, estado: Estado) -> Acao:
        """"Vou pensar": respeito, o link do produto em foco e nenhuma insistência."""
        ref = estado.coletados.get("ultimo_produto")
        if ref is None:
            return responder("vou_pensar")
        r = resultado_de(estado, "ver_produto", referencia=ref)
        if r is None:
            return ferramenta("ver_produto", referencia=ref)
        if r.estado != "ok":
            return responder("vou_pensar")
        return responder("vou_pensar", produto=r.dados["nome"])

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
        protocolo = estado.chamados_assunto.get(estado.ultimo_assunto or "geral")
        if protocolo and resultado_de(estado, "registrar_encaminhamento") is None:  # mesmo assunto: não abre outro
            if resultado_de(estado, "consultar_politica", temas=["horario", "contato"]) is None:
                return ferramenta("consultar_politica", temas=["horario", "contato"])
            return responder("atendente_ja_registrado", protocolo=protocolo)
        resumo = "Cliente pediu atendimento humano."
        if estado.pendentes:
            resumo += f" Assunto anterior: {estado.pendentes[-1]['objetivo']}."
        pedido = estado.coletados.get("pedido")
        if pedido:
            resumo += f" Pedido consultado: {pedido['pedido_id']}."
        return self._registrar(estado, "atendente", resumo)

    def _i_comparar(self, estado: Estado) -> Acao:
        """Dois produtos nomeados: preço e ficha do catálogo dos dois, sem escolher "o melhor"."""
        dados = []
        for ref in estado.slots["comparar_refs"]:
            r = resultado_de(estado, "ver_produto", referencia=ref)
            if r is None:
                return ferramenta("ver_produto", referencia=ref)
            if r.estado == "ok":
                dados.append(r.dados)
                continue
            if r.estado in ("vazio", "ambiguo"):
                return perguntar("produto_nao_encontrado", "referencia_produto")
            return self._erro(estado, r)
        estado.coletados["ultimo_produto"] = dados[-1]["id"]
        return responder("comparacao")

    def _i_ingles(self, estado: Estado) -> Acao:
        return responder("so_portugues", tema=estado.slots.get("tema_ingles"))

    def _i_desconhecido(self, estado: Estado) -> Acao:
        if estado.sentimento != "neutro":  # insulto ou queixa sem pedido concreto: acolhe e oferece atendente
            return propor("acolhimento", "atendente",
                          "Cliente demonstrou insatisfacao e aceitou atendimento humano.")
        if estado.incompreensoes >= 1:
            return propor("nao_entendi_de_novo", "sem_dado",
                          "Cliente fez uma pergunta que o assistente nao conseguiu entender.")
        return responder("nao_entendi")
