"""Textos da Lia. Todo fato de loja vem de resultados de ferramenta, nunca de literais aqui.

Voz: a da persona em persona.yaml (acolhedora, clara, informal mas profissional). Sem travessão.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from .. import config
from ..dinheiro import formatar
from ..texto import normalizar
from . import expediente
from .estado import Estado

ROTULOS_ASSUNTO = {
    "devolucao": "a devolução", "troca_preferencia": "a troca por preferência", "defeito": "o produto com defeito",
    "status_pedido": "a consulta do pedido", "preco_produto": "o preço do produto", "disponibilidade": "a disponibilidade",
    "busca_produto": "a busca de produtos", "frete": "o frete", "reclamacao": "a reclamação", "garantia": "a garantia",
    "pagamento": "as formas de pagamento",
}
# Ambiguidade do manual, dita na voz da loja (a evidência fica no YAML do manual e nos testes).
AMBIGUIDADE_CLIENTE = {
    "marco_troca_preferencia": "de quando a contagem do prazo parte",
    "prazo_30_x_90": "como o prazo de troca por defeito e o da garantia legal se combinam",
}
ROTULOS_REGRA = {"devolucao": "devolução por arrependimento", "defeito": "troca por defeito",
                 "troca_preferencia": "troca por preferência"}
STATUS_PEDIDO = {"pending": "pendente", "confirmed": "confirmado", "shipped": "enviado", "delivered": "entregue",
                 "cancelled": "cancelado"}
SITUACAO = {"disponivel": "disponível", "esgotado": "esgotado no momento", "descontinuado": "descontinuado",
            "em_breve": "em breve (ainda não está à venda)"}
CAMPOS = {
    "canal_compra": "se a compra foi online ou na loja",
    "data_recebimento": "a data em que você recebeu o produto",
    "data_compra": "a data da compra",
    "estado_produto": "o estado do produto (se está na embalagem original e sem uso)",
    "descricao_defeito": "o que está acontecendo com o produto",
}
ROTULO_FORMA = {"pix": "PIX", "debito": "cartão de débito", "debit": "cartão de débito", "boleto": "boleto",
                "credit": "cartão de crédito", "credito": "cartão de crédito"}
# Frase natural do andamento do pedido (o código do status nunca aparece cru)
FRASE_STATUS = {"pending": "está pendente", "confirmed": "foi confirmado", "shipped": "foi enviado",
                "delivered": "foi entregue", "cancelled": "foi cancelado"}
CONFIRMA = "Responda sim ou não."
FECHAMENTO = "Posso ajudar em mais alguma coisa?"


# --- acesso aos resultados de ferramenta ---------------------------------------------------

def _condicoes(estado: Estado) -> dict[str, Any]:
    saida: dict[str, Any] = {}
    for p in estado.passos:
        if p.ferramenta == "consultar_politica" and p.resultado.estado == "ok":
            for s in p.resultado.dados["secoes"]:
                for c in s["condicoes"]:
                    saida[c["chave"]] = c["valor"]
    return saida


def _ambiguidades(estado: Estado) -> dict[str, dict[str, Any]]:
    saida: dict[str, dict[str, Any]] = {}
    for p in estado.passos:
        if p.ferramenta == "consultar_politica" and p.resultado.estado == "ok":
            for s in p.resultado.dados["secoes"]:
                for a in s["ambiguidades"]:
                    saida[a["id"]] = a
    return saida


def _dados(estado: Estado, ferramenta: str) -> dict[str, Any]:
    r = estado.ultimo(ferramenta)
    return r.dados if r is not None else {}


def _data_br(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "sem data"


def _lista(itens: list[str]) -> str:
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _aviso_expediente(estado: Estado) -> str:
    funcionamento = _condicoes(estado).get("horario.funcionamento")
    if not funcionamento:
        return ""
    sit = expediente.situacao(funcionamento, config.agora())
    if sit["aberto"] or not sit["retorno"]:
        return ""
    r = sit["retorno"]
    # o horário vem da regra de funcionamento; sem calendário de feriados, a promessa leva a ressalva
    ressalva = (" (pela regra de funcionamento; em feriado o horário pode mudar)"
                if "feriados_sem_calendario" in _ambiguidades(estado) else "")
    return aviso(estado, "fora_do_expediente",
                 f"No momento a loja está fora do expediente. A equipe volta {r['quando']} às {r['hora']}{ressalva}.",
                 valor=f"{r['quando']} {r['hora']}")


def aviso(e: Estado, id_: str, texto: str, valor: str = "", proprio: bool = False) -> str:
    """Aviso que acompanha uma resposta. Com a concisão ligada, não reaparece sem pedido do cliente.

    Reaparece se o valor mudou, ou se o aviso é parte do assunto e o cliente perguntou o mesmo assunto de novo
    (proprio=True). Aviso acessório (formato de preço, expediente) só volta se o valor mudar."""
    chave = f"aviso:{id_}"
    anterior = e.ja_informados.get(chave)
    contexto = str(e.coletados.get("ultimo_produto") or "") if proprio else ""  # aviso acessório não depende do produto
    repetido = anterior is not None and anterior["valor"] == valor and anterior.get("contexto", "") == contexto
    pediu_de_novo = repetido and proprio and anterior["intencao"] == (e.intencao or "")
    # mudou a ação pedida: o aviso do assunto é condição para interpretar a nova resposta
    acao_mudou = repetido and proprio and anterior["intencao"] != (e.intencao or "")
    omitir = e.concisao and repetido and not pediu_de_novo and not acao_mudou
    e.avisos_turno.append({"chave": chave, "valor": valor, "contexto": contexto,
                           "reapresentado": repetido and not pediu_de_novo and not acao_mudou, "omitido": omitir})
    return "" if omitir else texto


# --- textos --------------------------------------------------------------------------------

def saudacao(e: Estado, p: dict) -> str:
    nome = _condicoes(e).get("empresa.nome_fantasia")
    de = f" da {nome}" if nome else ""
    if e.concisao and e.ja_saudou:  # saudação no máximo uma vez por conversa
        txt = "Em que posso ajudar?"
    else:
        txt = f"Oi! Sou a Lia, assistente virtual{de}. Como posso te ajudar?"
    expediente_txt = _aviso_expediente(e)
    return f"{txt} {expediente_txt}".strip()


def horario(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    linhas = []
    for faixa in c.get("horario.funcionamento", []):
        dias = expediente.descrever_dias(faixa["dias"])
        linhas.append(f"- {dias}: fechado" if faixa.get("fechado") else
                      f"- {dias}: {faixa['abre']} às {faixa['fecha']}")
    if not linhas:
        return sem_dado(e, p)
    if c.get("horario.feriados_fechado"):
        linhas.append("- feriados: fechado")
    txt = "Nosso horário de funcionamento:\n" + "\n".join(linhas)
    if c.get("horario.datas_especiais_podem_estender"):
        txt += "\nEm datas especiais o horário pode ser estendido."
    if "feriados_sem_calendario" in _ambiguidades(e):
        a = aviso(e, "feriados_sem_calendario",
                  "Eu não tenho o calendário de feriados, então em feriado vale confirmar com a equipe.", proprio=True)
        txt += ("\n" + a) if a else ""
    sit = expediente.situacao(c["horario.funcionamento"], config.agora())
    if sit["aberto"]:
        txt += "\nAgora a loja está aberta."
    else:
        a = _aviso_expediente(e)
        txt += ("\n" + a) if a else ""
    return txt


def endereco(e: Estado, p: dict) -> str:
    end = _condicoes(e).get("empresa.endereco")
    if not end:
        return sem_dado(e, p)
    return (f"Estamos na {end['logradouro']}, {end['numero']}, bairro {end['bairro']}, "
            f"{end['cidade']} - {end['uf']}, CEP {end['cep']}.")


def contato(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    linhas = [f"- {rotulo}: {c[chave]}" for chave, rotulo in (
        ("contato.telefone_capa", "Telefone"), ("contato.whatsapp_secao_7", "WhatsApp"),
        ("contato.email_capa", "E-mail")) if chave in c]
    if not linhas:
        return sem_dado(e, p)
    return "Você pode falar com a loja por estes canais:\n" + "\n".join(linhas)


def pagamento(e: Estado, p: dict) -> str:
    """Responde o que foi perguntado: uma forma, só cartão ou parcelamento; a lista inteira só quando não há foco."""
    c = _condicoes(e)
    if "pagamento.pix_desconto_percentual" not in c:
        return sem_dado(e, p)
    forma = e.slots.get("forma")
    msg = normalizar(e.slots.get("texto_limpo", ""))
    if re.search(r"\b(parte|partes|combin\w+|mistur\w+|dividir|juntar|metade)\b", msg) or re.match(r"e\b", msg):
        forma = None  # combinar formas, ou "e no pix?" sem produto: a resposta é a lista inteira
    linhas: dict[str, str] = {"pix": f"PIX: {c['pagamento.pix_desconto_percentual']}% de desconto sobre o preço de tabela"}
    if c.get("pagamento.debito_a_vista"):
        linhas["debito"] = "Cartão de débito: à vista"
    if "pagamento.credito_parcelas_max" in c:
        sem = " sem juros" if c.get("pagamento.credito_sem_juros") else ""
        linhas["credito"] = f"Cartão de crédito: até {c['pagamento.credito_parcelas_max']}x{sem}"
    if c.get("pagamento.boleto_a_vista"):
        compensa = c.get("pagamento.boleto_compensacao_dias_uteis_max")
        linhas["boleto"] = "Boleto: à vista" + (f", compensação em até {compensa} dias úteis" if compensa else "")
    if forma == "credito" and e.slots.get("cartao_generico"):
        escolhidas = [k for k in ("debito", "credito") if k in linhas]
    elif forma in linhas:
        escolhidas = [forma]
    else:
        forma, escolhidas = None, list(linhas)
    if len(escolhidas) == 1:
        txt = linhas[escolhidas[0]] + "."
        if escolhidas[0] == "debito":  # "todas as bandeiras aceitas" está no texto da seção de pagamento
            bandeiras = _linha_do_manual(e, "bandeiras")
            if bandeiras:
                txt += " " + bandeiras.split("|")[-1].strip().rstrip(".") + "."
    else:
        txt = "Formas de pagamento:\n" + "\n".join(f"- {linhas[k]}" for k in escolhidas)
    if "credito" in escolhidas and "pagamento.parcelamento_faixas" in c:
        faixas = [f"{f['de']}x a {f['ate']}x: parcela mínima {formatar(f['parcela_minima_centavos'])}"
                  for f in c["pagamento.parcelamento_faixas"]]
        txt += "\nParcela mínima por faixa: " + "; ".join(faixas) + "."
        if "parcela_minima" in _ambiguidades(e) and "pagamento.credito_parcela_minima_tabela_centavos" in c:
            txt += aviso(e, "parcela_minima_duas_leituras",
                         f" A tabela de pagamento fala em {formatar(c['pagamento.credito_parcela_minima_tabela_centavos'])} "
                         "por parcela, então em casos de limite a equipe confirma.", proprio=True)
    combinar = c.get("pagamento.combinacao_formas_acima_centavos")
    if combinar and forma is None:
        txt += f"\nÉ possível combinar formas de pagamento (por exemplo PIX e cartão) em compras acima de {formatar(combinar)}."
    if forma is None or "credito" in escolhidas:
        return txt + "\nSe quiser, me diga o produto e o número de parcelas que eu calculo."
    return txt + "\nSe quiser, me diga o produto que eu calculo o valor."


def frete_info(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if "frete.gratis_acima_centavos" not in c:
        return sem_dado(e, p)
    prazo = c.get("frete.prazo_dias_uteis", {})
    base = c.get("frete.cidade_base", "a cidade da loja")
    txt = (f"Para {base}: frete grátis em pedidos a partir de {formatar(c['frete.gratis_acima_centavos'])}; abaixo "
           f"disso, taxa fixa de {formatar(c['frete.taxa_abaixo_centavos'])}. O valor considera as promoções e é "
           "contado antes do desconto do PIX.")
    if prazo:
        txt += f" Prazo de {prazo['min']} a {prazo['max']} dias úteis."
    mods = c.get("frete.outras_cidades_modalidades", [])
    if mods:
        txt += " Para outras cidades o envio é por " + _lista([m["nome"] for m in mods]) + ", com valor calculado pelo CEP."
    return txt + "\nMe diga a cidade e o valor do pedido que eu confirmo o frete."


def frete_prazo(e: Estado, p: dict) -> str:
    """Prazo de entrega da cidade informada, do manual; o valor do frete só depois de saber o valor do pedido."""
    c = _condicoes(e)
    prazo, base = c.get("frete.prazo_dias_uteis"), c.get("frete.cidade_base")
    if not prazo or not base:
        return sem_dado(e, p)
    if normalizar(p.get("cidade", "")) == normalizar(base):
        txt = f"Para {base}, o prazo é de {prazo['min']} a {prazo['max']} dias úteis."
    else:
        mods = c.get("frete.outras_cidades_modalidades", [])
        itens = [f"{m['nome']}: {m['prazo_dias_uteis']['min']} a {m['prazo_dias_uteis']['max']} dias úteis" for m in mods]
        txt = "Para outras cidades o prazo depende da modalidade: " + "; ".join(itens) + "." if itens else sem_dado(e, p)
    return txt + "\nSe quiser saber o valor do frete, me diga o valor do pedido."


def pedir_valor_pedido(e: Estado, p: dict) -> str:
    return "Para calcular o frete, qual é o valor aproximado do pedido?"


def frete_calculado(e: Estado, p: dict) -> str:
    r = _dados(e, "calcular_condicoes")
    f = r.get("frete", {})
    cidade = e.coletados.get("cidade", "").title()
    if e.coletados.get("uf"):
        cidade = f"{cidade}/{e.coletados['uf']}"
    prazo = f.get("prazo_dias_uteis")
    prazo_txt = f" Prazo de {prazo['min']} a {prazo['max']} dias úteis." if prazo else ""
    sit = f.get("situacao")
    if sit == "gratis":
        return f"Para {cidade}, com esse valor o frete é grátis.{prazo_txt}"
    if sit == "taxa":
        return f"Para {cidade}, o frete é uma taxa fixa de {formatar(f['taxa_centavos'])}.{prazo_txt}"
    mods = _condicoes(e).get("frete.outras_cidades_modalidades")
    extra = f" Os envios são por {_lista([m['nome'] for m in mods])}." if mods else ""
    return (f"Para {cidade}, o frete depende de cotação e é calculado pela equipe, e eu não consigo informar o valor "
            f"por aqui.{extra}{DICA_ESTIMATIVA}")


DICA_ESTIMATIVA = " Se me disser o produto e o CEP de entrega, eu faço uma estimativa de frete (simulação)."


def _destino(d: dict) -> str:
    return f"{d['cidade']}/{d['uf']}"


def frete_estimado(e: Estado, p: dict) -> str:
    d = _dados(e, "estimar_frete")
    partes = []
    for m in d["modalidades"]:
        prazo = m.get("prazo_dias_uteis")
        prazo_txt = f", prazo estimado de {prazo['min']} a {prazo['max']} dias úteis" if prazo else ""
        partes.append(f"{m['nome']}: {formatar(m['valor_centavos'])}{prazo_txt}")
    return (f"Para {_destino(d)}, com 1 unidade de {p['produto']}, o frete estimado (simulação) é: "
            + "; ".join(partes) + ". É uma estimativa do protótipo, não a tarifa de uma transportadora, "
            "e o valor final depende da cotação da nossa equipe.")


def frete_cidade_base(e: Estado, p: dict) -> str:
    d = _dados(e, "estimar_frete")
    f = d["frete"]
    prazo = f.get("prazo_dias_uteis")
    prazo_txt = f" Prazo de {prazo['min']} a {prazo['max']} dias úteis." if prazo else ""
    if f["situacao"] == "gratis":
        return f"Para {d['cidade']}, com esse produto o frete é grátis.{prazo_txt}"
    return f"Para {d['cidade']}, o frete é uma taxa fixa de {formatar(f['taxa_centavos'])}.{prazo_txt}"


def frete_cotacao_individual(e: Estado, p: dict) -> str:
    d = _dados(e, "estimar_frete")
    return (f"Para {_destino(d)}, o frete de {p['produto']} é de cotação individual: a nossa equipe faz o cálculo, "
            "e eu não informo valor por aqui.")


def frete_cep_indisponivel(e: Estado, p: dict) -> str:
    return ("Não consegui consultar esse CEP agora, então prefiro não chutar um valor de frete. "
            "Tente de novo em instantes.")


def frete_cep_nao_encontrado(e: Estado, p: dict) -> str:
    return "Não encontrei esse CEP. Confere os números e me manda de novo?"


def frete_pedir_cep(e: Estado, p: dict) -> str:
    return "Para estimar o frete, qual é o CEP de entrega?"


def frete_pedir_produto(e: Estado, p: dict) -> str:
    return "Para estimar o frete, qual é o produto? Me diga a marca e o modelo."


def _modalidade_com_prazo(m: dict[str, Any]) -> str:
    """Nome da modalidade que já traz parênteses recebe o prazo dentro deles, sem parênteses seguidos."""
    prazo = f"{m['prazo_dias_uteis']['min']} a {m['prazo_dias_uteis']['max']} dias úteis"
    nome = str(m["nome"])
    return f"{nome[:-1]}, {prazo})" if nome.endswith(")") else f"{nome} ({prazo})"


def frete_outra_cidade(e: Estado, p: dict) -> str:
    """Cidade fora da base do manual: a equipe calcula o frete; não pede o valor do pedido."""
    c = _condicoes(e)
    cidade = str(p.get("cidade", "")).title()
    if p.get("uf"):
        cidade = f"{cidade}/{p['uf']}"
    txt = (f"Para {cidade}, o frete depende de cotação e é calculado pela equipe, e eu não consigo informar o valor "
           "por aqui.")
    mods = c.get("frete.outras_cidades_modalidades", [])
    if mods:
        itens = [_modalidade_com_prazo(m) for m in mods]
        txt += " Os envios são por " + _lista(itens) + "."
    return txt + DICA_ESTIMATIVA


def fora_escopo(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if not c.get("escopo.somente_instrumentos"):
        return sem_dado(e, p)
    acessorios = c.get("escopo.acessorios_nao_vendidos", [])
    lista = f" ({_lista(acessorios)})" if acessorios else ""
    return (f"Aqui a gente trabalha só com instrumentos musicais, então não vendemos acessórios{lista}. "
            "Posso te ajudar a escolher um instrumento?")


def garantia_info(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    legal, defeito = c.get("regra.garantia_legal"), c.get("regra.defeito")
    if not legal:
        return sem_dado(e, p)
    txt = (f"Garantia legal: {legal['prazo_dias']} dias contra defeito de fabricação, contados do {legal['marco_inicial']} "
           "pelo cliente.")
    if defeito:
        txt += (f" Para troca por defeito, o prazo é de {defeito['prazo_dias']} dias {defeito['tipo_dias']} contados da "
                f"{defeito['marco_inicial']}.")
    if "prazo_30_x_90" in _ambiguidades(e):
        txt += aviso(e, "prazo_30_x_90",
                     " Como esses dois prazos se combinam depende de confirmação da nossa equipe.", proprio=True)
    fab = c.get("garantia.fabricante_prazo_meses")
    if fab:
        txt += (f" Os fabricantes costumam ter garantia própria, de {fab['min']} meses a {fab['max'] // 12} anos, "
                "descrita no certificado que acompanha o produto.")
    nao = c.get("garantia.nao_cobre")
    if nao:
        txt += " Não cobre: " + "; ".join(x[0].lower() + x[1:] for x in nao) + "."
    return txt + "\nSe estiver com problema em algum produto, me conta que eu te ajudo a abrir a solicitação."


def _prazo(regra: dict[str, Any]) -> str:
    txt = f"{regra['prazo_dias']} dias"
    if regra.get("tipo_dias") not in (None, "nao_informado"):
        txt += f" {regra['tipo_dias']}"
    marco = {"compra": "da compra", "recebimento": "do recebimento"}.get(regra.get("marco_inicial"))
    return f"{txt}, contados {marco}" if marco else txt


def trocas_info(e: Estado, p: dict) -> str:
    """Resumo curto de troca, devolução e garantia: uma linha por regra. Exclusões ficam para o 'sim'."""
    c = _condicoes(e)
    amb = _ambiguidades(e)
    arrep, defeito, pref = c.get("regra.arrependimento"), c.get("regra.defeito"), c.get("regra.preferencia")
    legal = c.get("regra.garantia_legal")
    linhas = []
    if arrep:
        online = " (compra online)" if arrep.get("aplica_a") == "compra_online" else ""
        linhas.append(f"- Arrependimento: {_prazo(arrep)}{online}.")
    if defeito:
        linhas.append(f"- Defeito: {_prazo(defeito)}.")
    if pref:
        if "marco_troca_preferencia" in amb:
            linhas.append(f"- Preferência: {pref['prazo_dias']} dias; de quando a contagem parte depende de confirmação da nossa equipe.")
        else:
            linhas.append(f"- Preferência: {_prazo(pref)}.")
    if legal:
        extra = ""
        if defeito and "prazo_30_x_90" in amb:
            extra = f"; como convive com os {defeito['prazo_dias']} dias do defeito, a equipe confirma"
        linhas.append(f"- Garantia legal: {_prazo(legal)}{extra}.")
    if not linhas:
        return sem_dado(e, p)
    return ("Troca, devolução e garantia:\n" + "\n".join(linhas)
            + "\nA equipe confirma se o seu caso se enquadra."
            + "\nQuer ver o que não entra em troca e o que a garantia não cobre? Se preferir, posso verificar um pedido seu.")


def trocas_detalhe(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    partes = []
    nao = c.get("trocas.itens_nao_elegiveis")
    if nao:
        partes.append("Não entram em troca: " + "; ".join(x[0].lower() + x[1:] for x in nao) + ".")
    cobre = c.get("garantia.nao_cobre")
    if cobre:
        partes.append("A garantia não cobre: " + "; ".join(x[0].lower() + x[1:] for x in cobre) + ".")
    fab = c.get("garantia.fabricante_prazo_meses")
    if fab:
        partes.append(f"Os fabricantes costumam ter garantia própria, de {fab['min']} meses a {fab['max'] // 12} anos, "
                      "descrita no certificado do produto.")
    if not partes:
        return sem_dado(e, p)
    return "\n".join(partes) + "\nSe tiver um caso seu, me diga que quer trocar ou devolver e o número do pedido."


def busca(e: Estado, p: dict) -> str:
    # a busca principal não leva "limite"; a consulta de apoio da recomendação (limite 1) não é a lista mostrada
    r = next((x.resultado for x in reversed(e.passos)
              if x.ferramenta == "buscar_produtos" and "limite" not in x.args), None)
    if r is None:
        return falha_ferramenta(e, p)
    if r.estado == "vazio":
        if p.get("sem_categoria"):
            return ("Não encontrei esse tipo de instrumento à venda no catálogo hoje. "
                    f"Temos {_lista(p['sem_categoria'])}. Qual deles te interessa?")
        if r.motivo == "categoria_inexistente":
            return "Não encontrei essa categoria no nosso catálogo. Quer tentar outro tipo de instrumento?"
        return ("Não encontrei produtos disponíveis com esses filtros agora. "
                "Quer tentar outra faixa de preço ou outro modelo?")
    d = r.dados
    linhas = []
    for i in d["itens"]:
        promo = f" (em promoção: {i['promocao']['percentual']}% de desconto)" if i["promocao"] and \
            not i["promocao"].get("ambigua") else ""
        linhas.append(f"- {i['nome']}: {formatar(i['preco_centavos'])}{promo}")
    mostrados = len(d["itens"])
    n = d["total_encontrado"]
    cab = (f"Encontrei {n} " + ("opção disponível" if n == 1 else "opções disponíveis")
           + (f", do menor para o maior preço (mostrando {mostrados}):" if d["total_encontrado"] > mostrados else ":"))
    a = aviso(e, "valores_de_tabela", "Os valores são o preço de tabela.")
    fecho = "Quer ver as condições de algum deles?"
    rec = p.get("recomendacao")
    if p.get("qualificar"):  # uma pergunta só, sobre nível, uso ou orçamento
        fecho = QUALIFICACAO
    elif rec:
        fecho = f"Quer ver as condições do {rec['nome']}?" if p.get("oferta_condicoes") else ""
    sugestao = ""
    if rec:
        motivo = MOTIVO_RECOMENDACAO[rec["motivo"]].format(percentual=rec.get("percentual"))
        if rec.get("orcamento"):
            motivo += " e cabe no orçamento que você informou"
        sugestao = f"Minha sugestão: {rec['nome']}, porque {motivo}."
    corpo = cab + "\n" + "\n".join(linhas) + "\n" + (a + " " if a else "")
    return (corpo + " ".join(x for x in (sugestao, fecho) if x)).rstrip()


# Lead: a pergunta de qualificação é uma só; o motivo da sugestão vem sempre do dado (nunca "o melhor" ou "o mais vendido").
QUALIFICACAO = "Para eu indicar melhor, é para quem está começando ou já toca, e qual a faixa de preço?"
MOTIVO_RECOMENDACAO = {
    "iniciante": "o catálogo o descreve como indicado para iniciantes",
    "promocao": "está em promoção ativa, com {percentual}% de desconto",
    "menor_preco": "é a opção de menor preço desta lista",
}


def pedir_categoria(e: Estado, p: dict) -> str:
    cats = p.get("categorias") or []
    if cats:
        return (f"Temos {_lista(cats)}. Qual tipo de instrumento te interessa? "
                "Pode dizer também uma marca ou uma faixa de preço.")
    return "Que tipo de instrumento você procura? Pode dizer também uma marca ou uma faixa de preço."


def pedir_produto(e: Estado, p: dict) -> str:
    return "Qual produto? Me diga a marca e o modelo."


def produto_nao_encontrado(e: Estado, p: dict) -> str:
    return "Não encontrei esse produto. Pode me dizer a marca e o modelo do jeito que está no anúncio?"


def escolha_produto(e: Estado, p: dict) -> str:
    opcoes = e.coletados.get("opcoes", [])
    linhas = [f"{i}) {o['nome']}" for i, o in enumerate(opcoes, start=1)]
    return "Achei mais de um modelo parecido:\n" + "\n".join(linhas) + "\nQual deles? Pode responder com o número."


def escolha_produto_curta(e: Estado, p: dict) -> str:
    return "Em qual desses modelos? Responda com o número da lista."


def objecao_preco(e: Estado, p: dict) -> str:
    """"Tá caro": só o que existe no dado (opção mais barata, promoção ativa, parcelas), sem desconto inventado."""
    if p.get("sem_oferta"):
        return ("Entendo. Os valores que eu informo são os do catálogo e os das promoções ativas, "
                "e eu não consigo oferecer desconto fora disso.")
    partes = ["Entendo."]
    barato = p.get("mais_barato")
    if barato:
        partes.append(f"Uma opção mais em conta em {p['categoria']} é o {barato['nome']}, por "
                      f"{formatar(barato['preco_centavos'])} (preço de tabela).")
    else:
        partes.append(f"O {p['produto']} já é a opção de menor preço em {p['categoria']}.")
    if p.get("percentual"):
        partes.append(f"O {p['produto']} está em promoção ativa, com {p['percentual']}% de desconto.")
    if p.get("oferta_parcelas"):
        partes.append("Quer ver as parcelas no cartão de crédito?")
    return " ".join(partes)


def vou_pensar(e: Estado, p: dict) -> str:
    if p.get("produto"):
        return f"Claro, sem pressa. Deixo aqui o link do {p['produto']} para você ver com calma."
    return "Claro, sem pressa. Quando quiser, é só me chamar."


def produto_indisponivel(e: Estado, p: dict) -> str:
    d = _dados(e, "ver_produto")
    nome, situacao = d["nome"], d["situacao_venda"]
    if situacao == "descontinuado":
        txt = f"{nome} foi descontinuado e não faz mais parte do catálogo."
    elif situacao == "em_breve":
        txt = f"{nome} ainda não está à venda, então não consigo confirmar disponibilidade."
    else:
        txt = f"{nome} está esgotado no momento. Não consigo informar previsão de reposição."
    r = e.ultimo("buscar_produtos")
    if r is not None and r.estado == "ok":
        linhas = [f"- {i['nome']}: {formatar(i['preco_centavos'])}" for i in r.dados["itens"]]
        txt += (f"\nOpções disponíveis na mesma categoria ({d['categoria']}), preço de tabela:\n" + "\n".join(linhas)
                + "\nQuer ver as condições de algum deles?")
    elif r is not None and r.estado == "vazio":
        txt += f" Também não encontrei alternativas disponíveis em {d['categoria']} agora."
    else:  # a consulta falhou: a oferta só existe porque um "sim" executa a busca de novo
        txt += f" Não consegui consultar opções parecidas agora. Quer que eu tente de novo? {CONFIRMA}"
    return txt


def promocoes(e: Estado, p: dict) -> str:
    r = e.ultimo("listar_promocoes")
    if r is None:
        return falha_ferramenta(e, p)
    if r.estado == "vazio":
        termo = r.dados.get("termo")
        if termo:
            return (f"A promoção {termo.title()} não está ativa agora, então não posso prometer esse "
                    "desconto. Se quiser, mostro as promoções que estão ativas.")
        return "Não há nenhuma promoção ativa agora."
    linhas = []
    for i in r.dados["promocoes"]:
        extra = "" if i["situacao_venda"] == "disponivel" else f" ({SITUACAO.get(i['situacao_venda'])})"
        if i["conflito"]:
            linhas.append(f"- {i['produto_nome']}: {i['percentual']}% de desconto, preço original "
                          f"{formatar(i['original_centavos'])}; há mais de uma promoção ativa e a equipe confirma o valor{extra}")
        else:
            linhas.append(f"- {i['produto_nome']}: de {formatar(i['original_centavos'])} por "
                          f"{formatar(i['final_centavos'])} ({i['percentual']}% de desconto){extra}")
    a = aviso(e, "pix_nao_soma", "O desconto do PIX não soma com preço promocional.")
    return "Promoções ativas:\n" + "\n".join(linhas) + (("\n" + a) if a else "")


def recusa_manipulacao(e: Estado, p: dict) -> str:
    pix = _condicoes(e).get("pagamento.pix_desconto_percentual")
    extra = f" e o desconto de {pix}% no PIX" if pix else ""
    return ("Não consigo atender esse pedido. Os descontos que eu informo são só os das promoções ativas"
            f"{extra}. Quer ver as promoções ativas?")


def recusa_dado_de_terceiro(e: Estado, p: dict) -> str:
    return ("Não passo dados pessoais de clientes, como telefone, e-mail, endereço ou nome. Se o pedido é seu, posso "
            "consultar o andamento com o número do pedido e os 4 últimos dígitos do telefone cadastrado.")


def fora_escopo_geral(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if not c.get("escopo.somente_instrumentos"):
        return sem_dado(e, p)
    return ("Esse assunto foge do que eu consigo ajudar por aqui, já que a loja trabalha só com instrumentos "
            "musicais. Posso ajudar com produtos, preços, pedidos, trocas e devoluções?")


def disponibilidade(e: Estado, p: dict) -> str:
    d = _dados(e, "ver_produto")
    txt = f"{d['nome']}: {SITUACAO.get(d['situacao_venda'], d['situacao_venda'])}, conforme o estoque agora."
    return f"{txt} Preço de tabela: {formatar(d['preco_centavos'])}." if d.get("preco_centavos") else txt


def preco(e: Estado, p: dict) -> str:
    d = _dados(e, "calcular_condicoes")
    nome = d["produto_nome"]
    partes = []
    if d.get("percentual"):
        a = aviso(e, "pix_nao_soma", "O desconto do PIX não soma com promoção.")
        partes.append(f"{nome}: preço de tabela {formatar(d['original_centavos'])}, promoção de {d['percentual']}% "
                      f"e preço final {formatar(d['final_centavos'])}." + (" " + a if a else ""))
    elif d["forma"] == "pix":
        partes.append(f"{nome}: preço de tabela {formatar(d['original_centavos'])}. No PIX "
                      f"({d.get('pix_percentual')}% de desconto) fica {formatar(d['final_centavos'])}.")
    else:
        partes.append(f"{nome}: preço de tabela {formatar(d['original_centavos'])}.")
    if d["forma"] == "credito":
        partes.append(f"No crédito em {d['parcelas']}x, cada parcela fica em {formatar(d['parcela_centavos'])}.")
        if d["permitido"] == "sim":
            partes.append("Esse parcelamento atende a parcela mínima da loja.")
        elif d["permitido"] == "nao":
            partes.append("Esse parcelamento não atende a parcela mínima da loja.")
        else:
            partes.append(f"Esse parcelamento precisa de confirmação da nossa equipe: a parcela mínima é "
                          f"{formatar(d['minimo_tabela_centavos'])} em uma regra e {formatar(d['minimo_faixa_centavos'])} "
                          f"na faixa de {d['parcelas']}x. Quer que eu registre a dúvida para eles? {CONFIRMA}")
    if d.get("situacao_venda") not in (None, "disponivel"):
        partes.append(f"Atenção: o produto está {SITUACAO.get(d['situacao_venda'])}.")
        return " ".join(partes)
    if p.get("valor_frete"):  # uma condição que ajuda por vez, e só uma vez na conversa
        partes.append(f"Em {str(p['valor_frete']).title()}, o frete desse produto é grátis.")
        e.valores_citados.append("frete_gratis")
    if p.get("compra"):  # o passo seguinte é o botão: a Lia nunca adiciona nada sozinha
        partes.append("Para comprar, toque em Adicionar ao carrinho; eu não adiciono nada por você.")
    elif d["forma"] != "credito" and p.get("oferta_parcelas"):
        partes.append("Quer ver as parcelas no cartão de crédito?")
    return " ".join(partes)


def preco_promocao_conflitante(e: Estado, p: dict) -> str:
    return ("Esse produto aparece com mais de uma promoção ativa, e eu não vou chutar o preço. "
            f"Quer que eu registre para a equipe confirmar o valor? {CONFIRMA}")


def item_nao_elegivel(e: Estado, p: dict) -> str:
    return (f"Esse item não entra em troca: {p['trecho']}. "
            "Se o seu caso for outro, é só me contar.")


def pedir_pedido(e: Estado, p: dict) -> str:
    regra = e.coletados.get("regra")
    if regra and p.get("com_regra") and e.objetivo in ROTULOS_REGRA:
        v = regra["valor"]
        online = ", e vale para compra online" if v.get("aplica_a") == "compra_online" else ""
        return (f"Pela regra da loja, {ROTULOS_REGRA[e.objetivo]}: {_prazo(v)}{online}. A equipe confirma se o seu "
                "caso se enquadra. Para consultar o pedido, me diga o número do pedido e os 4 últimos dígitos do "
                "telefone cadastrado.")
    if p.get("tem_pedido") and not p.get("tem_final"):
        return "Agora preciso dos 4 últimos dígitos do telefone cadastrado no pedido."
    if p.get("tem_final") and not p.get("tem_pedido"):
        return "Qual é o número do pedido?"
    return "Para consultar o pedido, me diga o número do pedido e os 4 últimos dígitos do telefone cadastrado."


def pedido_negado(e: Estado, p: dict) -> str:
    return ("Não consegui validar esse pedido com os dados informados. Confira o número do pedido e os 4 últimos "
            "dígitos do telefone cadastrado e me mande de novo.")


def pedido_negado_limite(e: Estado, p: dict) -> str:
    return ("Ainda não consegui validar o pedido e, por segurança, vou parar de tentar por aqui. "
            f"Quer que eu peça para um atendente te ajudar? {CONFIRMA}")


def status_pedido(e: Estado, p: dict) -> str:
    ped = e.coletados["pedido"]
    itens = ", ".join(f"{i['quantidade']}x {i['nome']}" for i in ped["itens"])
    frase = FRASE_STATUS.get(ped["status"], f"está com o andamento {STATUS_PEDIDO.get(ped['status'], ped['status'])}")
    forma = _forma_pedido(ped["forma_pagamento"])
    pago = f" ({forma})" if forma else ""
    txt = (f"Pedido {ped['pedido_id']} {frase}.\nItens: {itens}.\n"
           f"Total do pedido: {formatar(ped['total_gravado_centavos'])}{pago}.")
    if ped.get("rastreio"):
        txt += f"\nCódigo de rastreio: {ped['rastreio']}."
    if ped.get("previsao"):
        txt += f"\nPrevisão de entrega: {_data_br(ped['previsao'])}."
        if ped.get("previsao_vencida"):
            txt += " Essa data já passou e o pedido ainda não consta como entregue."
    if ped.get("nota"):
        txt += f"\nObservação do pedido: {ped['nota']}."
    if p.get("oferta") == "previsao_vencida":
        txt += f"\nQuer que eu registre para a equipe verificar o atraso? {CONFIRMA}"
    return txt


def status_pedido_demo(e: Estado, p: dict) -> str:
    d = e.coletados["pedido_demo"]
    itens = ", ".join(f"{i['quantidade']}x {i['nome']}" for i in d["itens"])
    return (f"Pedido {d['numero']}: feito no site. {d['aviso']}\n"
            f"Itens: {itens}.\n{d['frete_linha']}.\n{d['total_rotulo']}: {formatar(d['total_gravado_centavos'])}.")


def pedido_demo_negado(e: Estado, p: dict) -> str:
    return ("Não encontrei esse pedido nesta conversa. Ele só abre no mesmo navegador em que foi feito. "
            "Confira o número, que começa com PED-.")


def _forma_pedido(bruto: str) -> str:
    """Forma de pagamento em português; código desconhecido não aparece cru."""
    if bruto.startswith("credit_"):
        return f"cartão de crédito em {bruto.split('_')[1]}"
    return ROTULO_FORMA.get(bruto, "")


def _nota_prazo_defeito(e: Estado) -> str:
    """Troca por defeito: o prazo conta da compra, e a data do pedido (do sistema) diz de quando."""
    ped, regra = e.coletados.get("pedido") or {}, (e.coletados.get("regra") or {}).get("valor")
    if e.objetivo != "defeito" or not ped.get("data_pedido") or not regra:
        return ""
    return (f" O pedido é de {_data_br(ped['data_pedido'])}, dentro do prazo de {regra['prazo_dias']} dias "
            "para troca por defeito.")


def pedir_dados_posvenda(e: Estado, p: dict) -> str:
    ped = e.coletados["pedido"]
    campos = [CAMPOS.get(c, c) for c in p["campos"]]
    achei = aviso(e, "pedido_encontrado", f"Encontrei o pedido {ped['pedido_id']}.", str(ped["pedido_id"]))
    return f"{achei}{_nota_prazo_defeito(e)} Para organizar sua solicitação, me conta: {_lista(campos)}.".strip()


def propor_posvenda(e: Estado, p: dict) -> str:
    ped, regra = e.coletados["pedido"], e.coletados["regra"]["valor"]
    itens = ", ".join(f"{i['quantidade']}x {i['nome']}" for i in ped["itens"])
    consta = (f"pedido {ped['pedido_id']}, status {STATUS_PEDIDO.get(ped['status'], ped['status'])}, {itens}, "
               f"total gravado {formatar(ped['total_gravado_centavos'])}")
    if ped.get("data_pedido"):
        consta += f", feito em {_data_br(ped['data_pedido'])}"
    if ped.get("previsao"):
        consta += f", previsão de entrega {_data_br(ped['previsao'])}"
    decl = []
    rotulo = {"canal_compra": "compra {}", "data_recebimento": "recebimento em {}", "data_compra": "compra em {}",
              "estado_produto": "produto {}", "descricao_defeito": "problema: {}"}
    for c in regra["dados_necessarios"]:
        v = e.declarado(c)
        if v is None:
            continue
        v = _data_br(v) if c.startswith("data_") else v
        decl.append(rotulo.get(c, "{}").format(v))
    prazo = regra.get("prazo_dias")
    condicao = f"{prazo} dias {regra['tipo_dias']}" if regra.get("tipo_dias") not in (None, "nao_informado") else f"{prazo} dias"
    marco = regra.get("marco_inicial")
    quando = {"compra": "da compra", "recebimento": "do recebimento"}
    marco_txt = ("sem informar de quando conta" if marco == "nao_informado"
                 else f"contados a partir {quando.get(marco, 'do marco inicial')}")
    aplica = " e vale para compra online" if regra.get("aplica_a") == "compra_online" else ""
    exigido = f" Produto: {regra['estado_exigido']}." if regra.get("estado_exigido") else ""
    amb = e.coletados["regra"].get("ambiguidades_ids", [])
    pontos = [AMBIGUIDADE_CLIENTE[i] for i in amb if i in AMBIGUIDADE_CLIENTE]
    nota = f" Depende de confirmação da nossa equipe: {pontos[0]}." if pontos else ""
    return (
        "Resumo da sua solicitação:" + _nota_prazo_defeito(e) + "\n"
        f"1) O que consta no seu pedido: {consta}.\n"
        f"2) O que você me informou (não verificado): {'; '.join(decl)}.\n"
        f"3) O que a equipe confirma: se o seu caso se enquadra na regra da loja ({condicao}, {marco_txt}{aplica}).{exigido}"
        f"{nota} Eu não consigo garantir a elegibilidade, a decisão é da equipe.\n"
        f"Posso registrar essa solicitação para a equipe? {CONFIRMA}")


def reclamacao_empatia(e: Estado, p: dict) -> str:
    return ("Sinto muito pelo que aconteceu. Quero que a equipe veja o seu caso com atenção. "
            f"Posso registrar uma reclamação com o que você me contou? {CONFIRMA}")


def pedir_relato(e: Estado, p: dict) -> str:
    return ("Entendo. Me conta em poucas palavras o que aconteceu? "
            "Não precisa passar telefone nem e-mail, a equipe já tem como falar com você.")


def negacao_reclamacao(e: Estado, p: dict) -> str:
    return "Tudo bem, não vou abrir reclamação. Posso ajudar com mais alguma coisa?"


def negacao_atendente(e: Estado, p: dict) -> str:
    return "Tranquilo, sigo te ajudando por aqui. O que você precisa?"


def chamado_registrado(e: Estado, p: dict) -> str:
    d = _dados(e, "registrar_encaminhamento")
    txt = f"Chamado registrado. Protocolo: {d['protocolo']}."
    if d.get("repetido"):
        txt += " Esse pedido já estava registrado com esse protocolo."
    if d.get("prazo_retorno_horas_uteis"):
        txt += f" A equipe retorna em até {d['prazo_retorno_horas_uteis']} horas úteis."
    aviso = _aviso_expediente(e)
    return f"{txt} {aviso}".strip()


def registro_falhou(e: Estado, p: dict) -> str:
    r = e.ultimo("registrar_encaminhamento")
    if r is not None and r.estado == "negado":
        return ("Não consegui registrar porque o texto tinha telefone ou e-mail, e isso eu não guardo. "
                "A equipe já tem como falar com você. Pode repetir sem esses dados?")
    return ("Não consegui registrar o chamado agora, então ainda não existe protocolo. "
            "Pode tentar de novo em instantes?")


def registro_cancelado(e: Estado, p: dict) -> str:
    return "Combinado, não registrei nada. Se mudar de ideia é só me avisar. Posso ajudar em mais alguma coisa?"


def falha_ferramenta(e: Estado, p: dict) -> str:
    base = ("Tive um problema na consulta e não vou arriscar uma resposta sem confirmar. "
            "Pode tentar de novo em instantes?")
    if e.falhas_seguidas >= 2:
        return base[:-len("Pode tentar de novo em instantes?")] + f"Se preferir, registro o problema para a equipe. {CONFIRMA}"
    return base


def identidade(e: Estado, p: dict) -> str:
    nome = _condicoes(e).get("empresa.nome_fantasia")
    de = f" da {nome}" if nome else ""
    return (f"Sou a Lia, assistente virtual{de}. Não sou uma pessoa: respondo de forma automática, com as informações "
            "da loja. Posso ajudar com produtos e preços, pedidos, pagamento, frete, trocas e devoluções, horário e "
            "endereço. Se você quiser falar com a equipe, é só pedir.")


def encerramento(e: Estado, p: dict) -> str:
    return "Por nada! Foi um prazer ajudar. Até a próxima."


def confirmacao_solta(e: Estado, p: dict) -> str:
    """"sim" ou "não" sem pergunta pendente."""
    if e.slots.get("negativo") and not e.slots.get("afirmativo"):
        return "Tudo bem. Em que mais posso ajudar?"
    if e.coletados.get("protocolo"):
        return "Certo, o seu chamado já está registrado. Posso ajudar em mais alguma coisa?"
    return ("Certo! Sobre o que você quer falar? Posso ajudar com produtos e preços, pedidos, pagamento, frete, "
            "trocas e devoluções, horário e endereço.")


def recusa_instrucoes(e: Estado, p: dict) -> str:
    return ("Não consigo atender esse pedido, porque as minhas instruções internas não são compartilhadas. Posso "
            "ajudar com produtos e preços, pedidos, pagamento, frete, trocas e devoluções, horário e endereço.")


def _linha_do_manual(e: Estado, palavra: str) -> str | None:
    for passo in e.passos:
        if passo.ferramenta == "consultar_politica" and passo.resultado.estado == "ok":
            for sec in passo.resultado.dados["secoes"]:
                for linha in (sec.get("texto") or "").splitlines():
                    if palavra in normalizar(linha):
                        return linha.strip(" •\t")
    return None


def reembolso_prazo(e: Estado, p: dict) -> str:
    dias = _condicoes(e).get("devolucao.arrependimento_reembolso_dias_uteis_max")
    if not dias:
        return sem_dado(e, p)
    linha = _linha_do_manual(e, "reembolso")
    if linha:
        corpo = linha[0].lower() + linha[1:].rstrip(".")
        return f"Na devolução por arrependimento, {corpo}. A equipe confirma se o seu caso se enquadra."
    return (f"Na devolução por arrependimento, o reembolso sai em até {dias} dias úteis. "
            "A equipe confirma se o seu caso se enquadra.")


def previsao_entrega(e: Estado, p: dict) -> str:
    ped = e.coletados["pedido"]
    numero = ped["pedido_id"]
    if ped["status"] == "delivered":
        txt = f"O pedido {numero} já consta como entregue."
    elif ped["status"] == "cancelled":
        txt = f"O pedido {numero} está cancelado, então não há entrega prevista."
    elif ped.get("previsao"):
        txt = f"A previsão de entrega do pedido {numero} é {_data_br(ped['previsao'])}."
        if ped.get("previsao_vencida"):
            txt += " Essa data já passou e o pedido ainda não consta como entregue."
    else:
        txt = f"O pedido {numero} ainda não tem previsão de entrega registrada."
    if ped.get("rastreio") and ped["status"] not in ("delivered", "cancelled"):
        txt += f"\nCódigo de rastreio: {ped['rastreio']}."
    if p.get("oferta") == "previsao_vencida":
        txt += f"\nQuer que eu registre para a equipe verificar o atraso? {CONFIRMA}"
    return txt


def extremo_lista(e: Estado, p: dict) -> str:
    r = e.ultimo("buscar_produtos")
    if r is None or r.estado != "ok":
        return falha_ferramenta(e, p)
    i = r.dados["itens"][0]
    rotulo = "O mais barato" if p.get("extremo", "min") == "min" else "O mais caro"
    promo = (f" (em promoção: {i['promocao']['percentual']}% de desconto)"
             if i["promocao"] and not i["promocao"].get("ambigua") else "")
    return (f"{rotulo} da busca é {i['nome']}: {formatar(i['preco_centavos'])}, preço de tabela{promo}. "
            "Quer ver as condições dele?")


def sem_dado(e: Estado, p: dict) -> str:
    return ("Não encontrei essa informação nos dados que eu tenho, e prefiro não inventar. "
            f"Quer que eu registre a dúvida para a equipe? {CONFIRMA}")


def perguntas_repetidas(e: Estado, p: dict) -> str:
    return ("Parece que não estou conseguindo avançar com essa informação, desculpa. "
            f"Posso registrar o seu caso para a equipe te ajudar? {CONFIRMA}")


def atendente_ja_registrado(e: Estado, p: dict) -> str:
    txt = (f"Você já tem um chamado registrado, protocolo {p['protocolo']}. "
           "Ele já está na fila da equipe, então não abri outro.")
    return f"{txt} {_aviso_expediente(e)}".strip()


# Tom: poucas formas, nunca repetidas na mesma conversa, sem desculpa por fato correto e sem prometer prazo.
RECONHECIMENTOS = {
    "frustrado": ("Entendo, vou direto ao ponto.", "Entendo sua frustração.", "Imagino como isso é chato."),
    "irritado": ("Entendo a sua irritação e quero ajudar.", "Sinto muito que a situação esteja assim.",
                 "Percebo que está sendo difícil, vamos resolver."),
}
OFERTA_HUMANO = "Quer que um atendente te ajude? " + CONFIRMA


CONFERI_PEDIDO = "Entendo sua frustração. Conferi o que está registrado sobre o seu pedido."


def reconhecimento(e: Estado) -> str:
    """Frase curta de reconhecimento para o sentimento do turno; vazia se neutro ou se as formas acabaram.

    A forma que fala do pedido só sai se a consulta do pedido de fato ocorreu neste turno."""
    if e.sentimento == "frustrado" and e.ultimo("consultar_pedido") is not None             and CONFERI_PEDIDO not in e.reconhecimentos_usados:
        e.reconhecimentos_usados.append(CONFERI_PEDIDO)
        return CONFERI_PEDIDO
    for frase in RECONHECIMENTOS.get(e.sentimento, ()):
        if frase not in e.reconhecimentos_usados:
            e.reconhecimentos_usados.append(frase)
            return frase
    return ""


def dado_recusado(e: Estado, p: dict) -> str:
    return "Tudo bem. Quando quiser retomar, é só me chamar."


def confirmar_registro(e: Estado, p: dict) -> str:
    return f"Posso registrar isso para a equipe? {CONFIRMA}"


def nao_entendi(e: Estado, p: dict) -> str:
    return ("Não entendi bem. Posso ajudar com produtos e preços, pedidos, pagamento, frete, trocas e devoluções, "
            "horário e endereço. Pode me dizer de outro jeito?")


def nao_entendi_de_novo(e: Estado, p: dict) -> str:
    return f"Ainda não consegui entender, desculpa. Quer que um atendente te ajude? {CONFIRMA}"


def ok_sem_retomar(e: Estado, p: dict) -> str:
    return "Tudo bem, deixei esse assunto de lado. Em que mais posso ajudar?"


def retomar(e: Estado, p: dict) -> str:
    assunto = ROTULOS_ASSUNTO.get(p["assunto"], "o assunto anterior")
    return f"Antes a gente estava falando sobre {assunto}. Quer retomar? {CONFIRMA}"


# --- conformidade com o manual (etapa 10) -----------------------------------------------------------------

def _sentenca(texto: str) -> str:
    """Item de lista do manual dito no meio da frase: inicial minúscula, sem ponto final."""
    texto = texto.strip(" •\t").rstrip(".")
    return texto[0].lower() + texto[1:] if texto and not texto[:2].isupper() else texto


def garantia_excluida(e: Estado, p: dict) -> str:
    itens = _condicoes(e).get("garantia.nao_cobre") or []
    padrao = r"desgaste" if p.get("desgaste") and not p.get("mau_uso") else r"queda|mau uso"
    achados = [x for x in itens if re.search(padrao, normalizar(x))]
    if not achados:
        return sem_dado(e, p)
    return (f"Pelas regras da loja, a garantia não cobre: {_sentenca(achados[0])}. Por isso esse caso não entra em troca por "
            "defeito nem por preferência. Se o seu caso for outro, é só me contar.")


def avaria_recebimento(e: Estado, p: dict) -> str:
    return ("Se o produto chegou com avaria, o certo é recusar o recebimento e falar com a loja imediatamente. "
            f"Quer que eu registre o problema para a equipe? {CONFIRMA}")


def devolucao_loja_fisica(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    arrep, defeito, pref = c.get("regra.arrependimento"), c.get("regra.defeito"), c.get("regra.preferencia")
    if not arrep or arrep.get("aplica_a") != "compra_online":
        return sem_dado(e, p)
    partes = [f"O direito de arrependimento vale para compra online ({_prazo(arrep)}), então não se aplica a uma "
              "compra feita na loja física."]
    cabe = []
    if defeito:
        cabe.append(f"troca por defeito de fabricação ({_prazo(defeito)})")
    if pref:
        cabe.append(f"troca por preferência ({pref['prazo_dias']} dias, conforme a disponibilidade do produto)")
    if cabe:
        partes.append("Dependendo do caso, cabe " + " ou ".join(cabe) + ". A equipe confirma se o seu caso se enquadra.")
    return " ".join(partes)


def defeito_apos_prazo(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    regra = c.get("regra.defeito")
    if not regra or not c.get("defeito.apos_prazo_aciona_fabricante"):
        return sem_dado(e, p)
    ped = e.coletados.get("pedido") or {}
    quando = f"O pedido é de {_data_br(ped['data_pedido'])} e passaram os" if ped.get("data_pedido") else "Passados os"
    inter = (" A loja pode intermediar o processo se você pedir."
             if c.get("defeito.loja_pode_intermediar_mediante_solicitacao") else "")
    return (f"{quando} {regra['prazo_dias']} dias para troca por defeito. Depois desse prazo a garantia é acionada "
            f"direto com o fabricante.{inter} Quer que eu registre o pedido de intermediação para a equipe? {CONFIRMA}")


def devolucao_frete(e: Estado, p: dict) -> str:
    if not _condicoes(e).get("devolucao.arrependimento_frete_por_conta_da_loja"):
        return sem_dado(e, p)
    return ("Na devolução por arrependimento, o frete de devolução é por conta da loja. "
            "A equipe confirma se o seu caso se enquadra.")


def rain_check(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if "promocoes.rain_check" not in c or c["promocoes.rain_check"]:
        return sem_dado(e, p)
    return ("Não seguramos o preço de promoção: produto esgotado durante a promoção não gera rain check (reserva de "
            "preço), e quando a promoção acaba vale o preço atual. Se quiser, é só pedir que eu mostro as promoções "
            "ativas.")


def rastreio_como(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    por, onde = c.get("rastreamento.enviado_por"), c.get("rastreamento.consulta_em")
    if not por or not onde:
        return sem_dado(e, p)
    return (f"O código de rastreamento é enviado automaticamente por {_lista(por)} assim que o pedido é despachado, e "
            f"dá para acompanhar no site dos {_lista(onde)}. Se já tiver um pedido, eu consulto o andamento por aqui "
            "com o número dele e os 4 últimos dígitos do telefone.")


def privacidade(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    secao = next((s for pas in e.passos if pas.ferramenta == "consultar_politica" and pas.resultado.estado == "ok"
                  for s in pas.resultado.dados["secoes"] if s["id"] == "9"), None)
    finalidades = [_sentenca(ln) for ln in ((secao or {}).get("texto") or "").splitlines() if ln.strip().startswith("•")]
    if not secao or not finalidades or "privacidade.compartilha_para_marketing" not in c:
        return sem_dado(e, p)
    txt = ("Seus dados pessoais (nome, telefone, e-mail, endereço) são usados só para: "
           + "; ".join(finalidades) + ".")
    if not c["privacidade.compartilha_para_marketing"]:
        txt += " Dados de clientes não são compartilhados com terceiros para fins de marketing."
    if c.get("privacidade.exclusao_a_pedido_do_cliente"):
        canais = [c[k] for k in ("contato.whatsapp_secao_7", "contato.email_capa") if k in c]
        txt += " Você pode pedir a exclusão dos seus dados a qualquer momento"
        txt += f" pelo WhatsApp ou e-mail da loja ({' / '.join(canais)})." if canais else "."
    return txt


def empresa_dados(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    nome, foco = c.get("empresa.nome_fantasia"), p.get("foco") or ["fundacao"]
    partes = []
    if "fundacao" in foco and c.get("empresa.fundacao_ano"):
        end = c.get("empresa.endereco") or {}
        onde = f" em {end['cidade']}" if end.get("cidade") else ""
        partes.append(f"A {nome} foi fundada em {c['empresa.fundacao_ano']}{onde}.")
    if ("cnpj" in foco or "razao" in foco) and c.get("empresa.razao_social"):
        partes.append(f"A razão social é {c['empresa.razao_social']}")
        if "cnpj" in foco and c.get("empresa.cnpj"):
            partes[-1] += f", CNPJ {c['empresa.cnpj']}"
        partes[-1] += "."
    return " ".join(partes) if partes else sem_dado(e, p)


def frete_modalidade(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    mods = c.get("frete.outras_cidades_modalidades") or []
    m = next((x for x in mods if normalizar(x["nome"]).startswith(normalizar(p["modalidade"]))), None)
    if not m:
        return sem_dado(e, p)
    prazo = m["prazo_dias_uteis"]
    extra = ", com rastreamento" if m.get("rastreamento") else ""
    extra += " e seguro incluído" if m.get("seguro") else ""
    base = c.get("frete.cidade_base", "a cidade da loja")
    return (f"{m['nome']}: {prazo['min']} a {prazo['max']} dias úteis{extra}. Vale para envios fora de {base}. "
            "Para estimar o valor, me diga o produto e o CEP de entrega.")


def frete_grande_porte(e: Estado, p: dict) -> str:
    return (f"Para {str(p['cidade']).title()}, {p['item']} são instrumentos de grande porte e o frete tem cotação "
            "individual: a nossa equipe faz o cálculo, e eu não informo valor por aqui.")


def parecidos(e: Estado, p: dict) -> str:
    """Outros modelos da mesma categoria do produto em foco, em faixa de preço próxima (ou mais baratos)."""
    d = _dados(e, "ver_produto")
    r = e.ultimo("buscar_produtos")
    itens = [i for i in (r.dados["itens"] if r is not None and r.estado == "ok" else []) if i["id"] != d["id"]][:3]
    faixa = "mais barato que" if p.get("mais_barato") else "de faixa de preço próxima ao"
    if not itens:
        return (f"Não encontrei outro modelo de {d['categoria']} disponível {faixa} {d['nome']}. "
                "Quer que eu mostre as opções da categoria?")
    linhas = [f"- {i['nome']}: {formatar(i['preco_centavos'])}" for i in itens]
    return (f"Modelos de {d['categoria']} {faixa} {d['nome']}, preço de tabela:\n" + "\n".join(linhas)
            + "\nQuer ver as condições de algum deles?")


TEXTOS: dict[str, Callable[[Estado, dict], str]] = {
    f.__name__: f for f in (
        saudacao, horario, endereco, contato, pagamento, frete_info, pedir_valor_pedido, frete_calculado,
        fora_escopo, garantia_info, busca, pedir_categoria, pedir_produto, produto_nao_encontrado, escolha_produto,
        disponibilidade, preco, preco_promocao_conflitante, pedir_pedido, pedido_negado, pedido_negado_limite,
        status_pedido, status_pedido_demo, pedido_demo_negado, pedir_dados_posvenda, propor_posvenda, reclamacao_empatia, pedir_relato, negacao_reclamacao,
        negacao_atendente, chamado_registrado, registro_falhou, registro_cancelado, falha_ferramenta, sem_dado,
        nao_entendi, nao_entendi_de_novo, ok_sem_retomar, confirmar_registro, produto_indisponivel, promocoes,
        recusa_manipulacao, recusa_dado_de_terceiro, fora_escopo_geral, perguntas_repetidas,
        atendente_ja_registrado, trocas_info, trocas_detalhe, dado_recusado, frete_prazo,
        item_nao_elegivel, identidade, encerramento, confirmacao_solta, recusa_instrucoes, reembolso_prazo,
        previsao_entrega, extremo_lista, frete_outra_cidade, frete_estimado, frete_cotacao_individual,
        frete_cep_indisponivel, frete_cep_nao_encontrado, frete_pedir_produto, frete_pedir_cep, frete_cidade_base,
        escolha_produto_curta, objecao_preco, vou_pensar, garantia_excluida, avaria_recebimento, devolucao_loja_fisica,
        defeito_apos_prazo, devolucao_frete, rain_check, rastreio_como, privacidade, empresa_dados, frete_modalidade,
        frete_grande_porte, parecidos)
}


def renderizar(chave: str, estado: Estado, parametros: dict[str, Any]) -> str:
    return TEXTOS[chave](estado, parametros)
