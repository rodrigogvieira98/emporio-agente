"""Percepção: lê a mensagem, extrai dados e decide se o assunto continua, muda ou retoma."""
from __future__ import annotations

import re
from difflib import get_close_matches
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from .. import config
from ..dinheiro import para_centavos
from ..ferramentas.encaminhamento import mascarar_dado_pessoal
from ..ferramentas.pedido_demo import PADRAO_NUMERO, achar_numero
from ..texto import normalizar, tokens
from . import catalogo, sentimento
from . import vocabulario as v
from .estado import Estado

POSVENDA = {"devolucao", "troca_preferencia", "defeito"}
# o que sobrevive à troca de assunto: pedido consultado, produto em foco e a última lista mostrada
MANTER = ("pedido", "protocolo", "ultimo_produto", "ultimos_produtos", "ultima_busca", "ofertas_recusadas",
          "recomendado", "cidade_cliente", "dias_compra")
FAMILIAS = {
    "busca_produto": "produto", "preco_produto": "produto", "disponibilidade": "produto", "objecao_preco": "produto",
    "status_pedido": "posvenda", "previsao_entrega": "posvenda", "motivo_cancelamento": "posvenda", "devolucao": "posvenda", "troca_preferencia": "posvenda",
    "defeito": "posvenda", "garantia": "posvenda",
}
# esperando um dado: respostas curtas continuam o assunto
AGUARDA_DADO = {"pedido", "dados_posvenda", "referencia_produto", "escolha_produto", "cidade", "valor_pedido", "categoria",
                "cep"}
RE_CEP = re.compile(r"(?<!\d)(\d{5})-(\d{3})(?!\d)|\bcep\D{0,12}?(\d{5})(\d{3})(?!\d)")
UFS = ("ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg", "pa", "pb", "pr", "pe", "pi", "rj",
       "rn", "rs", "ro", "rr", "sc", "sp", "se", "to")

_PRECO = r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)(?:\s*(mil))?(?:\s*reais|\s*real)?"
RE_MAX = re.compile(r"\b(?:ate|no maximo|maximo|abaixo de|menos de|por ate)\s*" + _PRECO)
# "tenho 500 reais", "meu orçamento é 800": teto dito sem "até"; exige unidade para não confundir "tenho 2 filhos"
RE_TETO_IMPLICITO = re.compile(
    r"\b(?:so tenho|tenho|disponho de|orcamento (?:de|e|eh|seria|maximo de)|verba de|posso gastar|uns|cerca de|em torno de)\s*"
    r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)(?:\s*(mil))?(?:\s*reais|\s*real)?")
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
                "entrega", "envio", "casa", "loja", "la", "isso", "esse", "essa", "estoque", "vezes",
                # pergunta de prazo, preço ou condição nunca é nome de cidade
                "quantos", "quantas", "quanto", "quantidade", "que", "qual", "quais", "dias", "dia", "tempo", "prazo", "cada",
                "pix", "boleto", "cartao", "frete", "preco", "parcela", "parcelas", "dois", "duas", "tres", "hoje", "amanha"}
PALAVRAS_QUE_NAO_SAO_CIDADE = NAO_E_CIDADE | {"chega", "chegar", "demora", "demorar", "fica", "custa", "sai", "dela", "dele"}


def _cidade_plausivel(candidata: str) -> bool:
    """Nome de cidade tem poucas palavras e nenhuma de pergunta, prazo ou preço."""
    palavras = candidata.split()
    return 0 < len(palavras) <= 4 and not any(p in PALAVRAS_QUE_NAO_SAO_CIDADE for p in palavras)
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
    demo = achar_numero(resto)  # pedido de demonstração (PED-0001): não é pedido dos dados
    if demo:
        out["pedido_demo"] = demo
        resto = PADRAO_NUMERO.sub(" ", resto)
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


# Termos que marcam pagamento: com eles na frente (ou na frase), "3x" é parcelamento e não nome de produto.
TERMOS_PAGAMENTO = {"em", "ate", "de", "no", "na", "a", "ser", "pagar", "pago", "paga", "pagando", "pagamento", "parcelar",
                    "parcelado", "parcelada", "parcelo", "parcela", "parcelas", "vezes", "vez", "cartao", "credito",
                    "debito", "dividir", "dividido", "divido", "fazer", "faco", "fechar", "fecho", "levo", "juros",
                    "pix", "boleto", "financiar", "financiado", "passar", "passo"}


def _nome_de_produto(texto: str, m: re.Match[str], voc: catalogo.Vocabulario) -> bool:
    """"2X" é nome de produto ("Bass 2X") quando o catálogo o conhece e vem junto de marca, categoria ou outra palavra
    do nome. Vira parcelamento quando acompanha verbo ou termo de pagamento ("em 3x", "no cartão 3x") ou quando vem
    sozinho, sem nada antes (o produto em foco é o da conversa)."""
    if m.group(0).replace(" ", "") not in voc.df:
        return False
    antes = texto[:m.start()].split()
    if not antes:
        return False
    ultima = antes[-1]
    if ultima in TERMOS_PAGAMENTO:
        return False
    if ultima in voc.df or ultima in v.CATEGORIAS:
        return True
    return not any(t in TERMOS_PAGAMENTO for t in antes)  # palavra neutra ("o 2X"): só é nome sem pagamento na frase


