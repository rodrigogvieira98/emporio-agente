"""Percepção: lê a mensagem, extrai dados e decide se o assunto continua, muda ou retoma."""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from .. import config
from ..dinheiro import para_centavos
from ..ferramentas.encaminhamento import mascarar_dado_pessoal
from ..texto import normalizar, tokens
from . import catalogo
from . import vocabulario as v
from .estado import Estado

POSVENDA = {"devolucao", "troca_preferencia", "defeito"}
FAMILIAS = {
    "busca_produto": "produto", "preco_produto": "produto", "disponibilidade": "produto",
    "status_pedido": "posvenda", "devolucao": "posvenda", "troca_preferencia": "posvenda",
    "defeito": "posvenda", "garantia": "posvenda",
}
# esperando um dado: respostas curtas continuam o assunto
AGUARDA_DADO = {"pedido", "dados_posvenda", "referencia_produto", "escolha_produto", "cidade", "valor_pedido", "categoria"}

_PRECO = r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)(?:\s*(mil))?(?:\s*reais|\s*real)?"
RE_MAX = re.compile(r"\b(?:ate|no maximo|maximo|abaixo de|menos de|por ate)\s*" + _PRECO)
RE_MIN = re.compile(r"\b(?:a partir de|acima de|mais de|no minimo|minimo)\s*" + _PRECO)
RE_VALOR = re.compile(r"(?:r\$\s*(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?))|(?:\b(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:reais|real)\b)")
RE_PARCELAS = re.compile(r"\b(\d{1,2})\s*x\b|\bem (\d{1,2}) (?:vezes|parcelas)\b|\b(\d{1,2}) (?:vezes|parcelas)\b")
RE_CIDADE = re.compile(r"\b(?:para|pra|em|na cidade de|moro em|sou de|estou em)\s+([a-z]+(?:\s+(?:de|do|da|dos|das)?\s*[a-z]+){0,2})")


def _reais(texto: str, mil: str | None = None) -> int | None:
    limpo = texto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpo)
    except InvalidOperation:
        return None
    if mil:
        valor *= 1000
    return para_centavos(valor)


LIMITE_DISTINTIVO = 4  # marca que aparece em até 4 produtos identifica o item
NAO_E_CIDADE = {"compra", "pedido", "valor", "mim", "ele", "ela", "um", "uma", "o", "a", "os", "as", "meu", "minha",
                "entrega", "envio", "casa", "loja", "la", "isso", "esse", "essa", "estoque", "vezes"}
PARA_NA_CIDADE = {"com", "um", "uma", "pedido", "valor", "no", "e", "ou", "r", "se", "que", "por", "quanto"}


def _cortar_cidade(trecho: str) -> str:
    """Pára antes de 'de um pedido', 'com ...' etc., sem cortar 'Nova Alvorada do Sul'."""
    palavras = trecho.split()
    saida: list[str] = []
    for i, w in enumerate(palavras):
        proxima = palavras[i + 1] if i + 1 < len(palavras) else None
        if w in PARA_NA_CIDADE or (w in ("de", "do", "da", "dos", "das") and (proxima is None or proxima in PARA_NA_CIDADE)):
            break
        saida.append(w)
    return " ".join(saida)


def _datas(norm: str) -> list[tuple[date, str | None]]:
    hoje = config.hoje()
    achadas: list[tuple[date, str | None]] = []
    for m in v.DATA.finditer(norm):
        dia, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
        try:
            if ano is None:
                d = date(hoje.year, mes, dia)
                if d > hoje:
                    d = date(hoje.year - 1, mes, dia)
            else:
                a = int(ano)
                d = date(a + 2000 if a < 100 else a, mes, dia)
        except ValueError:
            continue
        antes = norm[max(0, m.start() - 30):m.start()]
        dica = ("recebimento" if re.search(r"receb|entreg|chegou|chegada", antes)
                else "compra" if re.search(r"compr|pedi|fiz", antes) else None)
        achadas.append((d, dica))
    for palavra, dias in (("anteontem", 2), ("ontem", 1), ("hoje", 0)):
        if re.search(rf"\b{palavra}\b", norm):
            antes = norm[max(0, norm.index(palavra) - 30):norm.index(palavra)]
            dica = "recebimento" if re.search(r"receb|chegou", antes) else "compra" if re.search(r"compr", antes) else None
            achadas.append((hoje - timedelta(days=dias), dica))
            break
    return achadas


