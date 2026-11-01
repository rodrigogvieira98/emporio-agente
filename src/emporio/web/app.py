"""App FastAPI do site. Subir com: uvicorn emporio.web.app:app

Variáveis: EMPORIO_MODELO (modelo do Ollama para a redação; vazio = só regras), EMPORIO_DECISOR (padrão
regras), EMPORIO_SEGREDO (assinatura do cookie; sem ele, um segredo novo a cada processo),
EMPORIO_COOKIE_SEGURO=1 (cookie só por HTTPS).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from .. import dinheiro
from ..agente import llm
from ..agente.fabrica import criar_agente
from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.pedido_demo import PREFIXO as PREFIXO_PEDIDO, achar_numero, consultar_pedido_demo
from ..ferramentas.pedidos import consultar_pedido
from ..ferramentas.politica import consultar_politica
from ..ferramentas.produtos import buscar_produtos, ver_produto
from ..ferramentas.promocoes import listar_promocoes
from ..politicas.manual import carregar_manual, fato
from . import apresentacao, carrinho, compra, conteudo, contato, fotos, home, navegacao

POR_PAGINA = 12  # produtos por página do catálogo; o limite de 5 itens é do chat, não do site

log = logging.getLogger("emporio.web")

AQUI = Path(__file__).resolve().parent
VERSAO_SW = "1"  # sobe a cada mudança do service worker ou da lista de estáticos que exija renovar o cache
SEM_SESSAO = ("/static", "/saude", "/sw.js", "/manifest.webmanifest", "/offline", "/favicon.ico")
COOKIE = "emporio_sessao"
MAX_MENSAGEM = 500  # limite de entrada do sistema, não é regra de loja
MSG_FALHA = "Não consegui consultar isso agora. Tente de novo em instantes."


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
        linhas.append({"p": item, "produto_id": i["produto_id"], "quantidade": i["quantidade"]})
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
    app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
    modelos = Jinja2Templates(directory=AQUI / "templates")
    modelos.env.globals.update(loja=apresentacao.loja, categorias=navegacao.listar_categorias,
                               situacao_loja=apresentacao.situacao_loja, cores=apresentacao.cores, ilustracao=apresentacao.ilustracao,
                               menu_categorias=home.categorias, formas_pagamento=apresentacao.formas_de_pagamento,
                               canais=contato.canais, itens_no_carrinho=_itens_no_carrinho,
                               prefixo_pedido=PREFIXO_PEDIDO,
                               rotulo_forma=apresentacao.ROTULO_FORMA, parcelas_max=compra.parcelas_max)
    modelos.env.filters.update(brl=apresentacao.brl, data_br=apresentacao.data_br,
                               pagamento=apresentacao.forma_pagamento, quebras=apresentacao.quebras)

    def obter_agente() -> Any:
        with trava_criacao:
            if app.state.agente is None:
                app.state.agente = criar_agente(llm.modelo_padrao())
            return app.state.agente

    def pagina(request: Request, nome: str, status: int = 200, **contexto: Any) -> HTMLResponse:
        return modelos.TemplateResponse(request, nome, contexto, status_code=status)

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
        resposta = await call_next(request)
        if novo:
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
            "background_color": c.get("papel"), "theme_color": c.get("tinta"), "categories": ["shopping", "music"],
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
        estaticos = sorted("/static/" + p.relative_to(AQUI / "static").as_posix()
                           for p in (AQUI / "static").rglob("*")
                           if p.is_file() and p.suffix != ".txt")  # licenças não vão para o cache
        corpo = ((AQUI / "sw.js").read_text(encoding="utf-8")
                 .replace('"/*VERSAO*/"', json.dumps(VERSAO_SW))
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
                      descricao="Violões, guitarras, baixos, teclados, baterias e ukuleles, com preço, condição de "
                                "pagamento e entrega à vista.")

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
    def fale_conosco(request: Request):
        return pagina_contato(request)

    @app.post("/fale-conosco", response_class=HTMLResponse)
    def fale_conosco_enviar(request: Request, assunto: str = Form(""), mensagem: str = Form(""),
                            contato_retorno: str = Form(""), site: str = Form("")):
        valores = {"assunto": assunto, "mensagem": mensagem, "contato": contato_retorno}
        if site.strip():  # campo isca: pessoa não vê nem preenche; descarta sem gravar e sem dar pista
            return pagina(request, "fale_conosco.html", titulo_pagina="Fale conosco", valores={}, erros={},
                          protocolo="", limites=contato.LIMITES, descricao="")
        erros = contato.validar(valores)
        if erros:
            return pagina_contato(request, valores, erros, 422)
        try:
            protocolo = contato.gravar(valores)
        except Exception:  # noqa: BLE001 - o formulário não pode derrubar o site, e o texto do cliente é mantido
            return pagina_contato(request, valores, {"geral": "Não conseguimos registrar agora. Tente de novo em instantes."}, 502)
        return pagina(request, "fale_conosco.html", titulo_pagina="Fale conosco", valores={}, erros={},
                      protocolo=protocolo, limites=contato.LIMITES, descricao="")

    @app.get("/catalogo", response_class=HTMLResponse)
    def catalogo(request: Request, categoria: str = "", termo: str = "", preco_min: str = "",
                 preco_max: str = "", todos: str = "", pagina_: int = Query(1, alias="pagina", ge=1)):
        filtros = {"categoria": categoria.strip(), "termo": termo.strip(), "preco_min": preco_min.strip(),
                   "preco_max": preco_max.strip(), "todos": bool(todos)}
        erro = None
        itens: list[dict[str, Any]] = []
        total = 0
        paginas = 1
        try:
            minimo = dinheiro.para_centavos(filtros["preco_min"].replace(",", ".")) if filtros["preco_min"] else None
            maximo = dinheiro.para_centavos(filtros["preco_max"].replace(",", ".")) if filtros["preco_max"] else None
        except Exception:  # noqa: BLE001 - texto que não é número
            minimo = maximo = None
            erro = "Use apenas números nos campos de preço."
        if erro is None:
            r = buscar_produtos(categoria=filtros["categoria"] or None, termo=filtros["termo"] or None,
                                preco_min=minimo, preco_max=maximo, incluir_indisponiveis=filtros["todos"],
                                limite=POR_PAGINA, deslocamento=(pagina_ - 1) * POR_PAGINA, para_site=True)
            if r.estado == "ok":
                promos = _promocoes()
                itens = [home.com_categoria(apresentacao.preparar_item(i, promos)) for i in r.dados["itens"]]
                total = r.dados["total_encontrado"]
                paginas = max(1, -(-total // POR_PAGINA))
                if not itens:  # página além do fim: volta à última, sem página vazia
                    return RedirectResponse(str(request.url.include_query_params(pagina=paginas)), status_code=303)
            elif r.estado == "vazio":
                erro = ("Não temos essa categoria no catálogo." if r.motivo == "categoria_inexistente"
                        else "Nenhum produto encontrado com esses filtros.")
            elif r.motivo == "faixa_incoerente":
                erro = "A faixa de preço está incoerente: o mínimo passa do máximo."
            else:
                erro = MSG_FALHA
        consulta = {k: v for k, v in (("categoria", filtros["categoria"]), ("termo", filtros["termo"]),
                                      ("preco_min", filtros["preco_min"]), ("preco_max", filtros["preco_max"]),
                                      ("todos", "1" if filtros["todos"] else "")) if v}
        titulo = filtros["categoria"] or ("Resultados da busca" if filtros["termo"] else "Catálogo")
        return pagina(request, "catalogo.html", itens=itens, total=total, erro=erro, filtros=filtros,
                      pagina_atual=pagina_, paginas=paginas, por_pagina=POR_PAGINA, consulta=consulta,
                      titulo_pagina=titulo, descricao="Instrumentos musicais com preço e condição de pagamento.")

    @app.get("/produto/{produto_id}", response_class=HTMLResponse)
    def produto(request: Request, produto_id: int):
        r = ver_produto(referencia=produto_id)
        if r.estado == "vazio":
            return pagina(request, "mensagem.html", 404, titulo="Produto não encontrado",
                          texto="Não achamos esse produto. Veja o catálogo ou pergunte para a Lia.")
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
        return pagina(request, "politicas.html", temas=temas, titulo_pagina="Políticas da loja",
                      descricao="Pagamento, frete e entrega, trocas e devoluções, promoções e garantia.")

    # ---- compra de demonstração (incremento 1) ----------------------------------------------------

    def pagina_carrinho(request: Request, aviso: str | None = None, status: int = 200) -> HTMLResponse:
        return pagina(request, "carrinho.html", status, linhas=_linhas_carrinho(request.state.conversa_id),
                      aviso=aviso, max_por_item=carrinho.MAX_POR_ITEM)

    @app.get("/carrinho", response_class=HTMLResponse)
    def ver_carrinho(request: Request):
        return pagina_carrinho(request)

    @app.post("/carrinho/adicionar")
    def carrinho_adicionar(request: Request, produto_id: int = Form(...), quantidade: int = Form(1)):
        try:
            carrinho.adicionar(request.state.conversa_id, produto_id, quantidade)
        except carrinho.RecusaCarrinho as recusa:
            return pagina_carrinho(request, str(recusa), 422)
        return RedirectResponse("/carrinho", status_code=303)

    @app.post("/carrinho/alterar")
    def carrinho_alterar(request: Request, produto_id: int = Form(...), quantidade: int = Form(...)):
        try:
            carrinho.definir_quantidade(request.state.conversa_id, produto_id, quantidade)
        except carrinho.RecusaCarrinho as recusa:
            return pagina_carrinho(request, str(recusa), 422)
        return RedirectResponse("/carrinho", status_code=303)

    @app.post("/carrinho/remover")
    def carrinho_remover(request: Request, produto_id: int = Form(...)):
        carrinho.remover(request.state.conversa_id, produto_id)
        return RedirectResponse("/carrinho", status_code=303)

    def pagina_checkout(request: Request, forma: str, parcelas: str, cidade: str, aviso: str | None = None,
                        status: int = 200) -> HTMLResponse:
        c = compra.calcular(request.state.conversa_id, forma, parcelas, cidade)
        return pagina(request, "checkout.html", status, c=c, aviso=aviso, formas=compra.FORMAS)

    @app.get("/checkout", response_class=HTMLResponse)
    def ver_checkout(request: Request, forma: str = "pix", parcelas: str = "1", cidade: str = ""):
        return pagina_checkout(request, forma, parcelas, cidade)

    @app.post("/checkout", response_class=HTMLResponse)
    def finalizar_checkout(request: Request, forma: str = Form("pix"), parcelas: str = Form("1"),
                           cidade: str = Form(""), total_visto: str = Form("")):
        sessao = request.state.conversa_id
        atual = compra.calcular(sessao, forma, parcelas, cidade)
        if total_visto != str(atual["total"]):  # o cliente mudou algo sem atualizar os valores
            return pagina_checkout(request, forma, parcelas, cidade,
                                   "Os valores mudaram desde a última conferência. Confira o total e finalize de novo.",
                                   409)
        try:
            numero = compra.finalizar(sessao, forma, parcelas, cidade)
        except compra.CompraRecusada:
            return pagina_checkout(request, forma, parcelas, cidade, None, 422)
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
        if pedido.upper().startswith(PREFIXO_PEDIDO):  # pedido feito no site: identificado pela sessão, sem telefone
            achado = achar_numero(pedido)
            r = (consultar_pedido_demo(numero=achado, conversa_id=request.state.conversa_id) if achado else None)
            if r is not None and r.estado == "ok":
                return pagina(request, "rastreio.html", resultado=None, demo=r.dados, pedido=pedido, aviso=None)
            if r is None or r.estado == "negado":
                aviso = "Não foi possível validar esse pedido com os dados informados. Confira e tente de novo."
                return pagina(request, "rastreio.html", 403, resultado=None, pedido=pedido, aviso=aviso)
            return pagina(request, "rastreio.html", 502, resultado=None, pedido=pedido, aviso=MSG_FALHA)
        if not pedido.isdigit() or len(final_telefone) != 4 or not final_telefone.isdigit():
            return pagina(request, "rastreio.html", 422, resultado=None, pedido=pedido,
                          aviso="Informe o número do pedido e os 4 últimos dígitos do telefone cadastrado.")
        r = consultar_pedido(pedido_id=int(pedido), final_telefone=final_telefone,
                             conversa_id=request.state.conversa_id)
        if r.estado == "ok":
            return pagina(request, "rastreio.html", resultado=r.dados, pedido=pedido, aviso=None,
                          status_pedido=apresentacao.ROTULO_STATUS_PEDIDO)
        if r.estado == "negado":
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
        return pagina(request, "_chat_troca.html", usuario=mensagem, lia=resposta.texto, aviso=None)

    return app


app = criar_app()