# Números que não são produto: tempo desde a compra, número do pedido, final de telefone, percentual.
RE_NUMERO_NAO_PRODUTO = re.compile(
    r"\b\d+\s*(?:dias?|semanas?|mes(?:es)?|anos?|horas?|unidades?)\b"
    r"|\b(?:pedido|numero|nro|num)\s*(?:no\s*|n\s*)?#?\s*\d+\b|#\s*\d+\b"
    r"|\b(?:final|ultimos|terminad\w*|terminando)\s*(?:em|com|de|do telefone|e)?\s*\d{4}\b"
    r"|\b\d+(?:,\d+)?\s*(?:%|por cento)")


def _limpar_para_referencia(norm: str, voc: catalogo.Vocabulario) -> str:
    s = re.sub(r"\b\d{5}-\d{3}\b|\bcep\b\D{0,12}?\d{8}\b|\b\d{5}-?\d{3}\b", " ", norm)  # o CEP não faz parte do nome do produto
    s = RE_NUMERO_NAO_PRODUTO.sub(" ", s)
    s = RE_MAX.sub(" ", s)
    s = RE_MIN.sub(" ", s)
    s = RE_TETO_IMPLICITO.sub(lambda m: " " if re.search(r"\breais?\b|r\$|mil", m.group(0)) else m.group(0), s)
    s = RE_VALOR.sub(" ", s)
    s = RE_PARCELAS.sub(lambda m: m.group(0) if _nome_de_produto(s, m, voc) else " ", s)
    s = v.DATA.sub(" ", s)
    s = sentimento.FORTE.sub(" ", s)  # desabafo não é parte do nome do produto
    s = sentimento.MEDIO.sub(" ", s)
    return s


def _refs_de_comparacao(norm: str, voc: catalogo.Vocabulario) -> list[str]:
    """Dois produtos citados numa comparação: parte a frase nos separadores e lê a referência de cada trecho.
    O segundo trecho só com o modelo ("... e o C70") herda a marca do primeiro."""
    limpo = _limpar_para_referencia(norm, voc)
    refs: list[str] = []
    for parte in v.SEPARADOR_COMPARACAO.split(limpo):
        palavras = [t for t in tokens(parte) if t not in v.PALAVRAS_SOLTAS and t not in v.PALAVRAS_COMPARACAO
                    and (t in voc.df or re.search(r"\d", t))]
        if palavras and any(re.search(r"\d", t) or voc.df.get(t, 99) <= LIMITE_DISTINTIVO for t in palavras):
            refs.append(" ".join(palavras))
    if len(refs) >= 2 and len(refs[1].split()) == 1 and len(refs[0].split()) > 1:
        refs[1] = f"{refs[0].split()[0]} {refs[1]}"  # "Yamaha C40 e o C70"
    return refs[:2]


def _marcar_produto_nomeado(slots: dict[str, Any], voc: catalogo.Vocabulario) -> None:
    """A referência identifica um único produto do cadastro (marca e modelo, ou um modelo com número): o produto
    nomeado responde pelo próprio cadastro, antes de qualquer busca por categoria."""
    slots.pop("produto_nomeado", None)
    ref = set(tokens(slots.get("referencia") or ""))
    if not ref or not (len(ref) >= 2 or any(re.search(r"\d", t) for t in ref)):
        return
    if sum(ref <= nome for nome in voc.nomes) == 1:
        slots["produto_nomeado"] = True


