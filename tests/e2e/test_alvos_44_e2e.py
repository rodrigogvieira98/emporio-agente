"""Alvos de toque de 44 px nas páginas do site em 360 e 390 px, medidos no navegador."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

PAGINAS = ["/", "/catalogo", "/produto/90", "/carrinho", "/checkout", "/rastreio", "/fale-conosco",
           "/perguntas-frequentes", "/politicas", "/privacidade", "/creditos"]

JS = """() => {
  const ruins = [];
  const sel = 'a[href], button, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, summary, textarea';
  for (const e of document.querySelectorAll(sel)) {
    if (e.closest('.so-leitor, .isca, [hidden]') || e.classList.contains('pular') || e.closest('.carrossel-lista[aria-hidden]')) continue;
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (e.tagName === 'A' && cs.display === 'inline') continue;        // link dentro de frase: exceção de texto corrido
    const r = e.closest('.carrossel-item') ? {width: e.offsetWidth, height: e.offsetHeight} : e.getBoundingClientRect();  // cartões laterais do carrossel têm escala animada: vale o tamanho de layout
    if (!r.width || !r.height) continue;
    if (r.height < 43.5 || r.width < 43.5) ruins.push([e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : ''), (e.textContent || e.name || '').trim().slice(0, 24), Math.round(r.width), Math.round(r.height)]);
  }
  return ruins;
}"""


@pytest.mark.parametrize("caminho", PAGINAS)
def test_alvos_de_toque_tem_44px(servidor_movel, movel, caminho):
    pagina, _, _ = movel
    if caminho == "/checkout":
        pagina.goto(servidor_movel + "/produto/90")
        pagina.click("text=Adicionar ao carrinho")
    pagina.goto(servidor_movel + caminho)
    if pagina.locator(".menu-botao").is_visible():
        pagina.tap(".menu-botao")  # mede também os links dentro do menu recolhido
    ruins = pagina.evaluate(JS)
    assert not ruins, "; ".join(map(str, ruins))