def _numeros_de_pedido(norm: str, estado: Estado) -> dict[str, Any]:
    """Número do pedido e final do telefone. O final nunca é gravado."""
    out: dict[str, Any] = {}
    resto = norm
    tel = v.TELEFONE_COMPLETO.search(resto)
    if tel:
        out["final_telefone"] = re.sub(r"\D", "", tel.group(0))[-4:]
        resto = resto.replace(tel.group(0), " ")
    m = v.FINAL_EXPLICITO.search(resto)
    if m and "final_telefone" not in out:
        out["final_telefone"] = m.group(1)
    if m:
        resto = resto.replace(m.group(0), " ")
    m = v.PEDIDO_EXPLICITO.search(resto)
    if m:
        out["pedido_id"] = int(m.group(1) or m.group(2))
        resto = resto.replace(m.group(0), " ")
    if estado.aguardando == "pedido":
        resto = v.DATA.sub(" ", resto)
        for n in re.findall(r"\b\d+\b", resto):
            tem_pedido = "pedido_id" in out or estado.declarado("pedido_id") is not None
            if len(n) == 4 and "final_telefone" not in out and tem_pedido:
                out["final_telefone"] = n
            elif len(n) <= 3 and "pedido_id" not in out:
                out["pedido_id"] = int(n)
            elif len(n) == 4 and "final_telefone" not in out:
                out["final_telefone"] = n
    return out


def _limpar_para_referencia(norm: str, voc: catalogo.Vocabulario) -> str:
    s = RE_MAX.sub(" ", norm)
    s = RE_MIN.sub(" ", s)
    s = RE_VALOR.sub(" ", s)
    s = RE_PARCELAS.sub(lambda m: m.group(0) if m.group(0).replace(" ", "") in voc.df else " ", s)
    s = v.DATA.sub(" ", s)
    return s