def extrair_slots(norm: str, mensagem: str, estado: Estado) -> dict[str, Any]:
    slots: dict[str, Any] = {"palavras": len(norm.split())}
    slots.update(_numeros_de_pedido(norm, estado))
    m = RE_MAX.search(norm)
    if not m:
        t = RE_TETO_IMPLICITO.search(norm)
        # sem a unidade, "tenho 2 filhos" não é teto de preço
        m = t if t and (t.group(2) or re.search(r"\breais?\b|r\$", t.group(0))) else None
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
    for m in RE_PARCELAS.finditer(norm):
        # "Bass 2X" é nome de produto; "em 2x" é parcelamento, mesmo na mesma frase ("Bass 3X em 3x")
        if not _nome_de_produto(norm, m, voc):
            slots["parcelas"] = int(next(g for g in m.groups() if g))
            break
    if re.search(r"\bpix\b", norm):
        slots["forma"] = "pix"
    elif re.search(r"\bboleto\b", norm):
        slots["forma"] = "boleto"
    elif re.search(r"\bdebito\b", norm):
        slots["forma"] = "debito"
    elif re.search(r"\b(credito|cartao|parcel\w*)\b", norm) or "parcelas" in slots or re.search(
            r"\bquantas (vezes|parcelas)\b", norm):
        slots["forma"] = "credito"
    slots["cartao_generico"] = bool(re.search(r"\bcartao\b|\bcartoes\b", norm)) and not re.search(r"\b(debito|credito)\b", norm)
    sobra = [t for t in tokens(_limpar_para_referencia(norm, voc)) if t not in v.PALAVRAS_SOLTAS]
    corrigidos: dict[str, str] = {}
    for t in sobra:
        if t in v.CATEGORIAS:
            slots.setdefault("categoria", v.CATEGORIAS[t])
        elif len(t) >= 5 and t not in voc.df and not t.isdigit():
            parecida = get_close_matches(t, list(v.CATEGORIAS), n=1, cutoff=0.8)  # "gitarra", "violau", "bateira"
            if parecida:
                corrigidos[t] = parecida[0]
                slots.setdefault("categoria", v.CATEGORIAS[parecida[0]])
    conteudo = [t for t in sobra if t not in v.CATEGORIAS and t not in corrigidos
                and not any(p.fullmatch(t) for _, p in v.PADROES_INTENCAO)
                and not re.fullmatch(r"(comprar|comprei|gostei|interesse|interessado|interessada|fazer|quer)", t)]
    nomes = [t for t in conteudo if t in voc.df]
    if nomes:
        slots["termo"] = " ".join(nomes)
    # só vale como produto se algum termo identifica (modelo com número, ou marca rara no catálogo);
    # as demais palavras seguem junto, para que o que não existir resulte em "não encontrei"
    # número puro ("8", "10") nunca identifica produto sozinho: precisa de marca ou modelo junto
    com_letra = any(not t.isdigit() for t in conteudo)
    if any((re.search(r"\d", t) and (not t.isdigit() or com_letra)) or voc.df[t] <= LIMITE_DISTINTIVO for t in nomes):
        slots["referencia"] = " ".join(conteudo)
        slots["tem_modelo"] = True
    elif any(re.search(r"\d", t) and (not t.isdigit() or com_letra) for t in conteudo) and re.search(
            r"\b(preco\w*|custa\w*|valor|quanto|vende\w*|tem|disponivel|estoque)\b", norm):
        # modelo com número que o catálogo não conhece ("Stradivarius 1715"): a ferramenta diz se existe
        slots["referencia"] = " ".join(conteudo)
        slots["tem_modelo"] = True
    slots["desconhecidas"] = [t for t in conteudo if t not in voc.df and not re.search(r"\d", t)]
    _marcar_produto_nomeado(slots, voc)
    if slots.get("referencia"):
        # núcleo do nome: o que o catálogo conhece, o que tem número e o que o cliente escreveu com maiúscula
        # (nome próprio); o resto ("tá", "né", "disseram") é conversa. Só vale se identifica por modelo.
        capitalizadas = {normalizar(w) for w in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ-]*", mensagem)[1:]}
        nucleo = [t for t in conteudo if t in voc.df or re.search(r"\d", t) or t in capitalizadas]
        modelo = (any(re.search(r"\d", t) for t in nucleo) or sum(t in voc.df for t in nucleo) >= 2
                  or any(t in voc.df and voc.df[t] <= LIMITE_DISTINTIVO for t in nucleo))  # "Telecaster que tava..."
        if modelo:
            slots["referencia"] = " ".join(nucleo)
        _marcar_produto_nomeado(slots, voc)
    palavras_da_msg = set(tokens(norm))
    for c in voc.campanhas:
        chaves = [t for t in tokens(c) if t not in ("de", "da", "do", "dos", "das")]
        if chaves and all(t in palavras_da_msg for t in chaves):
            slots["termo_promocao"] = c
            break
    palavras = tokens(norm)
    fortes = sum(t in v.INGLES_FORTE for t in palavras)
    todas = sum(t in v.INGLES for t in palavras)
    slots["ingles"] = fortes >= 1 and todas >= 2 and not any(t in v.PORTUGUES_COMUM for t in palavras)
    if slots["ingles"]:
        slots["tema_ingles"] = next((tema for p, tema in v.TEMAS_INGLES if p.search(norm)), None)
        slots["agradecimento_ingles"] = bool(v.AGRADECIMENTO_INGLES.search(norm))
    if v.COMPARACAO.search(norm) or v.ENTRE_OU.search(norm):
        slots["comparar_refs"] = _refs_de_comparacao(norm, voc)
    camp = v.CAMPANHA_CITADA.search(norm)
    if camp:
        slots["promo_nome"] = camp.group(1)
        slots.setdefault("termo_promocao", camp.group(1))  # a ferramenta diz se há promoção ativa com esse nome
    dc = v.DESCONTO_CITADO.search(norm)
    if dc and re.search(r"\b(desconto|promocao|off|abatimento)\b", norm):
        slots["desconto_citado"] = int(dc.group(1))
    slots["pix_e_parcelas"] = slots.get("forma") == "pix" and (slots.get("parcelas") or 1) > 1
    formas_citadas = sum(bool(re.search(p, norm)) for p in (r"\bpix\b", r"\b(cartao|credito|debito)\b", r"\bboleto\b"))
    slots["combinar"] = bool(re.search(r"\b(metade|meio a meio|dividir|juntar|misturar|combin\w+|duas formas|dois cartoes|"
                                       r"parte no|uma parte)\b", norm)) and (formas_citadas >= 2 or "combin" in norm)
    slots["datas"] = _datas(norm)
    if v.CANAL_ONLINE.search(norm):
        slots["canal_compra"] = "online"
    elif v.CANAL_LOJA.search(norm):
        slots["canal_compra"] = "loja"
    if v.ESTADO_RUIM.search(norm):
        slots["estado_produto"] = "com sinais de uso ou sem a embalagem original"
    elif v.ESTADO_BOM.search(norm):
        slots["estado_produto"] = "na embalagem original, sem sinais de uso"
    slots["compra"] = bool(v.COMPRA.search(norm))
    slots["nivel"] = "iniciante" if v.NIVEL_INICIANTE.search(norm) else "outro" if v.NIVEL_OUTRO.search(norm) else None
    slots["orcamento_baixo"] = bool(v.ORCAMENTO_BAIXO.search(norm))
    slots["mau_uso"] = bool(v.MAU_USO.search(v.NEGA_MAU_USO.sub(" ", norm)))  # "sem queda" nega o gatilho
    slots["avaria"] = bool(v.AVARIA.search(norm))
    slots["demonstrativo"] = bool(v.DEMONSTRATIVO.search(norm))
    slots["os_dois"] = bool(v.OS_DOIS.search(norm))
    mq = v.QUANTIDADE.search(norm)
    if mq:
        bruto = mq.group(1) or mq.group(2)
        qtd = int(bruto) if bruto.isdigit() else v._NUM[bruto]
        if 2 <= qtd <= 20:
            slots["quantidade"] = qtd
    slots["desgaste"] = bool(v.DESGASTE.search(norm))
    slots["mais_barato"] = bool(v.EXTREMO_MIN.search(norm))
    dias = v.DIAS_DESDE_COMPRA.search(norm)
    if dias:  # "há 40 dias", "faz 2 meses": só o tempo desde a compra, para comparar com o prazo do manual
        unidade = {"d": 1, "s": 7, "m": 30}[dias.group(2)[0]]
        slots["dias_desde_compra"] = int(dias.group(1)) * unidade
    modalidade = next((m for m in catalogo.modalidades() if re.search(rf"\b{m}\b", norm)), None)
    if modalidade:
        slots["modalidade"] = modalidade.upper()
    slots["empresa_foco"] = [k for k, p in (("fundacao", v.EMPRESA_FUNDACAO), ("cnpj", v.EMPRESA_CNPJ),
                                            ("razao", v.EMPRESA_RAZAO)) if p.search(norm)]
    slots["bandeira"] = bool(v.DEBITO_BANDEIRA.search(norm))
    slots["pix_sobre_promocao"] = slots.get("forma") == "pix" and bool(v.PIX_SOBRE_PROMO.search(norm))
    slots["pergunta_prazo"] = bool(v.PERGUNTA_PRAZO.search(norm))
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
            if cand and cand.split()[0] not in NAO_E_CIDADE and _cidade_plausivel(cand):
                slots["cidade"] = cand
                break
    m_cep = RE_CEP.search(mensagem.lower())
    if m_cep:
        slots["cep"] = f"{m_cep.group(1) or m_cep.group(3)}-{m_cep.group(2) or m_cep.group(4)}"
    elif estado.aguardando == "cep" and re.fullmatch(r"\d{8}", mensagem.strip()):
        slots["cep"] = f"{mensagem.strip()[:5]}-{mensagem.strip()[5:]}"
    if slots.get("cidade") and slots.get("referencia"):
        # a cidade do destino ("entregam em Dourados") não faz parte do nome do produto
        fora = set(tokens(str(slots["cidade"]))) - set(voc.df)
        ref = " ".join(t for t in slots["referencia"].split() if t not in fora)
        if ref and ref != slots["referencia"]:
            slots["referencia"] = ref
            slots["desconhecidas"] = [t for t in slots.get("desconhecidas", []) if t not in fora]
    if slots.get("cidade"):
        ufs = "|".join(UFS)
        m_uf = re.search(rf"\b{re.escape(slots['cidade'])}\s*(?:/|-|,|\s)\s*({ufs})\b", norm)
        if m_uf:
            slots["uf"] = m_uf.group(1).upper()
    if estado.aguardando == "cidade" and "cidade" not in slots:
        resposta = re.sub(r"^(?:moro em|sou de|estou em|para|pra|em)\s+", "", norm).strip()
        # a resposta à pergunta da cidade é só o nome; outra pergunta ("e o preço dela no pix?") não vira cidade
        if _cidade_plausivel(resposta) and not any(p.search(norm) for n, p in v.PADROES_INTENCAO if n != "saudacao"):
            slots["cidade"] = resposta
    if estado.aguardando == "valor_pedido" and "valor" not in slots:
        m = re.search(r"\b(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\b", norm)
        if m:
            slots["valor"] = _reais(m.group(1))
    slots["texto_limpo"] = mascarar_dado_pessoal(mensagem.strip())[:300]
    return slots


