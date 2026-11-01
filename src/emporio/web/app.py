"""App FastAPI do site. Subir com: uvicorn emporio.web.app:app

Variáveis: EMPORIO_MODELO (modelo do Ollama para a redação; vazio = só regras), EMPORIO_DECISOR (padrão
regras), EMPORIO_SEGREDO (assinatura do cookie; sem ele, um segredo novo a cada processo),
EMPORIO_COOKIE_SEGURO=1 (cookie só por HTTPS).
"""
from __future__ import annotations

import logging
import os
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from .. import dinheiro
from ..agente import llm
from ..agente.fabrica import criar_agente
from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.pedidos import consultar_pedido
from ..ferramentas.politica import consultar_politica
from ..ferramentas.produtos import buscar_produtos, ver_produto
from ..ferramentas.promocoes import listar_promocoes
from ..politicas.manual import carregar_manual, fato
from . import apresentacao, navegacao

log = logging.getLogger("emporio.web")

AQUI = Path(__file__).resolve().parent
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


def criar_app(agente: Any = None) -> FastAPI:
    os.environ.setdefault("EMPORIO_DECISOR", "regras")
    segredo = os.environ.get("EMPORIO_SEGREDO") or secrets.token_hex(32)
    assinador = URLSafeSerializer(segredo, salt="emporio-sessao")
    seguro = os.environ.get("EMPORIO_COOKIE_SEGURO") == "1"
    trava_agente = threading.Lock()  # o agente guarda telemetria em memória: uma conversa por vez no processo
    trava_criacao = threading.Lock()

    app = FastAPI(title="Lia", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.agente = agente  # criado na primeira conversa, uma vez por processo
    app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
    modelos = Jinja2Templates(directory=AQUI / "templates")
    modelos.env.globals.update(loja=apresentacao.loja, categorias=navegacao.listar_categorias)
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
        if request.url.path.startswith("/static") or request.url.path == "/saude":
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

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request):
        promos = listar_promocoes()
        destaque = []
        if promos.estado == "ok":
            for p in promos.dados["promocoes"]:
                if p["conflito"] or p["situacao_venda"] != "disponivel":
                    continue
                destaque.append(p)
                if len(destaque) == 4:
                    break
        return pagina(request, "inicio.html", destaque=destaque)

    @app.get("/catalogo", response_class=HTMLResponse)
    def catalogo(request: Request, categoria: str = "", termo: str = "", preco_min: str = "",
                 preco_max: str = "", todos: str = ""):
        filtros = {"categoria": categoria.strip(), "termo": termo.strip(), "preco_min": preco_min.strip(),
                   "preco_max": preco_max.strip(), "todos": bool(todos)}
        erro = None
        itens: list[dict[str, Any]] = []
        total = 0
        try:
            minimo = dinheiro.para_centavos(filtros["preco_min"].replace(",", ".")) if filtros["preco_min"] else None
            maximo = dinheiro.para_centavos(filtros["preco_max"].replace(",", ".")) if filtros["preco_max"] else None
        except Exception:  # noqa: BLE001 - texto que não é número
            minimo = maximo = None
            erro = "Use apenas números nos campos de preço."
        if erro is None:
            r = buscar_produtos(categoria=filtros["categoria"] or None, termo=filtros["termo"] or None,
                                preco_min=minimo, preco_max=maximo, incluir_indisponiveis=filtros["todos"])
            if r.estado == "ok":
                promos = _promocoes()
                itens = [apresentacao.preparar_item(i, promos) for i in r.dados["itens"]]
                total = r.dados["total_encontrado"]
            elif r.estado == "vazio":
                erro = ("Não temos essa categoria no catálogo." if r.motivo == "categoria_inexistente"
                        else "Nenhum produto encontrado com esses filtros.")
            elif r.motivo == "faixa_incoerente":
                erro = "A faixa de preço está incoerente: o mínimo passa do máximo."
            else:
                erro = MSG_FALHA
        return pagina(request, "catalogo.html", itens=itens, total=total, erro=erro, filtros=filtros)

    @app.get("/produto/{produto_id}", response_class=HTMLResponse)
    def produto(request: Request, produto_id: int):
        r = ver_produto(referencia=produto_id)
        if r.estado == "vazio":
            return pagina(request, "mensagem.html", 404, titulo="Produto não encontrado",
                          texto="Não achamos esse produto. Veja o catálogo ou pergunte para a Lia.")
        if r.estado != "ok":
            return pagina(request, "mensagem.html", 502, titulo="Produto indisponível no momento", texto=MSG_FALHA)
        item = apresentacao.preparar_item(r.dados, _promocoes())
        condicoes = _condicoes_de_pagamento(produto_id) if item["pode_comprar"] else None
        return pagina(request, "produto.html", p=item, categoria=r.dados["categoria"], descricao=r.dados["descricao"],
                      condicoes=condicoes)

    @app.get("/politicas", response_class=HTMLResponse)
    def politicas(request: Request):
        temas = sorted(carregar_manual().temas_conhecidos())
        r = consultar_politica(temas=temas)
        if r.estado != "ok":
            return pagina(request, "mensagem.html", 502, titulo="Políticas indisponíveis no momento", texto=MSG_FALHA)
        secoes = [s for s in r.dados["secoes"] if s["publico"] and s["texto"]]
        return pagina(request, "politicas.html", secoes=secoes)

    @app.get("/rastreio", response_class=HTMLResponse)
    def rastreio_form(request: Request):
        return pagina(request, "rastreio.html", resultado=None, aviso=None, pedido="")

    @app.post("/rastreio", response_class=HTMLResponse)
    def rastreio(request: Request, pedido: str = Form(""), final_telefone: str = Form("")):
        pedido, final_telefone = pedido.strip(), final_telefone.strip()
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
        try:
            with trava_agente:
                resposta = agente_.responder(request.state.conversa_id, mensagem, "real")
        except Exception:  # noqa: BLE001 - a conversa não pode derrubar o site
            log.exception("falha no agente")
            return pagina(request, "_chat_troca.html", 200, usuario=mensagem, lia=None, aviso=MSG_FALHA)
        return pagina(request, "_chat_troca.html", usuario=mensagem, lia=resposta.texto, aviso=None)

    return app


app = criar_app()