def extrair_slots(norm: str, mensagem: str, estado: Estado) -> dict[str, Any]:
    slots: dict[str, Any] = {"palavras": len(norm.split())}
    slots.update(_numeros_de_pedido(norm, estado))
    m = RE_MAX.search(norm)
    if m:
        slots["preco_max"] = _reais(m.group(1), m.group(2))
    m = RE_MIN.search(norm)
    if m:
        slots["preco_min"] = _reais(m.group(1), m.group(2))
    if "preco_max" not in slots and "preco_min" not in slots:
        m = RE_VALOR.search(norm)
        if m:
            slots["valor"] = _reais(m.group(1) or m.group(2))
    voc = catalogo.vocabulario()
    m = RE_PARCELAS.search(norm)
    if m:
        antes = norm[:m.start()].split()
        token = m.group(0).replace(" ", "")
        # "Bass 2X" é nome de produto; "em 2x" é parcelamento
        if not (token in voc.df and (not antes or antes[-1] not in ("em", "ate", "de", "no"))):
            slots["parcelas"] = int(next(g for g in m.groups() if g))
    if re.search(r"\bpix\b", norm):
        slots["forma"] = "pix"
    elif re.search(r"\bboleto\b", norm):
        slots["forma"] = "boleto"
    elif re.search(r"\bdebito\b", norm):
        slots["forma"] = "debito"
    elif re.search(r"\b(credito|cartao|parcel\w*)\b", norm) or "parcelas" in slots:
        slots["forma"] = "credito"
    sobra = [t for t in tokens(_limpar_para_referencia(norm, voc)) if t not in v.PALAVRAS_SOLTAS]
    for t in sobra:
        if t in v.CATEGORIAS:
            slots.setdefault("categoria", v.CATEGORIAS[t])
    conteudo = [t for t in sobra if t not in v.CATEGORIAS
                and not any(p.fullmatch(t) for _, p in v.PADROES_INTENCAO)
                and not re.fullmatch(r"(comprar|comprei|gostei|interesse|interessado|interessada|fazer|quer)", t)]
    nomes = [t for t in conteudo if t in voc.df]
    if nomes:
        slots["termo"] = " ".join(nomes)
    # só vale como produto se algum termo identifica (modelo com número, ou marca rara no catálogo);
    # as demais palavras seguem junto, para que o que não existir resulte em "não encontrei"
    if any(re.search(r"\d", t) or voc.df[t] <= LIMITE_DISTINTIVO for t in nomes):
        slots["referencia"] = " ".join(conteudo)
        slots["tem_modelo"] = True
    palavras_da_msg = set(tokens(norm))
    for c in voc.campanhas:
        chaves = [t for t in tokens(c) if t not in ("de", "da", "do", "dos", "das")]
        if chaves and all(t in palavras_da_msg for t in chaves):
            slots["termo_promocao"] = c
            break
    slots["datas"] = _datas(norm)
    if v.CANAL_ONLINE.search(norm):
        slots["canal_compra"] = "online"
    elif v.CANAL_LOJA.search(norm):
        slots["canal_compra"] = "loja"
    if v.ESTADO_RUIM.search(norm):
        slots["estado_produto"] = "com sinais de uso ou sem a embalagem original"
    elif v.ESTADO_BOM.search(norm):
        slots["estado_produto"] = "na embalagem original, sem sinais de uso"
    slots["afirmativo"] = bool(v.AFIRMATIVO.search(norm))
    slots["negativo"] = bool(v.NEGATIVO.search(norm))
    slots["nega_reclamacao"] = bool(v.NEGA_RECLAMACAO.search(norm))
    slots["nega_atendente"] = bool(v.NEGA_ATENDENTE.search(norm))
    slots["abrir_reclamacao"] = bool(v.ABRIR_RECLAMACAO.search(norm)) and not slots["nega_reclamacao"]
    conhecida = next((c for c in voc.cidades if re.search(rf"\b{re.escape(c)}\b", norm)), None)
    if conhecida:
        slots["cidade"] = conhecida
    else:
        for m in RE_CIDADE.finditer(norm):
            cand = _cortar_cidade(m.group(1))
            if cand and cand.split()[0] not in NAO_E_CIDADE:
                slots["cidade"] = cand
                break
    if estado.aguardando == "cidade" and "cidade" not in slots:
        slots["cidade"] = re.sub(r"^(?:moro em|sou de|estou em|para|pra|em)\s+", "", norm).strip()
    if estado.aguardando == "valor_pedido" and "valor" not in slots:
        m = re.search(r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)", norm)
        if m:
            slots["valor"] = _reais(m.group(1))
    slots["texto_limpo"] = mascarar_dado_pessoal(mensagem.strip())[:300]
    return slots