PRIMARIAS_COM_SECUNDARIA = {"sem_info", "busca_produto", "preco_produto", "disponibilidade", "horario", "endereco", "contato",
                            "promocao", "garantia", "pagamento"}


def classificar(norm: str, slots: dict[str, Any]) -> str | None:
    """Intenção principal; se a mensagem traz uma segunda pergunta de informação simples, vai em `secundaria`."""
    nova = _classificar(norm, slots)
    slots["secundaria"] = None
    if nova == "sem_info":  # "onde fica e tem estacionamento?": responde o que sabe e depois a falta de dado
        info = [n for n, p in v.PADROES_INTENCAO if n in v.SECUNDARIAS and p.search(norm)]
        if info:
            slots["secundaria"] = "sem_info"
            return info[0]
        return nova
    if nova in PRIMARIAS_COM_SECUNDARIA:
        outras = [n for n, p in v.PADROES_INTENCAO if n in v.SECUNDARIAS and n != nova and p.search(norm)]
        if outras:
            slots["secundaria"] = outras[0]
    # preço de um produto citado + frete na mesma mensagem: responde o preço e depois o frete
    tem_ref = bool(slots.get("referencia") or slots.get("produto_id"))
    sem_preco_do_frete = re.sub(r"\b(?:quanto|valor|preco)\b(?:\s+\w+){0,3}?\s+(?:d[oae]s?\s+)?(?:frete|entrega|envio)\b", " ", norm)
    pede_preco = any(n == "preco_produto" and p.search(sem_preco_do_frete) for n, p in v.PADROES_INTENCAO)
    pede_frete = any(n == "frete" and p.search(norm) for n, p in v.PADROES_INTENCAO)
    if tem_ref and pede_preco and pede_frete and nova in ("frete", "preco_produto") and not slots.get("cep"):
        slots["secundaria"] = "frete"
        return "preco_produto"
    return nova


