"""QA móvel (etapa 16), um teste por item, em 360 e 390 px, com medição."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_retrato_da_lia_no_botao_e_no_painel(servidor_movel, movel):
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/")
    js = """() => [...document.querySelectorAll('img.lia-retrato')].filter(i => i.getBoundingClientRect().width > 0).map(i => {
        const r = i.getBoundingClientRect(), c = getComputedStyle(i);
        return {src: i.currentSrc, w: r.width, h: r.height, natural: i.naturalWidth, raio: c.borderRadius};})"""
    medidas = pagina.evaluate(js)  # fechada: só o botão
    pagina.click("#chat-alternar")
    medidas += pagina.evaluate(js)  # aberta: só o cabeçalho do painel
    assert len(medidas) == 2
    for m in medidas:
        assert "/static/lia-" in m["src"] and m["src"].endswith(".webp") and m["natural"] > 0 and m["w"] == 44 == m["h"]
        assert m["raio"] in ("50%", "22px")
    assert "assistente virtual" in pagina.inner_text(".chat-id")