def classificar(norm: str, slots: dict[str, Any]) -> str | None:
    if v.MANIPULACAO.search(norm):
        return "tentativa_manipulacao"
    if v.DADO_DE_TERCEIRO.search(norm):
        return "dado_de_terceiro"
    achadas = [nome for nome, p in v.PADROES_INTENCAO if nome != "saudacao" and p.search(norm)]
    ref, categoria = slots.get("referencia"), slots.get("categoria")
    for nome in achadas:
        if nome == "promocao":
            if ref:
                return "preco_produto"
            return "pagamento" if re.search(r"\b(pix|boleto|cartao|credito|debito)\b", norm) else "promocao"
        if nome == "preco_produto":
            return "preco_produto" if ref or not categoria else "busca_produto"
        if nome == "pagamento":
            return "preco_produto" if ref else "pagamento"
        if nome == "disponibilidade":
            return "disponibilidade" if ref or not categoria else "busca_produto"
        return nome
    if categoria or re.search(r"\b(procuro|busco|quero (um|uma)|indica\w*|recomenda\w*|opcoes|catalogo)\b", norm):
        return "busca_produto"
    if ref:
        return "disponibilidade" if re.search(r"\btem\b", norm) else "preco_produto"
    if slots.get("termo") and re.search(chr(92) + "btem" + chr(92) + "b", norm):
        return "busca_produto"
    if v.FORA_DO_ASSUNTO.search(norm):
        slots["assunto_geral"] = True
        return "fora_escopo"
    if re.search(v.PADROES_INTENCAO[-1][1].pattern, norm):
        return "saudacao"
    return None


def _trocar_assunto(estado: Estado, novo: str) -> None:
    """Guarda o assunto em andamento antes de mudar."""
    if estado.objetivo and estado.objetivo != novo:
        estado.pendentes.append({"objetivo": estado.objetivo, "coletados": estado.coletados,
                                 "declarados": estado.declarados, "aguardando": estado.aguardando})
        estado.pendentes = estado.pendentes[-3:]
        estado.coletados = {k: x for k, x in estado.coletados.items() if k in ("pedido", "protocolo")}
        estado.declarados = {k: x for k, x in estado.declarados.items() if k == "pedido_id"}
    estado.objetivo = novo
    estado.aguardando = None


def _aplicar_slots(estado: Estado) -> None:
    s = estado.slots
    if "pedido_id" in s:
        atual = estado.coletados.get("pedido")
        if atual and atual.get("pedido_id") != s["pedido_id"]:
            estado.coletados.pop("pedido", None)
        estado.declarar("pedido_id", s["pedido_id"])
    for campo in ("canal_compra", "estado_produto"):
        if campo in s and estado.objetivo in POSVENDA | {"garantia"}:
            estado.declarar(campo, s[campo])
    # "sim" ou "não" só vale como resposta quando a única coisa perguntada foi o estado do produto
    if (estado.aguardando == "dados_posvenda" and estado.objetivo in POSVENDA | {"garantia"}
            and estado.ultima_pergunta.get("campos") == ["estado_produto"] and "estado_produto" not in s):
        if s["afirmativo"] and not s["negativo"]:
            estado.declarar("estado_produto", "na embalagem original, sem sinais de uso")
        elif s["negativo"]:
            estado.declarar("estado_produto", "com sinais de uso ou sem a embalagem original")
    if estado.objetivo in ("defeito", "garantia") and estado.declarado("descricao_defeito") is None:
        so_dado = any(k in s for k in ("canal_compra", "estado_produto")) or bool(s.get("datas"))
        if (s.get("nova") == "defeito" and s["palavras"] >= 4) or (
                estado.aguardando == "dados_posvenda" and s["palavras"] >= 3 and not so_dado
                and not s["afirmativo"] and not s["negativo"]):
            estado.declarar("descricao_defeito", s["texto_limpo"])
    soltas = []
    for d, dica in s.get("datas", []):
        if dica and estado.objetivo in POSVENDA | {"garantia"}:
            estado.declarar(f"data_{dica}", d.isoformat())
        elif estado.objetivo in POSVENDA | {"garantia"}:
            soltas.append(d.isoformat())
    s["datas_soltas"] = soltas
    if estado.objetivo in ("preco_produto",):
        for k in ("forma", "parcelas"):
            if k in s:
                estado.coletados[k] = s[k]


