"""App FastAPI do site. Subir com: uvicorn emporio.web.app:app

Variáveis: EMPORIO_MODELO (modelo do Ollama para a redação; vazio = só regras), EMPORIO_DECISOR (padrão
regras), EMPORIO_SEGREDO (assinatura do cookie; sem ele, um segredo novo a cada processo),
EMPORIO_COOKIE_SEGURO=1 (cookie só por HTTPS).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import threading
import uuid
from pathlib import Path
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.exceptions import HTTPException as ErroHTTP

from .. import config
from ..agente import llm
from ..agente.fabrica import criar_agente
from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.pedido_demo import PREFIXO as PREFIXO_PEDIDO, achar_numero, consultar_pedido_demo
from ..ferramentas.pedidos import consultar_pedido
from ..ferramentas.politica import consultar_politica
from ..ferramentas.produtos import buscar_produtos, ver_produto
from ..ferramentas.promocoes import listar_promocoes
from ..texto import radical, tokens
from ..politicas.manual import carregar_manual, fato
from . import apresentacao, carrinho, compra, conteudo, contato, entradas, fotos, home, navegacao
from .limite import LimiteRastreio

POR_PAGINA = 12  # produtos por página do catálogo; o limite de 5 itens é do chat, não do site

log = logging.getLogger("emporio.web")

AQUI = Path(__file__).resolve().parent

_HASH_SW: dict[str, Any] = {}


def _estaticos() -> list[str]:
    """Estáticos que vão para o pré-cache (licenças ficam de fora)."""
    return sorted("/static/" + p.relative_to(AQUI / "static").as_posix()
                  for p in (AQUI / "static").rglob("*") if p.is_file() and p.suffix != ".txt")


def versao_sw() -> str:
    """Hash do conteúdo de sw.js e dos estáticos do pré-cache: mudou um arquivo, muda a versão do cache."""
    caminhos = [AQUI / "sw.js"] + [AQUI / p[1:] for p in _estaticos()]
    assinatura = tuple((c.stat().st_mtime_ns, c.stat().st_size) for c in caminhos)  # evita reler tudo a cada pedido
    guardado = _HASH_SW.get("assinatura")
    if guardado == (tuple(caminhos), assinatura):
        return _HASH_SW["hash"]
    h = hashlib.sha256()
    for caminho in caminhos:
        h.update(str(caminho.relative_to(AQUI)).encode())
        h.update(caminho.read_bytes())
    _HASH_SW.update(assinatura=(tuple(caminhos), assinatura), hash=h.hexdigest()[:12])
    return _HASH_SW["hash"]


SEM_SESSAO = ("/static", "/saude", "/sw.js", "/manifest.webmanifest", "/offline", "/favicon.ico")
COOKIE = "emporio_sessao"
MAX_MENSAGEM = 500  # limite de entrada do sistema, não é regra de loja
MSG_FALHA = "Não conseguimos consultar isso agora. Tente de novo em instantes."
ERROS_PAGINA = {
    403: ("Pedido não aceito", "Por segurança, só aceitamos formulários enviados pelas páginas desta loja. "
                               "Volte ao início e tente de novo."),
    404: ("Página não encontrada", "Não achamos o endereço que você abriu. Veja o catálogo ou volte ao início."),
    405: ("Método não permitido", "Esta página não aceita essa ação. Volte ao início e tente de novo."),
    422: ("Não entendemos esse pedido", "Algum dado veio em formato que não aceitamos. Volte à página anterior, confira o que foi preenchido e tente de novo."),
    500: ("Algo deu errado", "Tivemos um problema do nosso lado, e ele já ficou registrado. Tente de novo em instantes ou volte ao início."),
}
ERRO_PADRAO = ("Não foi possível concluir", "Não conseguimos atender esse pedido agora. Volte ao início e tente de novo.")


def _promocoes() -> dict[int, dict[str, Any]]:
    r = listar_promocoes()
    if r.estado != "ok":
        return {}
    return {p["produto_id"]: p for p in r.dados["promocoes"]}


def _condicoes_de_pagamento(produto_id: int) -> dict[str, Any]:
    """À vista por forma e o maior parcelamento que a ferramenta aprova; nada é calculado aqui."""
    linhas = []
    for forma in ("pix", "debito", "boleto"):
        r = calcular_condicoes(produto_id=produto_id, forma=forma)
        if r.estado == "ok":
            linhas.append({"forma": apresentacao.ROTULO_FORMA[forma], "valor": r.dados["final_centavos"]})
    parcelamento = None
    f = fato("pagamento.credito_parcelas_max")
    maximo = int(f.valor) if f else 1
    for n in range(maximo, 0, -1):
        r = calcular_condicoes(produto_id=produto_id, forma="credito", parcelas=n)
        if r.estado == "ok" and r.dados["permitido"] == "sim":
            sem_juros = fato("pagamento.credito_sem_juros")
            parcelamento = {"parcelas": n, "parcela": r.dados["parcela_centavos"], "total": r.dados["final_centavos"],
                            "sem_juros": bool(sem_juros and sem_juros.valor)}
            break
    return {"a_vista": linhas, "parcelamento": parcelamento}


def _itens_no_carrinho(request: Request) -> int:
    """Quantidade de unidades no carrinho da sessão, para o cabeçalho; qualquer falha vira zero."""
    try:
        conversa = getattr(request.state, "conversa_id", None)
        return carrinho.quantidade_total(conversa) if conversa else 0
    except Exception:  # noqa: BLE001 - o cabeçalho não pode derrubar a página
        return 0


def _linhas_carrinho(sessao: str) -> list[dict[str, Any]]:
    promos = _promocoes()
    linhas = []
    for i in carrinho.listar(sessao):
        r = ver_produto(referencia=i["produto_id"])
        if r.estado != "ok":
            linhas.append({"p": None, "produto_id": i["produto_id"], "quantidade": i["quantidade"]})
            continue
        item = home.com_foto(apresentacao.preparar_item(r.dados, promos), r.dados["categoria"])
        unitario = item["final"] if item["final"] is not None else item["original"]
        linhas.append({"p": item, "produto_id": i["produto_id"], "quantidade": i["quantidade"],
                       "subtotal": unitario * i["quantidade"] if item["pode_comprar"] else None})
    return linhas


def criar_app(agente: Any = None) -> FastAPI:
    os.environ.setdefault("EMPORIO_DECISOR", "regras")
    segredo = os.environ.get("EMPORIO_SEGREDO") or secrets.token_hex(32)
    assinador = URLSafeSerializer(segredo, salt="emporio-sessao")
    seguro = os.environ.get("EMPORIO_COOKIE_SEGURO") == "1"
    trava_agente = threading.Lock()  # o agente guarda telemetria em memória: uma conversa por vez no processo
    try:
        espera = float(os.environ.get("EMPORIO_ESPERA_AGENTE", "30"))  # segundos que o chat espera a vez
    except ValueError:
        espera = 30.0
    trava_criacao = threading.Lock()

    app = FastAPI(title="Lia", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.agente = agente  # criado na primeira conversa, uma vez por processo
    app.state.limite_rastreio = LimiteRastreio()
    assinador_contato = URLSafeSerializer(segredo, salt="emporio-contato")
    app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
    modelos = Jinja2Templates(directory=AQUI / "templates")
    modelos.env.globals.update(loja=apresentacao.loja, categorias=navegacao.listar_categorias,
                               situacao_loja=apresentacao.situacao_loja, cores=apresentacao.cores, ilustracao=apresentacao.ilustracao,
                               menu_categorias=home.categorias, formas_pagamento=apresentacao.formas_de_pagamento,
                               canais=contato.canais, faixa_contato=contato.faixa, itens_no_carrinho=_itens_no_carrinho,
                               prefixo_pedido=PREFIXO_PEDIDO,
                               rotulo_forma=apresentacao.ROTULO_FORMA, parcelas_max=compra.parcelas_max)
    modelos.env.filters.update(brl=apresentacao.brl, data_br=apresentacao.data_br,
                               pagamento=apresentacao.forma_pagamento, quebras=apresentacao.quebras,
                               politica=apresentacao.blocos_politica, hora=apresentacao.hora_br)

    def obter_agente() -> Any:
        with trava_criacao:
            if app.state.agente is None:
                app.state.agente = criar_agente(llm.modelo_padrao())
            return app.state.agente

    def pagina(request: Request, nome: str, status: int = 200, **contexto: Any) -> HTMLResponse:
        return modelos.TemplateResponse(request, nome, contexto, status_code=status)

    def pagina_de_erro(request: Request, status: int) -> HTMLResponse:
        titulo, texto = ERROS_PAGINA.get(status, ERRO_PADRAO)
        return pagina(request, "mensagem.html", status, titulo=titulo, texto=texto, titulo_pagina=titulo)

    @app.exception_handler(ErroHTTP)
    async def erro_http(request: Request, exc: ErroHTTP):
        return pagina_de_erro(request, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def erro_validacao(request: Request, exc: RequestValidationError):
        return pagina_de_erro(request, 422)

    @app.exception_handler(Exception)
    async def erro_interno(request: Request, exc: Exception):
        log.error("erro interno em %s %s", request.method, request.url.path, exc_info=exc)
        return pagina_de_erro(request, 500)

    def origem_valida(request: Request) -> bool:
        """Formulário vindo de outra origem é recusado. Sem cabeçalho Origin (cliente que não é navegador) passa."""
        origem = request.headers.get("origin")
        if origem is None:
            return True
        return origem != "null" and urlsplit(origem).netloc == request.headers.get("host", "")

    @app.middleware("http")
    async def sessao(request: Request, call_next):
        if request.url.path.startswith(SEM_SESSAO):
            return await call_next(request)
        conversa = None
        bruto = request.cookies.get(COOKIE)
        if bruto:
            try:
                valor = assinador.loads(bruto)
                conversa = valor if isinstance(valor, str) and valor.startswith("web-") else None
            except BadSignature:
                conversa = None
        novo = conversa is None
        if novo:
            conversa = "web-" + uuid.uuid4().hex
        request.state.conversa_id = conversa
        if request.method not in ("GET", "HEAD", "OPTIONS") and not origem_valida(request):
            return pagina_de_erro(request, 403)
        resposta = await call_next(request)
        if novo:  # POST de outra origem já foi recusado acima, sem tocar no cookie do visitante
            resposta.set_cookie(COOKIE, assinador.dumps(conversa), httponly=True, samesite="lax", secure=seguro,
                                max_age=60 * 60 * 24 * 30)
        return resposta

    @app.get("/saude")
    def saude() -> JSONResponse:
        banco_ok = buscar_produtos(limite=1).estado == "ok"
        modelo = llm.modelo_padrao()
        if not modelo:
            estado_modelo = "nao_configurado"
        else:
            try:
                llm.conferir_modelo(modelo)
                estado_modelo = "ok"
            except llm.ErroModelo as erro:
                estado_modelo = "indisponivel"
                log.info("modelo indisponivel: %s", erro)
        corpo = {"status": "ok" if banco_ok else "falha", "banco": "ok" if banco_ok else "indisponivel",
                 "modelo": estado_modelo, "nome_modelo": modelo}
        return JSONResponse(corpo, status_code=200 if banco_ok else 503)

    @app.get("/manifest.webmanifest")
    def manifesto() -> JSONResponse:
        info = apresentacao.loja()
        c = apresentacao.cores()
        corpo = {
            "name": info["nome"], "short_name": info["nome"].split(" ", 1)[0],
            "description": "Catálogo, condições e a assistente Lia, com os dados da loja.",
            "lang": "pt-BR", "dir": "ltr", "start_url": "/", "scope": "/", "id": "/", "display": "standalone",
            "background_color": c.get("creme"), "theme_color": c.get("palco"), "categories": ["shopping", "music"],
            "icons": [
                {"src": "/static/icones/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/static/icones/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "/static/icones/maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
                {"src": "/static/icones/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        }
        return JSONResponse(corpo, media_type="application/manifest+json")

    @app.get("/sw.js")
    def service_worker() -> Response:
        estaticos = _estaticos()
        corpo = ((AQUI / "sw.js").read_text(encoding="utf-8")
                 .replace('"/*VERSAO*/"', json.dumps(versao_sw()))
                 .replace("/*ESTATICOS*/[]", json.dumps(estaticos, indent=2)))
        # Service-Worker-Allowed deixa o escopo na raiz; sem cache para a atualização chegar na hora
        return Response(corpo, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache, max-age=0", "Service-Worker-Allowed": "/"})

    @app.get("/offline", response_class=HTMLResponse)
    def offline(request: Request):
        return pagina(request, "offline.html")

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request):
        destaques = home.destaques()
        return pagina(request, "inicio.html", destaques=destaques, grade=home.grade({d["id"] for d in destaques}),
                      categorias_home=home.categorias(), faq=conteudo.perguntas(somente_principais=True),
                      abertura=fotos.foto_de_abertura(),
                      descricao="Violões, guitarras, baixos, teclados, baterias e ukuleles, com preço claro e as condições "
                                "de pagamento de cada produto.")

    @app.get("/favicon.ico")
    def favicon() -> RedirectResponse:
        return RedirectResponse("/static/icones/icon-192.png", status_code=307)

    @app.get("/perguntas-frequentes", response_class=HTMLResponse)
    def perguntas_frequentes(request: Request):
        return pagina(request, "faq.html", grupos=conteudo.faq_agrupada(), titulo_pagina="Perguntas frequentes",
                      descricao="Pagamento, entrega, acompanhamento do pedido, trocas e garantia.")

    @app.get("/privacidade", response_class=HTMLResponse)
    def privacidade(request: Request):
        return pagina(request, "privacidade.html", titulo_pagina="Privacidade e cookies", manual=conteudo.privacidade_manual(),
                      cookie=COOKIE, dias_cookie=60 * 60 * 24 * 30 // 86400, cookie_seguro=seguro,
                      descricao="Quais dados guardamos, por que usamos um cookie e como falar com a loja sobre eles.")

    @app.get("/creditos", response_class=HTMLResponse)
    def creditos(request: Request):
        return pagina(request, "creditos.html", titulo_pagina="Créditos das imagens",
                      fotos=sorted(fotos.creditos().values(), key=lambda f: f["arquivo"]),
                      descricao="Autor, licença e origem de cada fotografia usada na loja.")

    def pagina_contato(request: Request, valores: dict[str, str] | None = None, erros: dict[str, str] | None = None,
                       status: int = 200):
        return pagina(request, "fale_conosco.html", status, valores=valores or {}, erros=erros or {},
                      titulo_pagina="Fale conosco", protocolo=None, limites=contato.LIMITES,
                      descricao="Converse, ligue, escreva ou deixe uma mensagem para a loja.")

    @app.get("/fale-conosco", response_class=HTMLResponse)
    def fale_conosco(request: Request, enviado: str = ""):
        if enviado:  # confirmação depois do redirecionamento; o protocolo vem assinado, nunca da URL pura
            try:
                protocolo = assinador_contato.loads(enviado)
            except BadSignature:
                protocolo = None
            if isinstance(protocolo, str):
                return pagina(request, "fale_conosco.html", titulo_pagina="Fale conosco", valores={}, erros={},
                              protocolo=protocolo, limites=contato.LIMITES, descricao="")
        return pagina_contato(request)

    @app.post("/fale-conosco", response_class=HTMLResponse)
    def fale_conosco_enviar(request: Request, assunto: str = Form(""), mensagem: str = Form(""),
                            contato_retorno: str = Form(""), site: str = Form("")):
        valores = {"assunto": assunto, "mensagem": mensagem, "contato": contato_retorno}
        if site.strip():  # campo isca: pessoa não vê nem preenche; descarta sem gravar e sem dar pista
            return RedirectResponse("/fale-conosco?enviado=" + assinador_contato.dumps(""), status_code=303)
        erros = contato.validar(valores)
        if erros:
            return pagina_contato(request, valores, erros, 422)
        try:
            protocolo = contato.gravar(valores)
        except Exception:  # noqa: BLE001 - o formulário não pode derrubar o site, e o texto do cliente é mantido
            return pagina_contato(request, valores, {"geral": "Não conseguimos registrar agora. Tente de novo em instantes."}, 502)
        return RedirectResponse("/fale-conosco?enviado=" + assinador_contato.dumps(protocolo), status_code=303)

    def _categoria_canonica(texto: str) -> str:
        """Slug da Lia ou digitação livre ('ukulele', 'VIOLAO') vira o nome da categoria; sem par, fica como veio."""
        consulta = {radical(t) for t in tokens(texto)}
        if not consulta:
            return texto
        achadas = [n for n in navegacao.listar_categorias() if consulta <= {radical(t) for t in tokens(n)}]
        exata = [n for n in achadas if consulta == {radical(t) for t in tokens(n)}]
        escolha = exata or achadas
        return escolha[0] if len(escolha) == 1 else texto

    @app.get("/catalogo", response_class=HTMLResponse)
    def catalogo(request: Request, categoria: str = "", termo: str = "", preco_min: str = "",
                 preco_max: str = "", todos: str = "", pagina_: str = Query("1", alias="pagina")):
        numero_pagina = entradas.inteiro(pagina_)
        if not numero_pagina:
            return pagina_de_erro(request, 422)
        filtros = {"categoria": _categoria_canonica(categoria.strip()), "termo": termo.strip(), "preco_min": preco_min.strip(),
                   "preco_max": preco_max.strip(), "todos": bool(todos)}
        erro = None
        itens: list[dict[str, Any]] = []
        total = 0
        paginas = 1
        busca_vazia = False
        minimo, erro_min = entradas.preco_em_centavos(filtros["preco_min"])
        maximo, erro_max = entradas.preco_em_centavos(filtros["preco_max"])
        erro = erro_min or erro_max
        if erro is None and filtros["termo"] and not any(c.isalnum() for c in filtros["termo"]):
            erro = "Digite pelo menos uma letra ou um número para buscar."
        if erro is None:
            r = buscar_produtos(categoria=filtros["categoria"] or None, termo=filtros["termo"] or None,
                                preco_min=minimo, preco_max=maximo, incluir_indisponiveis=filtros["todos"],
                                limite=POR_PAGINA, deslocamento=(numero_pagina - 1) * POR_PAGINA, para_site=True)
            if r.estado == "ok":
                promos = _promocoes()
                itens = [home.com_categoria(apresentacao.preparar_item(i, promos)) for i in r.dados["itens"]]
                total = r.dados["total_encontrado"]
                paginas = max(1, -(-total // POR_PAGINA))
                if not itens:  # página além do fim: volta à última, sem página vazia
                    return RedirectResponse(str(request.url.include_query_params(pagina=paginas)), status_code=303)
            elif r.estado == "vazio":
                if r.motivo == "categoria_inexistente":
                    erro = "Não temos essa categoria no catálogo."
                else:
                    busca_vazia = True
            elif r.motivo == "faixa_incoerente":
                erro = "A faixa de preço está incoerente: o mínimo passa do máximo."
            else:
                erro = MSG_FALHA
        consulta = {k: v for k, v in (("categoria", filtros["categoria"]), ("termo", filtros["termo"]),
                                      ("preco_min", filtros["preco_min"]), ("preco_max", filtros["preco_max"]),
                                      ("todos", "1" if filtros["todos"] else "")) if v}
        titulo = filtros["categoria"] or ("Resultados da busca" if filtros["termo"] else "Catálogo")
        return pagina(request, "catalogo.html", itens=itens, total=total, erro=erro, filtros=filtros,
                      pagina_atual=numero_pagina, paginas=paginas, busca_vazia=busca_vazia,
                      nomes_categorias=[c["nome"] for c in home.categorias()], por_pagina=POR_PAGINA, consulta=consulta,
                      titulo_pagina=titulo, descricao="Instrumentos musicais com preço e condição de pagamento.")

    @app.get("/produto/{produto_id}", response_class=HTMLResponse)
    def produto(request: Request, produto_id: str):
        numero = entradas.inteiro(produto_id)
        if numero is None:
            return pagina_de_erro(request, 404)
        produto_id = numero
        r = ver_produto(referencia=produto_id)
        if r.estado == "vazio":
            return pagina(request, "mensagem.html", 404, titulo="Produto não encontrado",
                          texto="Não achamos esse produto. Veja o catálogo ou pergunte à Lia.")
        if r.estado != "ok":
            return pagina(request, "mensagem.html", 502, titulo="Produto indisponível no momento", texto=MSG_FALHA)
        item = home.com_foto(apresentacao.preparar_item(r.dados, _promocoes()), r.dados["categoria"])
        condicoes = _condicoes_de_pagamento(produto_id) if item["pode_comprar"] else None
        return pagina(request, "produto.html", p=item, categoria=r.dados["categoria"], descricao_produto=r.dados["descricao"],
                      condicoes=condicoes, titulo_pagina=item["nome"], descricao=(r.dados["descricao"] or "")[:155],
                      imagem=(item["foto"] or {}).get("src"))

    @app.get("/politicas", response_class=HTMLResponse)
    def politicas(request: Request):
        temas = conteudo.politicas()
        if not temas:
            return pagina(request, "mensagem.html", 502, titulo="Políticas indisponíveis no momento", texto=MSG_FALHA)
        return pagina(request, "politicas.html", temas=temas, titulo_pagina="Políticas da Loja",
                      descricao="Pagamento, frete e entrega, trocas e devoluções, promoções e garantia.")

    # ---- compra de demonstração (incremento 1) ----------------------------------------------------

    def pagina_carrinho(request: Request, aviso: str | None = None, status: int = 200) -> HTMLResponse:
        linhas = _linhas_carrinho(request.state.conversa_id)
        return pagina(request, "carrinho.html", status, linhas=linhas, aviso=aviso, max_por_item=carrinho.MAX_POR_ITEM,
                      total_produtos=sum(l["subtotal"] for l in linhas if l.get("subtotal") is not None),
                      titulo_pagina="Carrinho")

    @app.get("/carrinho", response_class=HTMLResponse)
    def ver_carrinho(request: Request):
        return pagina_carrinho(request)

    def dados_do_carrinho(request: Request, produto_id: str, quantidade: str | None = None):
        """Produto e quantidade já validados; None e a resposta de erro quando algum não é um inteiro seguro."""
        produto = entradas.inteiro(produto_id)
        if produto is None:
            return None, None, pagina_carrinho(request, "Não entendemos qual produto você quer.", 422)
        if quantidade is None:
            return produto, None, None
        n = entradas.inteiro(quantidade)
        if n is None:
            return produto, None, pagina_carrinho(
                request, f"A quantidade por item vai de {carrinho.MIN_POR_ITEM} a {carrinho.MAX_POR_ITEM}.", 422)
        return produto, n, None

    @app.post("/carrinho/adicionar")
    def carrinho_adicionar(request: Request, produto_id: str = Form(""), quantidade: str = Form("1")):
        produto_id, quantidade, erro = dados_do_carrinho(request, produto_id, quantidade)
        if erro is not None:
            return erro
        try:
            carrinho.adicionar(request.state.conversa_id, produto_id, quantidade)
        except carrinho.RecusaCarrinho as recusa:
            return pagina_carrinho(request, str(recusa), 422)
        return RedirectResponse("/carrinho", status_code=303)

    @app.post("/carrinho/alterar")
    def carrinho_alterar(request: Request, produto_id: str = Form(""), quantidade: str = Form("")):
        produto_id, quantidade, erro = dados_do_carrinho(request, produto_id, quantidade)
        if erro is not None:
            return erro
        try:
            carrinho.definir_quantidade(request.state.conversa_id, produto_id, quantidade)
        except carrinho.RecusaCarrinho as recusa:
            return pagina_carrinho(request, str(recusa), 422)
        return RedirectResponse("/carrinho", status_code=303)

    @app.post("/carrinho/remover")
    def carrinho_remover(request: Request, produto_id: str = Form("")):
        produto_id, _, erro = dados_do_carrinho(request, produto_id)
        if erro is not None:
            return erro
        carrinho.remover(request.state.conversa_id, produto_id)
        return RedirectResponse("/carrinho", status_code=303)

    def pagina_checkout(request: Request, forma: str, parcelas: str, cep: str, aviso: str | None = None,
                        status: int = 200) -> HTMLResponse:
        c = compra.calcular(request.state.conversa_id, forma, parcelas, cep)
        if request.headers.get("HX-Request") == "true" and request.headers.get("HX-Boosted") != "true":
            return pagina(request, "_checkout_dinamico.html", status, c=c, formas=compra.FORMAS, oob=True)
        return pagina(request, "checkout.html", status, c=c, aviso=aviso, formas=compra.FORMAS)

    @app.get("/checkout", response_class=HTMLResponse)
    def ver_checkout(request: Request, forma: str = "pix", parcelas: str = "1", cep: str = ""):
        return pagina_checkout(request, forma, parcelas, cep)

    @app.post("/checkout", response_class=HTMLResponse)
    def finalizar_checkout(request: Request, forma: str = Form("pix"), parcelas: str = Form("1"),
                           cep: str = Form(""), total_visto: str = Form("")):
        sessao = request.state.conversa_id
        atual = compra.calcular(sessao, forma, parcelas, cep)
        if total_visto != str(atual["total"]):  # o cliente mudou algo sem atualizar os valores
            return pagina_checkout(request, forma, parcelas, cep,
                                   "Os valores mudaram desde a última conferência. Confira o total e finalize de novo.",
                                   409)
        try:
            numero = compra.finalizar(sessao, forma, parcelas, cep)
        except compra.CompraRecusada:
            return pagina_checkout(request, forma, parcelas, cep, None, 422)
        return RedirectResponse(f"/pedido/{numero}", status_code=303)

    @app.get("/pedido/{numero}", response_class=HTMLResponse)
    def pedido_demo(request: Request, numero: str):
        achado = achar_numero(numero)
        r = consultar_pedido_demo(numero=achado, conversa_id=request.state.conversa_id) if achado else None
        if r is None or r.estado == "negado":
            return pagina(request, "mensagem.html", 404, titulo="Pedido não encontrado",
                          texto="Não achamos esse pedido neste navegador. Pedido feito aqui no site só abre no "
                                "navegador em que foi feito.")
        if r.estado != "ok":
            return pagina(request, "mensagem.html", 502, titulo="Pedido indisponível no momento", texto=MSG_FALHA)
        return pagina(request, "pedido_demo.html", d=r.dados)

    @app.get("/rastreio", response_class=HTMLResponse)
    def rastreio_form(request: Request):
        return pagina(request, "rastreio.html", resultado=None, aviso=None, pedido="")

    @app.post("/rastreio", response_class=HTMLResponse)
    def rastreio(request: Request, pedido: str = Form(""), final_telefone: str = Form("")):
        pedido, final_telefone = pedido.strip(), final_telefone.strip()
        limite = app.state.limite_rastreio
        ip = request.client.host if request.client else "?"
        sessao_ = request.state.conversa_id
        espera = limite.segundos_para_liberar(sessao_, pedido, ip)
        if espera is not None:  # bloqueado: nada é consultado, nem com o dado certo, e a mensagem não revela o pedido
            minutos = -(-espera // 60)
            libera = apresentacao.hora_br((config.agora() + timedelta(seconds=espera)).strftime("%H:%M"))
            return pagina(request, "rastreio.html", 429, resultado=None, pedido="", aviso=None,
                          bloqueio=f"Por segurança, a consulta fica bloqueada depois de várias tentativas sem sucesso. "
                                   f"Ela será liberada de novo às {libera} (em cerca de {minutos} minutos).")
        negado = lambda: limite.registrar_falha(sessao_, pedido, ip)  # noqa: E731
        if pedido.upper().startswith(PREFIXO_PEDIDO):  # pedido feito no site: identificado pela sessão, sem telefone
            achado = achar_numero(pedido)
            r = (consultar_pedido_demo(numero=achado, conversa_id=request.state.conversa_id) if achado else None)
            if r is not None and r.estado == "ok":
                return pagina(request, "rastreio.html", resultado=None, demo=r.dados, pedido=pedido, aviso=None)
            if r is None or r.estado == "negado":
                negado()
                aviso = "Não foi possível validar esse pedido com os dados informados. Confira e tente de novo."
                return pagina(request, "rastreio.html", 403, resultado=None, pedido=pedido, aviso=aviso)
            return pagina(request, "rastreio.html", 502, resultado=None, pedido=pedido, aviso=MSG_FALHA)
        numero = entradas.numero_de_pedido(pedido)
        if numero is None or not re.fullmatch(r"[0-9]{4}", final_telefone):
            return pagina(request, "rastreio.html", 422, resultado=None, pedido=pedido,
                          aviso="Informe o número do pedido e os 4 últimos dígitos do telefone cadastrado.")
        # a ferramenta limita por conversa sem prazo; a cada janela a conversa recomeça, e o prazo é do limite do site
        r = consultar_pedido(pedido_id=int(numero), final_telefone=final_telefone,
                             conversa_id=f"{sessao_}:{limite.janela_atual()}")
        if r.estado == "ok":
            return pagina(request, "rastreio.html", resultado=r.dados, pedido=pedido, aviso=None,
                          status_pedido=apresentacao.ROTULO_STATUS_PEDIDO)
        if r.estado == "negado":
            negado()
            aviso = "Não foi possível validar esse pedido com os dados informados. Confira e tente de novo."
            return pagina(request, "rastreio.html", 403, resultado=None, pedido=pedido, aviso=aviso)
        return pagina(request, "rastreio.html", 502, resultado=None, pedido=pedido, aviso=MSG_FALHA)

    @app.post("/chat", response_class=HTMLResponse)
    def chat(request: Request, mensagem: str = Form("")):
        mensagem = mensagem.strip()
        if not mensagem:
            return pagina(request, "_chat_troca.html", 422, usuario=None, lia=None, aviso="Digite uma mensagem.")
        if len(mensagem) > MAX_MENSAGEM:
            return pagina(request, "_chat_troca.html", 422, usuario=None, lia=None,
                          aviso=f"Mensagem longa demais. Use até {MAX_MENSAGEM} caracteres.")
        agente_ = obter_agente()
        if not trava_agente.acquire(timeout=espera):  # nada é executado: a mensagem não chegou ao agente
            return pagina(request, "_chat_troca.html", 503, usuario=mensagem, lia=None,
                          aviso="A Lia está atendendo outra conversa agora. Sua mensagem não foi enviada; "
                                "tente de novo em instantes.")
        try:
            resposta = agente_.responder(request.state.conversa_id, mensagem, "real")
        except Exception:  # noqa: BLE001 - a conversa não pode derrubar o site
            log.exception("falha no agente")
            return pagina(request, "_chat_troca.html", 200, usuario=mensagem, lia=None, aviso=MSG_FALHA)
        finally:
            trava_agente.release()
        return pagina(request, "_chat_troca.html", usuario=mensagem, lia=resposta.texto, aviso=None,
                      links=resposta.links)

    return app


app = criar_app()
