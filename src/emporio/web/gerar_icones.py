"""Gera os ícones do PWA a partir da marca SVG própria, renderizando com o Chromium do Playwright.

Uso: python -m emporio.web.gerar_icones
Nada é baixado: a marca é o símbolo "marca" de static/ilustracoes.svg. As cores vêm dos tokens de site.css.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import apresentacao

STATIC = Path(__file__).resolve().parent / "static"
SAIDA = STATIC / "icones"

# nome, lado em px, fração do lado ocupada pela marca. Maskable deixa a marca dentro da zona segura (80%).
ICONES = (
    ("icon-192.png", 192, 0.62),
    ("icon-512.png", 512, 0.62),
    ("maskable-192.png", 192, 0.50),
    ("maskable-512.png", 512, 0.50),
    ("apple-touch-icon-180.png", 180, 0.62),
)


def _marca_svg(cor_marca: str, cor_furo: str) -> str:
    """Símbolo 'marca' do sprite, pronto para ser embutido, com as cores trocadas."""
    sprite = (STATIC / "ilustracoes.svg").read_text(encoding="utf-8")
    bloco = re.search(r'<symbol id="marca"[^>]*>(.*?)</symbol>', sprite, re.S).group(1)
    bloco = bloco.replace("currentColor", cor_marca).replace("var(--furo, #F4EEE3)", cor_furo)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">{bloco}</svg>'


def gerar() -> list[Path]:
    from playwright.sync_api import sync_playwright

    c = apresentacao.cores()
    fundo, marca = c["madeira"], c["creme"]
    SAIDA.mkdir(parents=True, exist_ok=True)
    gerados: list[Path] = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for nome, lado, fracao in ICONES:
                miolo = int(lado * fracao)
                html = (f'<body style="margin:0;background:{fundo};width:{lado}px;height:{lado}px;display:grid;place-items:center">'
                        f'<div style="width:{miolo}px;height:{miolo}px">{_marca_svg(marca, fundo)}</div></body>')
                pagina = navegador.new_page(viewport={"width": lado, "height": lado})
                pagina.set_content(html)
                destino = SAIDA / nome
                pagina.screenshot(path=str(destino))
                pagina.close()
                gerados.append(destino)
        finally:
            navegador.close()
    return gerados


if __name__ == "__main__":
    for arquivo in gerar():
        print(arquivo)
