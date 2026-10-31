"""consultar_politica: seções do manual por tema."""
from __future__ import annotations

from pydantic import field_validator

from ..politicas.manual import carregar_manual, fonte_da_secao
from ..texto import normalizar
from .envelope import EntradaBase, Resultado, ferramenta, resultado


class EntradaPolitica(EntradaBase):
    temas: list[str]

    @field_validator("temas")
    @classmethod
    def _temas(cls, v: list[str]) -> list[str]:
        if not v or any(not t.strip() for t in v):
            raise ValueError("temas vazios")
        return v


@ferramenta(EntradaPolitica)
def consultar_politica(e: EntradaPolitica) -> Resultado:
    manual = carregar_manual()
    pedidos = [normalizar(t).replace(" ", "_") for t in e.temas]
    conhecidos = manual.temas_conhecidos()
    desconhecidos = [t for t in pedidos if t not in conhecidos]
    secoes = [s for s in manual.secoes if set(s.temas) & set(pedidos)]
    if not secoes:
        return resultado("vazio", {"temas_desconhecidos": desconhecidos}, motivo="tema_desconhecido")
    saida = []
    for s in secoes:
        saida.append({
            "id": s.id,
            "titulo": s.titulo,
            "versao": s.versao,
            "hash": s.hash,
            "publico": s.publico,
            # procedimento interno não tem o texto repassado; as condições seguem disponíveis
            "texto": s.texto if s.publico else None,
            "condicoes": [c.model_dump(exclude_none=True) for c in s.condicoes],
            "ambiguidades": [a.model_dump() for a in manual.ambiguidades_da_secao(s.id)],
        })
    return resultado("ok", {"secoes": saida, "temas_desconhecidos": desconhecidos},
                     [fonte_da_secao(s) for s in secoes])