def _tema_sem_info(norm: str) -> str | None:
    """Tema que os dados da loja não cobrem (estacionamento, retirada, usados, nota fiscal, seguro)."""
    return next((tema for tema, p in v.SEM_INFO if p.search(norm)), None)


def _classificar(norm: str, slots: dict[str, Any]) -> str | None:
    if v.MANIPULACAO.search(norm) or ((v.AUTORIDADE.search(norm) or v.PEDIDO_INDEVIDO.search(norm))
                                      and not v.DADO_DE_TERCEIRO.search(norm)):
        return "tentativa_manipulacao"
    if v.CARRINHO.search(norm) and not v.DADO_DE_TERCEIRO.search(norm):
        return "carrinho"  # a Lia não mexe no carrinho: explica e manda o link
    tema = _tema_sem_info(norm)
    if tema == "extravio" and slots.get("pedido_id"):
        tema = None  # com o número do pedido, a consulta do pedido responde
    if tema and not slots.get("ingles") and not v.DADO_DE_TERCEIRO.search(norm):
        slots["tema_sem_info"] = tema
        return "sem_info"
    if slots.get("ingles"):
        return "encerramento" if slots.get("agradecimento_ingles") else "ingles"
    if len(slots.get("comparar_refs") or []) == 2:
        return "comparar"
    if v.PEDIDO_INSTRUCOES.search(norm):
        return "pedido_instrucoes"
    if v.DADO_DE_TERCEIRO.search(norm):
        return "dado_de_terceiro"
    achadas = [nome for nome, p in v.PADROES_INTENCAO if nome != "saudacao" and p.search(norm)]
    if v.FINAL_EXPLICITO.search(norm) and "status_pedido" not in achadas:
        achadas = [n for n in achadas if n != "contato"] or ["status_pedido"]  # "telefone termina em 8765" é o dado do pedido
    for flag, intencao in (("nega_atendente", "pedir_atendente"), ("nega_reclamacao", "reclamacao")):
        sobra = [n for n in achadas if n != intencao]
        if slots.get(flag) and sobra:  # "não quero atendente, só o preço": o pedido que sobra é o que vale
            achadas = sobra
    if slots.get("desgaste") and not any(n in ("devolucao", "troca_preferencia") for n in achadas):
        # corda arrebentada: desgaste natural (8.3), não acessório nem defeito
        achadas = ["garantia", *[n for n in achadas if n not in ("fora_escopo", "garantia", "defeito")]]
    if slots.get("modalidade") and "frete" not in achadas and not any(
            n in ("devolucao", "defeito", "troca_preferencia", "status_pedido") for n in achadas):
        achadas = ["frete", *achadas]  # "qual o prazo do PAC?": pergunta de envio, mesmo sem a palavra "frete"
    if (slots.get("quantidade") or slots.get("os_dois")) and "preco_produto" not in achadas and not any(
            n in ("devolucao", "defeito", "troca_preferencia", "status_pedido", "frete") for n in achadas):
        achadas = ["preco_produto", *achadas]  # "e se eu comprar dois?", "e os dois?": conta sobre o produto em foco
    ref, categoria = slots.get("referencia"), slots.get("categoria")
    if ref and categoria and slots.get("produto_nomeado"):
        categoria = None  # "o baixo Ibanez 2X": a categoria só situa o produto nomeado, que responde pelo cadastro
    procurando = re.search(r"\b(procur\w+|busc\w+|precis\w+|querend\w+|pensando em|interessad\w+)\b", norm)
    if categoria and not ref and slots.get("demonstrativo") and not procurando and "preco_max" not in slots:
        categoria = None  # "essa guitarra no pix": a categoria só nomeia o produto em foco, não pede uma busca
    if slots.get("cep") and ("frete" in achadas or not achadas or achadas[0] in ("preco_produto", "disponibilidade")):
        return "frete"  # CEP na mensagem: o cliente quer o frete (estimativa com produto e CEP)
    extremo = "min" if v.EXTREMO_MIN.search(norm) else "max" if v.EXTREMO_MAX.search(norm) else None
    if (extremo and not ref and not categoria
            and all(n in ("preco_produto", "disponibilidade", "pagamento") for n in achadas)):
        slots["extremo"] = extremo
        return "extremo_lista"  # sem lista na conversa, a regra cai na pergunta de categoria
    if achadas and achadas[0] == "reclamacao" and not v.RECLAMACAO_EXPLICITA.search(norm):
        # desabafo ("que absurdo") com pedido concreto: segue o pedido; sem pedido concreto continua reclamação
        if any(n in v.CONCRETAS for n in achadas[1:]):
            achadas = achadas[1:]
    if (achadas and achadas[0] in ("devolucao", "troca_preferencia", "defeito")
            and v.PERGUNTA_GERAL_TROCAS.search(norm) and not v.CASO_PROPRIO.search(norm)):
        return "info_trocas"  # pergunta geral: responde a política, sem abrir o fluxo do pedido
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
    if re.search(v.PEDIDO_GENERICO, norm) and not ref and not categoria:
        return "busca_produto"  # "quero um instrumento", "me ajuda a escolher": a Lia oferece as categorias
    if categoria or re.search(r"\b(procuro|busco|quero (um|uma)|indica\w*|recomenda\w*|opcoes|catalogo)\b", norm):
        return "busca_produto"
    if ref:
        return "disponibilidade" if re.search(r"\btem\b", norm) else "preco_produto"
    if slots.get("compra"):
        return "preco_produto"  # "quero comprar": o produto em foco, ou pergunta qual
    if slots.get("termo") and re.search(chr(92) + "btem" + chr(92) + "b", norm):
        return "busca_produto"
    if (re.search(r"\b(vende\w*|trabalha\w*|tem|existe\w*)\b", norm) and slots.get("desconhecidas")
            and not achadas and not ref and not categoria):
        return "fora_escopo"  # "vocês vendem boquilha?": item que o catálogo não conhece, pergunta de escopo
    if v.FORA_DO_ASSUNTO.search(norm):
        slots["assunto_geral"] = True
        return "fora_escopo"
    if re.search(v.PADROES_INTENCAO[-1][1].pattern, norm):
        resto = [t for t in tokens(v.PADROES_INTENCAO[-1][1].sub(" ", norm)) if t not in v.PALAVRAS_SOLTAS]
        if len(resto) >= 4:
            return None  # a saudação veio com um pedido que as regras não leram: não responde só "oi"
        return "saudacao"
    if v.ENCERRAMENTO.search(norm):
        return "encerramento"
    if (slots.get("parcelas") or slots.get("forma")) and slots["palavras"] <= 6 and not v.PAGAMENTO_GERAL.search(norm):
        return "preco_produto"  # "e em 12x", "e no pix": pergunta de condição do produto em foco, ou pede o produto
    if v.FINAL_EXPLICITO.search(norm) or slots.get("pedido_id") or slots.get("pedido_demo"):
        return "status_pedido"  # número do pedido ou final do telefone sozinhos: é o dado da consulta, nunca despedida
    if slots["palavras"] <= 3 and slots.get("afirmativo"):
        return "confirmacao_solta"
    if slots["palavras"] <= 2 and slots.get("negativo"):
        return "confirmacao_solta"
    return None