def perceber(estado: Estado, mensagem: str) -> None:
    """Atualiza o estado com a mensagem do turno e define `estado.intencao`."""
    norm = normalizar(mensagem)
    estado.turno += 1
    estado.passos = []
    estado.permissao_registro = False
    estado.slots = extrair_slots(norm, mensagem, estado)
    s = estado.slots
    ag = ag_inicial = estado.aguardando
    nova = classificar(norm, s)
    estado.intencao = nova
    s["nova"] = nova

    # respostas a perguntas de sim ou não
    if ag == "retomar":
        if s["afirmativo"] and estado.pendentes:
            guardado = estado.pendentes.pop()
            estado.objetivo = guardado["objetivo"]
            estado.coletados = {**guardado["coletados"], **{k: x for k, x in estado.coletados.items() if k == "pedido"}}
            estado.declarados = {**guardado["declarados"], **estado.declarados}
            estado.aguardando = guardado["aguardando"]
            estado.intencao = estado.objetivo
            _aplicar_slots(estado)
            return
        estado.pendentes = []
        estado.aguardando = None
        estado.objetivo = None
        if s["negativo"]:
            estado.intencao = "retomada_recusada"
            return
        ag = None
    if ag == "confirmacao_registro":
        if s["afirmativo"] and not s["negativo"]:
            estado.permissao_registro = True
            estado.intencao = estado.objetivo
            return
        if s["negativo"]:
            estado.intencao = estado.objetivo
            s["cancelou"] = True
            return
        estado.coletados.pop("proposta", None)
        estado.aguardando = None
        ag = None
    if ag == "relato":
        if s["negativo"] and s["palavras"] <= 4:
            estado.intencao = estado.objetivo
            s["cancelou"] = True
            return
        s["relato"] = s["texto_limpo"]
        estado.intencao = estado.objetivo
        estado.permissao_registro = bool(estado.coletados.get("registro_explicito"))
        return

    # mensagem sem intenção própria, ou resposta a uma pergunta de dado: segue o assunto
    if estado.objetivo and ag in AGUARDA_DADO:
        familia_atual = FAMILIAS.get(estado.objetivo)
        fraca = nova in (None, "saudacao") or (
            estado.objetivo == "frete" and nova in ("preco_produto", "pagamento", "busca_produto"))
        mesma = nova in FAMILIAS and nova != "garantia" and FAMILIAS[nova] == familia_atual
        if fraca or mesma:
            if nova in POSVENDA and nova != estado.objetivo and familia_atual == "posvenda":
                estado.objetivo = nova  # o cliente refinou o pedido (era defeito, não devolução)
            estado.intencao = estado.objetivo
            _aplicar_slots(estado)
            _escolha_numerada(estado)
            return
    if nova is None:
        estado.intencao = "desconhecido"
        return
    if estado.objetivo and (ag is not None or ag_inicial is not None):
        _trocar_assunto(estado, nova)  # havia algo em andamento: guarda e oferece retomar depois
    else:
        estado.objetivo = nova
        estado.aguardando = None
        estado.coletados = {k: x for k, x in estado.coletados.items() if k in ("pedido", "protocolo")}
        estado.declarados = {k: x for k, x in estado.declarados.items() if k == "pedido_id"}
    if nova == "reclamacao" and s["abrir_reclamacao"]:
        estado.coletados["registro_explicito"] = True
        estado.permissao_registro = True
    if nova == "pedir_atendente" and not s["nega_atendente"]:
        estado.permissao_registro = True
    estado.intencao = nova
    _aplicar_slots(estado)


def _escolha_numerada(estado: Estado) -> None:
    """Resposta '2' a uma lista de modelos escolhe a opção correspondente."""
    opcoes = estado.coletados.get("opcoes")
    if estado.aguardando == "escolha_produto" and opcoes:
        m = re.fullmatch(r"\s*(?:opcao\s*)?(\d)\s*", normalizar(estado.slots.get("texto_limpo", "")))
        if m and 1 <= int(m.group(1)) <= len(opcoes):
            estado.slots["produto_id"] = opcoes[int(m.group(1)) - 1]["id"]
