"""O carrinho tem a mesma cor e o mesmo peso dos outros links do cabeçalho, em 1280 e 390 px."""
from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.e2e

JS = """() => { const f = e => { const c = getComputedStyle(e); return [c.color, c.fontWeight, c.borderTopWidth, c.borderBottomColor === 'rgba(0, 0, 0, 0)' || c.borderBottomWidth]; };
  return {carrinho: f(document.querySelector('.link-carrinho')),
          rastrear: f(document.querySelector('.menu-itens > a[href="/rastreio"]')),
          catalogo: f(document.querySelector('.menu-itens > a[href="/catalogo"]'))}; }"""


@pytest.mark.parametrize("largura,alto,movel", [(1280, 800, False), (390, 780, True)])
def test_carrinho_com_cor_e_peso_dos_demais(servidor_movel, largura, alto, movel):
    with sync_playwright() as p:
        nav = p.chromium.launch()
        try:
            pagina = nav.new_page(viewport={"width": largura, "height": alto})
            pagina.goto(servidor_movel + "/catalogo")
            if movel:
                pagina.click(".menu-botao")
            m = pagina.evaluate(JS)
            assert m["carrinho"][:2] == m["rastrear"][:2] == m["catalogo"][:2], m
            assert m["carrinho"][2] == "0px", m  # sem borda própria
            assert pagina.locator(".link-carrinho").is_visible()
            assert pagina.locator(".link-carrinho").bounding_box()["height"] >= 44 or not movel
        finally:
            nav.close()