def _recusar_oferta(estado: Estado, oferta: str) -> None:
    """Oferta recusada não se repete no assunto (produto ou categoria)."""
    recusadas = list(estado.coletados.get("ofertas_recusadas") or [])
    if oferta not in recusadas:
        recusadas.append(oferta)
    estado.coletados["ofertas_recusadas"] = recusadas[-10:]


def _trocar_assunto(estado: Estado, novo: str) -> None:
    """Guarda o assunto em andamento antes de mudar."""
    sem_dado = estado.aguardando is not None and not estado.declarados and not any(
        k not in MANTER for k in estado.coletados)
    if estado.objetivo and estado.objetivo != novo:
        if not sem_dado:  # assunto sem nenhum dado do cliente não vira convite de retomar
            estado.pendentes.append({"objetivo": estado.objetivo, "coletados": estado.coletados,
                                     "declarados": estado.declarados, "aguardando": estado.aguardando})
            estado.pendentes = estado.pendentes[-3:]
        estado.coletados = {k: x for k, x in estado.coletados.items() if k in MANTER}
        estado.declarados = {k: x for k, x in estado.declarados.items() if k == "pedido_id"}
    estado.objetivo = novo
    estado.aguardando = None


def _aplicar_slots(estado: Estado) -> None:
    s = estado.slots
    if "pedido_demo" in s:
        estado.declarar("pedido_demo", s["pedido_demo"])
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
    if s.get("dias_desde_compra") and estado.objetivo in POSVENDA | {"garantia"}:
        # o prazo dito num turno vale nos seguintes do mesmo caso ("comprei faz 2 meses" ... "e o braço?")
        estado.coletados["dias_compra"] = {"dias": s["dias_desde_compra"], "turno": estado.turno}
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
    sentimento.registrar(estado, mensagem)  # rótulo do turno; só o tom depende dele
    estado.passos = []
    estado.permissao_registro = False
    estado.slots = extrair_slots(norm, mensagem, estado)
    s = estado.slots
    ag = ag_inicial = estado.aguardando
    nova = classificar(norm, s)
    # produto em foco: o último consultado ou, depois de uma lista, o primeiro dela
    ultimo = estado.coletados.get("ultimo_produto") or ((estado.coletados.get("ultima_busca") or {}).get("ids") or [None])[0]
    # "se eu pagar no pix tem mais desconto?" com um produto em foco: recalcula o produto (e lembra que o PIX não soma)
    mais_desconto = s.get("forma") == "pix" and bool(re.search(r"\b(mais|outro|extra|adicional) desconto|desconto (a mais|extra|adicional)", norm))
    if (nova == "pagamento" and ultimo and "referencia" not in s and (s.get("forma") or s.get("parcelas"))
            and (s["palavras"] <= 5 or mais_desconto or s.get("demonstrativo")) and not re.search(r"\b(quais|formas|aceita\w*|como)\b", norm)):
        nova = "preco_produto"  # "e no pix?" depois de um preço continua falando do mesmo produto
        s["produto_id"] = ultimo
    if nova is None and s.get("pergunta_prazo") and estado.ultimo_assunto == "frete":
        nova = "frete"  # "e quanto tempo demora?" depois de uma pergunta de frete
    if nova is None and v.PROXIMO_PASSO.search(norm):
        assunto = estado.objetivo or estado.ultimo_assunto
        if assunto in POSVENDA | {"garantia"}:
            nova = assunto  # "o que eu faço?" depois de uma orientação: o assunto de pós-venda continua
    # busca em andamento: "até 600 reais" refina a lista; "qual você recomenda?" usa a categoria e o teto já ditos
    ub = (estado.coletados.get("ultima_busca") or {}).get("args") or {}
    so_faixa = ("preco_max" in s or "preco_min" in s) and "referencia" not in s and "categoria" not in s
    pede_indicacao = bool(re.search(r"\b(recomend\w*|indic\w*|sugere\w*|sugest\w*|melhor opcao|qual (voce )?(escolheria|levaria))\b", norm))
    if (ub.get("categoria") and "referencia" not in s and "categoria" not in s
            and nova in (None, "preco_produto", "busca_produto", "disponibilidade", "confirmacao_solta")
            and (so_faixa or (pede_indicacao and nova in (None, "busca_produto")))):
        s["categoria"] = ub["categoria"]
        for k in ("preco_min", "preco_max"):
            if k not in s and ub.get(k) is not None:
                s[k] = ub[k]
        nova = "busca_produto"
    if nova == "promocao" and ultimo and "referencia" not in s and not s.get("termo_promocao") and s.get("demonstrativo"):
        nova = "preco_produto"  # "esse tá em promoção?": a promoção do produto em foco
        s["produto_id"] = ultimo
        s["pergunta_promocao"] = True
    if nova is None and estado.ultimo_assunto == "frete" and s.get("cidade") and s["palavras"] <= 6:
        nova = "frete"  # "e em <outra cidade>?" depois de uma pergunta de frete
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
            if (estado.coletados.get("proposta") or {}).get("origem") == "sentimento":
                estado.oferta_humano = "recusada"  # oferta de atendente recusada não volta na conversa
            estado.intencao = estado.objetivo
            s["cancelou"] = True
            return
        estado.coletados.pop("proposta", None)
        estado.aguardando = None
        ag = None
    pergunta_so_do_estado = estado.ultima_pergunta.get("campos") == ["estado_produto"]  # aí "não" é resposta
    if (ag == "pedido" or (ag == "dados_posvenda" and not pergunta_so_do_estado)) and s["negativo"]             and s["palavras"] <= 4:
        estado.intencao = "dado_recusado"  # "não" a um pedido de dados encerra o assunto, sem repetir o pedido
        estado.objetivo = None
        estado.aguardando = None
        return
    if ag == "parcelamento":  # "quer ver as parcelas?": o sim mostra, o não encerra, outra coisa segue o fluxo normal
        estado.aguardando = None
        resposta_curta = nova in (None, "confirmacao_solta") and not s["compra"]  # "quero esse" é compra, não o sim
        if resposta_curta and s["afirmativo"] and not s["negativo"] and estado.coletados.get("ultimo_produto"):
            estado.objetivo = estado.intencao = "parcelamento_produto"
            return
        if resposta_curta and s["negativo"] and s["palavras"] <= 4:
            _recusar_oferta(estado, f"parcelas:{estado.coletados.get('ultimo_produto')}")
            estado.objetivo = None
            estado.intencao = "confirmacao_solta"
            return
        ag = None
    if ag == "condicoes":  # "quer ver as condições dele?": o sim mostra o preço da opção que a Lia destacou
        estado.aguardando = None
        alvo = estado.coletados.get("recomendado")
        resposta_curta = nova in (None, "confirmacao_solta") and not s["compra"]
        if resposta_curta and alvo and s["afirmativo"] and not s["negativo"]:
            estado.objetivo = estado.intencao = "preco_produto"
            s["produto_id"] = alvo
            _aplicar_slots(estado)
            return
        if resposta_curta and alvo and s["negativo"] and s["palavras"] <= 4:
            _recusar_oferta(estado, f"condicoes:{alvo}")
            estado.objetivo = None
            estado.intencao = "confirmacao_solta"
            return
        ag = None
    if ag == "qualificacao":  # "é para iniciante? qual a faixa de preço?": a resposta refina a busca da mesma categoria
        qual = estado.coletados.get("qualificacao") or {}
        estado.aguardando = None
        informa = any(s.get(k) is not None for k in ("preco_max", "preco_min", "valor", "nivel")) or s["orcamento_baixo"]
        if qual.get("categoria") and informa and nova in (None, "confirmacao_solta", "busca_produto", "preco_produto"):
            if s.get("valor") is not None and "preco_max" not in s and "preco_min" not in s:
                s["preco_max"] = s["valor"]  # "uns 1000 reais" é o teto da faixa
            s.setdefault("categoria", qual["categoria"])
            s["qualificado"] = True
            estado.coletados["qualificada"] = True
            estado.objetivo = estado.intencao = "busca_produto"
            _aplicar_slots(estado)
            return
        if (s["negativo"] or v.SEM_PREFERENCIA.search(norm)) and nova in (None, "confirmacao_solta"):  # recusou: não volta
            _recusar_oferta(estado, f"qualificacao:{qual.get('categoria')}")
            estado.objetivo = None
            estado.intencao = "confirmacao_solta"
            return
        estado.objetivo = None  # perguntou outra coisa: a pergunta ficou sem resposta e não vira "retomar"
        ag = ag_inicial = None
    if ag == "retentar_parecidas":
        estado.aguardando = None
        if s["afirmativo"] and not s["negativo"]:
            estado.intencao = "retentar_parecidas"
            return
        estado.coletados.pop("parecidas", None)
        estado.objetivo = None
        if s["negativo"]:
            estado.intencao = "retomada_recusada"
            return
        ag = None
    if ag == "detalhe_trocas":  # "quer ver o que não entra em troca e o que a garantia não cobre?"
        estado.aguardando = None
        if s["afirmativo"] and not s["negativo"]:
            estado.intencao = "detalhe_trocas"
            return
        if s["negativo"]:
            estado.objetivo = None
            estado.intencao = "retomada_recusada"
            return
        estado.objetivo = None
        ag = None
    if ag == "relato" and nova == "pedir_atendente" and not s["nega_atendente"]:
        estado.aguardando = ag = None  # pedir um humano no meio do relato não é o relato: registra o pedido de atendente
        estado.objetivo = None
    if ag == "relato":
        if s["negativo"] and s["palavras"] <= 4:
            estado.intencao = estado.objetivo
            s["cancelou"] = True
            return
        s["relato"] = s["texto_limpo"]
        estado.intencao = estado.objetivo
        estado.permissao_registro = bool(estado.coletados.get("registro_explicito"))
        return

    if nova == "encerramento":  # agradecimento ou despedida: fecha a conversa, sem oferta e sem falha de entendimento
        estado.objetivo = None
        estado.aguardando = None
        estado.pendentes = []
        estado.falhas_seguidas = 0
        estado.incompreensoes = 0
        estado.ultima_pergunta = {}
        estado.coletados = {k: x for k, x in estado.coletados.items() if k in MANTER}
        estado.declarados = {k: x for k, x in estado.declarados.items() if k == "pedido_id"}
        estado.intencao = "encerramento"
        return

    # categoria nova no meio de uma pergunta de produto ("violão barato" quando se esperava o modelo): busca nova
    if nova == "busca_produto" and s.get("categoria") and "referencia" not in s and ag in ("escolha_produto", "referencia_produto"):
        estado.objetivo = None
        estado.aguardando = None
        estado.coletados.pop("opcoes", None)
        ag = ag_inicial = None

    # mensagem sem intenção própria, ou resposta a uma pergunta de dado: segue o assunto
    if estado.objetivo and ag in AGUARDA_DADO:
        familia_atual = FAMILIAS.get(estado.objetivo)
        fraca = nova in (None, "saudacao", "confirmacao_solta") or (
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
        estado.coletados = {k: x for k, x in estado.coletados.items() if k in MANTER}
        estado.declarados = {k: x for k, x in estado.declarados.items() if k == "pedido_id"}
    if nova == "reclamacao" and s["abrir_reclamacao"]:
        estado.coletados["registro_explicito"] = True
        estado.permissao_registro = True
    if nova == "pedir_atendente" and not s["nega_atendente"]:
        estado.permissao_registro = True
    estado.intencao = nova
    _aplicar_slots(estado)


def aplicar_rotulo(estado: Estado, rotulo: str) -> None:
    """Intenção escolhida pela reserva (já validada contra a lista fechada): segue como se as regras a tivessem achado."""
    executa = "fora_escopo" if rotulo == "assunto_geral" else rotulo
    s = estado.slots
    if rotulo == "assunto_geral":
        s["assunto_geral"] = True
    if estado.objetivo and estado.aguardando is not None:
        _trocar_assunto(estado, executa)
    else:
        estado.objetivo = executa
        estado.aguardando = None
        estado.coletados = {k: x for k, x in estado.coletados.items() if k in MANTER}
        estado.declarados = {k: x for k, x in estado.declarados.items() if k == "pedido_id"}
    estado.intencao = executa
    s["nova"] = executa
    _aplicar_slots(estado)


def _escolha_numerada(estado: Estado) -> None:
    """Resposta '2' a uma lista de modelos escolhe a opção correspondente."""
    opcoes = estado.coletados.get("opcoes")
    if estado.aguardando == "escolha_produto" and opcoes:
        m = re.fullmatch(r"\s*(?:opcao\s*)?(\d)\s*", normalizar(estado.slots.get("texto_limpo", "")))
        if m and 1 <= int(m.group(1)) <= len(opcoes):
            estado.slots["produto_id"] = opcoes[int(m.group(1)) - 1]["id"]
