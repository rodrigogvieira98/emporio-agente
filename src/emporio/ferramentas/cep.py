"""Localizador de CEP do checkout.

O servidor consulta o ViaCEP (biblioteca padrão, 3 s de limite, memória em processo); o navegador nunca fala com
terceiros. O CEP da loja vem do manual e dispensa consulta. Se o serviço falhar, a compra não é bloqueada: a faixa de
a faixa da cidade-base vale como contingência e, fora dela, o frete fica com a equipe. `EMPORIO_CEP_EXTERNO=0` desliga a consulta.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from dataclasses import dataclass

from ..politicas.manual import fato
from ..texto import normalizar

log = logging.getLogger("emporio.ferramentas.cep")

URL_VIACEP = "https://viacep.com.br/ws/{cep}/json/"
LIMITE_SEGUNDOS = 3
# Não vem do manual: declarada no README. Usada só quando o serviço está indisponível.
FAIXA_CAMPO_GRANDE = (79000000, 79129999)

_memoria: dict[str, "Localizacao"] = {}
_trava = threading.Lock()


@dataclass(frozen=True)
class Localizacao:
    """estado: ok | inexistente | invalido | indisponivel."""
    estado: str
    cep: str = ""
    logradouro: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    contingencia: bool = False

    @property
    def endereco(self) -> str:
        cidade_uf = f"{self.cidade}/{self.uf}" if self.cidade and self.uf else self.cidade
        return ", ".join(p for p in (self.logradouro, self.bairro, cidade_uf) if p)


def apenas_digitos(cep: str) -> str:
    return "".join(ch for ch in (cep or "") if ch.isdigit())


def formato_valido(cep: str) -> bool:
    texto = (cep or "").strip()
    return len(apenas_digitos(texto)) == 8 and texto.replace("-", "").isdigit()


def formatar(cep: str) -> str:
    d = apenas_digitos(cep)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else (cep or "").strip()[:12]


def _cidade_base() -> str:
    f = fato("frete.cidade_base")
    return str(f.valor) if f else ""


def _loja() -> tuple[str, str, str]:
    """CEP, cidade e UF do endereço da loja no manual."""
    f = fato("empresa.endereco")
    try:
        e = f.valor
        return apenas_digitos(e["cep"]), str(e["cidade"]), str(e["uf"])
    except (AttributeError, KeyError, TypeError):
        return "", "", ""


def eh_cidade_base(cidade: str, uf: str) -> bool:
    """A cidade-base só conta com a UF da loja: há cidades de mesmo nome em outros estados."""
    _, _, uf_loja = _loja()
    return bool(cidade) and normalizar(cidade) == normalizar(_cidade_base()) and uf.upper() == uf_loja.upper()


def _consultar_externo(digitos: str) -> dict:
    req = urllib.request.Request(URL_VIACEP.format(cep=digitos), headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=LIMITE_SEGUNDOS) as resp:  # noqa: S310 (URL fixa, https)
        return json.loads(resp.read().decode("utf-8"))


def _contingencia(digitos: str) -> Localizacao:
    if FAIXA_CAMPO_GRANDE[0] <= int(digitos) <= FAIXA_CAMPO_GRANDE[1]:
        _, _, uf = _loja()
        return Localizacao("ok", formatar(digitos), cidade=_cidade_base(), uf=uf, contingencia=True)
    return Localizacao("indisponivel", formatar(digitos))


def localizar(cep: str) -> Localizacao:
    if not formato_valido(cep):
        return Localizacao("invalido", (cep or "").strip()[:12])
    d = apenas_digitos(cep)
    loja_cep, loja_cidade, loja_uf = _loja()
    if d == loja_cep:
        return Localizacao("ok", formatar(d), cidade=loja_cidade, uf=loja_uf)
    if os.environ.get("EMPORIO_CEP_EXTERNO", "1") == "0":
        return _contingencia(d)
    with _trava:
        achado = _memoria.get(d)
    if achado is not None:
        return achado
    try:
        dados = _consultar_externo(d)
        if not isinstance(dados, dict):
            raise ValueError("resposta fora do formato")
        if str(dados.get("erro", "")).lower() == "true":
            res = Localizacao("inexistente", formatar(d))
        else:
            cidade, uf = str(dados.get("localidade") or "").strip(), str(dados.get("uf") or "").strip()
            if not cidade or not uf:
                raise ValueError("resposta sem cidade ou UF")
            res = Localizacao("ok", formatar(d), str(dados.get("logradouro") or "").strip(),
                              str(dados.get("bairro") or "").strip(), cidade, uf)
    except Exception as exc:  # rede, tempo esgotado, JSON inválido: nunca derruba o checkout
        log.warning("consulta de CEP indisponivel (%s): %s", type(exc).__name__, exc)
        return _contingencia(d)
    with _trava:
        _memoria[d] = res
    return res
