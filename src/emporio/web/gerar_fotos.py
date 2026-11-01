"""Gera as fotos WebP do site a partir de originais do Wikimedia Commons e grava `static/fotos/creditos.json`.

Uso (só na geração; Pillow fica em requirements-e2e.txt, fora da imagem de produção):
    python -m emporio.web.gerar_fotos PASTA_DOS_ORIGINAIS

PASTA_DOS_ORIGINAIS é uma pasta vazia à parte, onde ficam os arquivos baixados (dado não confiável: são só lidos
pelo Pillow, nunca executados). O nome de cada original é o título do Commons com espaços trocados por "_".
Autor, licença e links vêm da API do Commons (`prop=imageinfo&iiprop=extmetadata|url`); licença fora de domínio
público, CC0, CC BY ou CC BY-SA interrompe a geração. Cada foto vira 800x600 em fundo branco, com a mesma
inclinação nos instrumentos de corpo longo, para a vitrine não parecer colagem.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SAIDA = Path(__file__).resolve().parent / "static" / "fotos"
LARGURA, ALTURA, LIMITE_BYTES = 800, 600, 200 * 1024
API = "https://commons.wikimedia.org/w/api.php"
LICENCAS_LIVRES = re.compile(r"^(CC BY(-SA)? \d\.\d|CC0.*|Public domain.*|PD.*)$", re.I)

# chave, título no Commons, rotação em graus (negativo = horário), recorte opcional (esq, topo, dir, base em fração), texto alternativo
FOTOS: tuple[dict[str, Any], ...] = (
    {"chave": "violao-nylon-1", "titulo": "Gitara klasyczna C30M firmy Yamaha.jpg", "giro": -60,
     "alt": "Violão clássico com cordas de nylon, de frente"},
    {"chave": "violao-folk-1", "titulo": "Gitara akustyczna GLA-T200J Tramontane firmy Lag.jpg", "giro": -60,
     "alt": "Violão folk com cordas de aço, de frente"},
    {"chave": "violao-eletroacustico-1", "titulo": "Gitara elektro-akustyczna GLA-T100 ACE Tramontane firmy Lag.jpg", "giro": -60,
     "alt": "Violão eletroacústico com corte lateral, de frente"},
    {"chave": "guitarra-corpo-1", "titulo": "Fender Stratocaster 004-2.jpg", "giro": -60,
     "alt": "Guitarra elétrica de corpo duplo e três captadores, de frente"},
    {"chave": "guitarra-corpo-2", "titulo": "Gitara elektryczna Pacifica 112-VCX firmy Yamaha.jpg", "giro": -60,
     "alt": "Guitarra elétrica preta de corpo duplo, de frente"},
    {"chave": "guitarra-corpo-3", "titulo": "Gitara elektryczna Variax JTV59 CSB firmy Line 6.jpg", "giro": -60,
     "alt": "Guitarra elétrica sunburst de corpo único, de frente"},
    {"chave": "guitarra-les-paul", "titulo": 'Gitara elektryczna Les Paul Slash "Apetite For Destruction" firmy Gibson.jpg', "giro": -60,
     "alt": "Guitarra elétrica de corpo único em acabamento sunburst, de frente"},
    {"chave": "baixo-1", "titulo": "Gitara basowa PBG2T sygn. Paul Grey firmy Ibanez.jpg", "giro": -60,
     "alt": "Baixo elétrico de quatro cordas, de frente"},
    {"chave": "baixo-2", "titulo": "Gitara basowa Road Worn 50's P-Bass firmy Fender.jpg", "giro": -60,
     "alt": "Baixo elétrico sunburst de quatro cordas, de frente"},
    {"chave": "bateria-1", "titulo": "Zestaw perkusyjny Element Power Fusion firmy Ludwig.jpg", "giro": 0,
     "tapar": ((290, 318, 386, 380), (310, 484, 338, 502)),
     "alt": "Bateria acústica com cinco peças e ferragens cromadas"},
    {"chave": "teclado-1", "titulo": "Novation ReMote 37SL.jpg", "giro": 0,
     "alt": "Teclado controlador de 37 teclas visto de cima"},
    {"chave": "teclado-2", "titulo": "Masterkeyboard.png", "giro": 0,
     "alt": "Teclado de palco azul com teclas brancas e pretas, em perspectiva"},
    {"chave": "ukulele-1", "titulo": "CreativeTools.se - PackshotCreator - Mahalo ukulele (5077880957).jpg", "giro": 0, "recorte": (0.0, 0.0, 1.0, 0.84), "tolerancia": 40,
     "alt": "Ukulele amarelo sobre fundo branco"},
    {"chave": "ukulele-2", "titulo": "Mahalo Soprano Ukulele.jpg", "giro": -60, "tolerancia": 60,
     "alt": "Ukulele soprano de madeira clara, de frente"},
    {"chave": "abertura", "titulo": "Kytara a ruka.jpg", "giro": 0, "recorte": (0.0, 0.30, 1.0, 0.80), "cobrir": True,
     "alt": "Mão tocando as cordas de um violão de acabamento sunburst"},
)


def _pedir(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "emporio-agente-gerador/1.0 (geracao local de fotos)"})
    for tentativa in range(6):
        try:
            return urllib.request.urlopen(req, timeout=60).read()
        except Exception:  # noqa: BLE001 - 429 e falhas de rede: espera e tenta de novo
            time.sleep(6 * (tentativa + 1))
    raise RuntimeError(f"falha ao consultar {url}")


def _texto(valor: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", valor or "")).split())


def metadados(titulos: list[str]) -> dict[str, dict[str, str]]:
    """Autor, licença e links de cada arquivo, direto da API do Commons."""
    consulta = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "extmetadata|url",
        "titles": "|".join("File:" + t for t in titulos)})
    dados = json.loads(_pedir(f"{API}?{consulta}"))
    saida: dict[str, dict[str, str]] = {}
    for pagina in dados["query"]["pages"].values():
        info = pagina["imageinfo"][0]
        m = info["extmetadata"]
        licenca = _texto(m.get("LicenseShortName", {}).get("value", ""))
        if not LICENCAS_LIVRES.match(licenca):
            raise SystemExit(f"licença não aceita em {pagina['title']}: {licenca!r}")
        saida[pagina["title"].removeprefix("File:")] = {
            "autor": _texto(m.get("Artist", {}).get("value", "")) or "Autor não informado",
            "licenca": licenca, "link_licenca": m.get("LicenseUrl", {}).get("value", ""),
            "link_origem": info["descriptionurl"]}
    return saida


def _fundo_branco(im, tolerancia: int = 28):
    """Leva o fundo quase branco (borda da foto) a branco puro, para a rotação não deixar moldura."""
    from PIL import Image, ImageDraw
    im = im.convert("RGB")
    for canto in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1)):
        ImageDraw.floodfill(im, canto, (255, 255, 255), thresh=tolerancia)
    return im


def _aparar(im):
    from PIL import Image, ImageChops
    fundo = Image.new("RGB", im.size, (255, 255, 255))
    caixa = ImageChops.difference(im, fundo).convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
    return im.crop(caixa) if caixa else im


def processar(caminho: Path, f: dict[str, Any]):
    from PIL import Image
    im = Image.open(caminho)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        fundo = Image.new("RGBA", im.size, (255, 255, 255, 255))
        fundo.alpha_composite(im)
        im = fundo
    im = im.convert("RGB")
    if f.get("recorte"):
        e, t, d, b = f["recorte"]
        im = im.crop((int(e * im.width), int(t * im.height), int(d * im.width), int(b * im.height)))
    if f.get("cobrir"):  # fotografia editorial: preenche o quadro, sem fundo branco
        escala = max(LARGURA / im.width, ALTURA / im.height)
        im = im.resize((round(im.width * escala), round(im.height * escala)), Image.LANCZOS)
        e, t = (im.width - LARGURA) // 2, (im.height - ALTURA) // 2
        return im.crop((e, t, e + LARGURA, t + ALTURA))
    im = _fundo_branco(im, f.get("tolerancia", 28))
    if f.get("giro"):
        im = im.rotate(f["giro"], expand=True, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    im = _aparar(im)
    margem = 0.07
    escala = min(LARGURA * (1 - 2 * margem) / im.width, ALTURA * (1 - 2 * margem) / im.height)
    im = im.resize((max(1, round(im.width * escala)), max(1, round(im.height * escala))), Image.LANCZOS)
    quadro = Image.new("RGB", (LARGURA, ALTURA), (255, 255, 255))
    quadro.paste(im, ((LARGURA - im.width) // 2, (ALTURA - im.height) // 2))
    for caixa in f.get("tapar", ()):  # logotipo do fabricante: cobre com a cor do entorno, para a foto não contradizer o produto
        _tapar(quadro, caixa)
    return quadro


def _tapar(quadro, caixa: tuple[int, int, int, int]) -> None:
    from PIL import ImageDraw, ImageStat
    e, t, d, b = caixa
    anel = quadro.crop((e - 6, t - 6, d + 6, b + 6))
    cor = tuple(int(v) for v in ImageStat.Stat(anel).median)
    ImageDraw.Draw(quadro).rectangle(caixa, fill=cor)


def gravar(im, destino: Path) -> int:
    for qualidade in (86, 80, 74, 68, 60, 50):
        im.save(destino, "WEBP", quality=qualidade, method=6)
        if destino.stat().st_size <= LIMITE_BYTES:
            break
    return destino.stat().st_size


def main(pasta: Path) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    meta = metadados([f["titulo"] for f in FOTOS])
    creditos = []
    for f in FOTOS:
        origem = pasta / f["titulo"].replace(" ", "_").replace('"', "")[-70:]
        if not origem.exists():
            print("sem original:", origem.name)
            continue
        arquivo = f["chave"] + ".webp"
        tamanho = gravar(processar(origem, f), SAIDA / arquivo)
        m = meta[f["titulo"]]
        creditos.append({"chave": f["chave"], "arquivo": arquivo, "largura": LARGURA, "altura": ALTURA, "alt": f["alt"],
                         "titulo": f["titulo"].removesuffix(".jpg").removesuffix(".png").removesuffix(".JPG"),
                         "autor": m["autor"], "licenca": m["licenca"], "link_licenca": m["link_licenca"],
                         "link_origem": m["link_origem"],
                         "alteracoes": ("Recortada e ajustada ao quadro 4:3." if f.get("cobrir") else
                                        "Recortada, girada e ajustada ao quadro 4:3 em fundo branco."
                                        + (" Logotipo do fabricante coberto." if f.get("tapar") else ""))})
        print(arquivo, tamanho // 1024, "KB")
    (SAIDA / "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    doc = Path(__file__).resolve().parents[3] / "docs" / "CREDITOS_IMAGENS.md"
    linhas = ["# Créditos das imagens", "",
              "Fotografias do Wikimedia Commons, em licença livre. Gerado por `python -m emporio.web.gerar_fotos`; "
              "a mesma lista aparece em `/creditos`.", "",
              "| Arquivo | Autor | Licença | Origem | Alterações |", "|---|---|---|---|---|"]
    for c in creditos:
        linhas.append(f"| {c['arquivo']} | {c['autor'].replace('|', '/')} | [{c['licenca']}]({c['link_licenca']}) | "
                      f"[página]({c['link_origem']}) | {c['alteracoes']} |")
    doc.write_text("\n".join(linhas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
