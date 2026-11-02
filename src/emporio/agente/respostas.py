"""Textos da Lia. Todo fato de loja vem de resultados de ferramenta, nunca de literais aqui.

Voz: a da persona em persona.yaml (acolhedora, clara, informal mas profissional). Sem travessão.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from .. import config
from ..dinheiro import formatar
from ..ferramentas.etapas_pedido import etapas_do_pedido, etapas_do_site, frase_lia
from ..texto import normalizar
from . import expediente, vocabulario
from .estado import Estado

ROTULOS_ASSUNTO = {
    "devolucao": "a devolução", "troca_preferencia": "a troca por preferência", "defeito": "o produto com defeito",
    "status_pedido": "a consulta do pedido", "preco_produto": "o preço do produto", "disponibilidade": "a disponibilidade",
    "busca_produto": "a busca de produtos", "frete": "o frete", "reclamacao": "a reclamação", "garantia": "a garantia",
    "pagamento": "as formas de pagamento",
}
# Ambiguidade do manual, dita na primeira pessoa (a evidência fica no YAML do manual e nos testes).
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
# Quando a Lia não decide: diz que não decide e aponta o atendente, que o cliente pode pedir.
NAO_CONFIRMO = "Daqui eu não consigo confirmar se o seu caso se enquadra; um atendente pode avaliar, é só pedir."


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
                 f"No momento estamos fora do expediente. Voltamos {r['quando']} às {expediente.hora_br(r['hora'])}{ressalva}.",
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
    de = f" do {nome}" if nome else ""
    if e.concisao and e.ja_saudou:  # saudação no máximo uma vez por conversa
        txt = "Em que posso ajudar?"
    else:
        txt = f"Oi! Sou a Lia, assistente virtual{de}. Como posso te ajudar?"
    expediente_txt = _aviso_expediente(e)
    return f"{txt} {expediente_txt}".strip()


_DIAS_CITADOS = (("segunda", 0), ("terca", 1), ("quarta", 2), ("quinta", 3), ("sexta", 4), ("sabado", 5), ("domingo", 6))
_SEMANA_TODA = re.compile(r"\b(semana|todos os dias|todo dia|toda a semana|horarios?|funcionamento|expediente|dias)\b")


def _dia_perguntado(e: Estado) -> int | None:
    """Dia da semana (0 = segunda) quando a pergunta cita um só dia e não pede a semana inteira."""
    msg = normalizar(e.slots.get("texto_limpo", ""))
    if _SEMANA_TODA.search(msg):
        return None
    achados = {n for nome, n in _DIAS_CITADOS if re.search(rf"\b{nome}s?\b", msg)}
    return achados.pop() if len(achados) == 1 else None


def _horario_do_dia(e: Estado, c: dict, dia: int) -> str | None:
    faixa = next((f for f in c.get("horario.funcionamento", []) if dia in f["dias"]), None)
    if faixa is None:
        return None
    nome = expediente.DIAS[dia]
    artigo = "no" if dia >= 5 else "na"
    if faixa.get("fechado"):
        txt = f"{artigo.capitalize()} {nome} não abrimos: fica fechado o dia todo."
    else:
        txt = f"{artigo.capitalize()} {nome} abrimos das {expediente.hora_br(faixa['abre'])} às {expediente.hora_br(faixa['fecha'])}."
    if c.get("horario.feriados_fechado") or "feriados_sem_calendario" in _ambiguidades(e):
        txt += " Se for feriado, o horário pode mudar; antes de vir, vale falar com um atendente."
    return txt


def horario(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    dia = _dia_perguntado(e)
    if dia is not None and c.get("horario.funcionamento"):
        txt = _horario_do_dia(e, c, dia)
        if txt:
            return txt
    linhas = []
    for faixa in c.get("horario.funcionamento", []):
        dias = expediente.descrever_dias(faixa["dias"])
        linhas.append(f"- {dias}: fechado" if faixa.get("fechado") else
                      f"- {dias}: das {expediente.hora_br(faixa['abre'])} às {expediente.hora_br(faixa['fecha'])}")
    if not linhas:
        return sem_dado(e, p)
    if c.get("horario.feriados_fechado"):
        linhas.append("- feriados: fechado")
    txt = "Nosso horário de funcionamento:\n" + "\n".join(linhas)
    if c.get("horario.datas_especiais_podem_estender"):
        txt += "\nEm datas especiais o horário pode ser estendido."
    if "feriados_sem_calendario" in _ambiguidades(e):
        a = aviso(e, "feriados_sem_calendario",
                  "Eu não tenho o calendário de feriados, então em feriado o horário pode mudar; antes de vir, vale falar com um atendente.", proprio=True)
        txt += ("\n" + a) if a else ""
    sit = expediente.situacao(c["horario.funcionamento"], config.agora())
    if sit["aberto"]:
        txt += "\nAgora estamos abertos."
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
    return "Você pode falar com a gente por estes canais:\n" + "\n".join(linhas)


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
                         "por parcela, então em casos de limite eu não consigo confirmar daqui.", proprio=True)
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
    base = c.get("frete.cidade_base", "a nossa cidade")
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
    return (f"Para {cidade}, o frete depende de cotação e é calculado pela equipe, então daqui eu não consigo "
            f"informar o valor.{extra}{DICA_ESTIMATIVA}")


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
            "e o valor final depende da cotação individual.")


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
    return (f"Para {_destino(d)}, o frete de {p['produto']} é de cotação individual, "
            "e daqui eu não consigo informar o valor.")


def frete_cep_indisponivel(e: Estado, p: dict) -> str:
    return ("Não consegui consultar esse CEP agora, então prefiro não chutar um valor de frete. "
            "Tente de novo em instantes.")


def frete_cep_nao_encontrado(e: Estado, p: dict) -> str:
    return "Não encontrei esse CEP. Confira os números e me mande de novo."


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
    """Cidade fora da base do manual: o frete é cotado, não calculado aqui; não pede o valor do pedido."""
    c = _condicoes(e)
    cidade = str(p.get("cidade", "")).title()
    if p.get("uf"):
        cidade = f"{cidade}/{p['uf']}"
    txt = (f"Para {cidade}, o frete depende de cotação e é calculado pela equipe, então daqui eu não consigo "
           "informar o valor.")
    mods = c.get("frete.outras_cidades_modalidades", [])
    if mods:
        itens = [_modalidade_com_prazo(m) for m in mods]
        txt += " Os envios são por " + _lista(itens) + "."
    if p.get("produto"):  # produto conhecido: só falta o CEP para a estimativa
        return txt + f" Para uma estimativa (simulação) do {p['produto']}, me diga o CEP de entrega."
    return txt + DICA_ESTIMATIVA


def frete_produto(e: Estado, p: dict) -> str:
    """Frete na cidade da loja pelo preço do produto em foco (a ferramenta decide grátis ou taxa)."""
    d = _dados(e, "calcular_condicoes")
    f = d.get("frete") or {}
    cidade = str(p.get("cidade", "")).title()
    prazo = f.get("prazo_dias_uteis")
    prazo_txt = f" Prazo de {prazo['min']} a {prazo['max']} dias úteis." if prazo else ""
    if f.get("situacao") == "gratis":
        return f"Em {cidade}, o frete do {d['produto_nome']} é grátis.{prazo_txt}"
    if f.get("situacao") == "taxa":
        return f"Em {cidade}, o frete do {d['produto_nome']} é uma taxa fixa de {formatar(f['taxa_centavos'])}.{prazo_txt}"
    return frete_outra_cidade(e, {"cidade": p.get("cidade", "")})


def fora_escopo(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if not c.get("escopo.somente_instrumentos"):
        return sem_dado(e, p)
    acessorios = c.get("escopo.acessorios_nao_vendidos", [])
    lista = f" ({_lista(acessorios)})" if acessorios else ""
    loja = " Também não tenho indicação de lojas parceiras para isso." if e.slots.get("pede_loja") else ""
    return (f"Aqui trabalhamos só com instrumentos musicais, então não vendemos acessórios{lista}.{loja} "
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
                     " Como esses dois prazos se combinam eu não consigo confirmar daqui; um atendente pode avaliar o seu caso.", proprio=True)
    fab = c.get("garantia.fabricante_prazo_meses")
    if fab:
        txt += (f" Os fabricantes costumam ter garantia própria, de {fab['min']} meses a {fab['max'] // 12} anos, "
                "descrita no certificado que acompanha o produto.")
    nao = c.get("garantia.nao_cobre")
    if nao:
        txt += " Não cobre: " + "; ".join(x[0].lower() + x[1:] for x in nao) + "."
    return txt + "\nSe estiver com problema em algum produto, me conte, e eu te ajudo a abrir a solicitação."


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
            linhas.append(f"- Preferência: {pref['prazo_dias']} dias; de quando a contagem parte eu não consigo confirmar daqui.")
        else:
            linhas.append(f"- Preferência: {_prazo(pref)}.")
    if legal:
        extra = ""
        if defeito and "prazo_30_x_90" in amb:
            extra = f"; como convive com os {defeito['prazo_dias']} dias do defeito, eu não consigo confirmar daqui"
        linhas.append(f"- Garantia legal: {_prazo(legal)}{extra}.")
    if not linhas:
        return sem_dado(e, p)
    return ("Troca, devolução e garantia:\n" + "\n".join(linhas)
            + "\n" + NAO_CONFIRMO
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


def _busca_sem_resultado_com_filtros(e: Estado) -> str:
    """A combinação de filtros somados não existe no catálogo: diz qual é, sem inventar produto."""
    args = next((x.args for x in reversed(e.passos) if x.ferramenta == "buscar_produtos" and "limite" not in x.args), {})
    partes = [vocabulario.FICHA_ROTULO.get((k, v), f"{k} {v}") for k, v in (args.get("ficha") or {}).items()]
    partes += [t for t in (args.get("termo") or "").split()]
    if args.get("preco_min") is not None:
        partes.append(f"a partir de {formatar(args['preco_min'])}")
    if args.get("preco_max") is not None:
        partes.append(f"até {formatar(args['preco_max'])}")
    categoria = str(args.get("categoria") or "produto")
    return (f"Não encontrei {categoria} disponível com " + _lista(partes) + " no catálogo agora. "
            "Quer tirar algum desses filtros ou tentar outra faixa de preço?")


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
        if p.get("filtros"):
            return _busca_sem_resultado_com_filtros(e)
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
    a = aviso(e, "valores_de_tabela", "Os valores seguem o preço de tabela.")
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


def _campanha_do_manual(e: Estado, termo: str) -> str | None:
    """A campanha citada pelo cliente como o manual a escreve (nome e época), sem o percentual de desconto."""
    from ..politicas.manual import carregar_manual
    from ..texto import tokens

    chaves = [t for t in tokens(termo) if t not in ("de", "da", "do", "dos", "das")]
    for sec in carregar_manual().secoes:
        if not sec.publico or "promocoes" not in sec.temas:
            continue
        for linha in sec.texto.splitlines():
            limpa = linha.strip(" •\t")
            if chaves and all(t in tokens(limpa) for t in chaves):
                return limpa.split(":")[0].strip() if "%" in limpa else limpa.rstrip(".")
    return None


def frete_gratis_valor(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    base, minimo, taxa = c.get("frete.cidade_base"), c.get("frete.gratis_acima_centavos"), c.get("frete.taxa_abaixo_centavos")
    if not (base and minimo and taxa):
        return sem_dado(e, p)
    return (f"Em {base}, o frete é grátis para pedidos acima de {formatar(minimo)}; abaixo disso, é uma taxa fixa de "
            f"{formatar(taxa)}. Para outras cidades, o frete depende do CEP e do produto.")


def promocoes(e: Estado, p: dict) -> str:
    r = e.ultimo("listar_promocoes")
    if r is None:
        return falha_ferramenta(e, p)
    if r.estado == "vazio":
        termo = r.dados.get("termo")
        if termo:
            linha = _campanha_do_manual(e, termo)
            if linha:
                return (f"Nós temos a campanha {linha} entre as nossas promoções, mas ela não está ativa agora, então não posso "
                        "prometer desconto nem percentual. Se quiser, mostro as promoções que estão ativas.")
            return (f"A promoção {termo.title()} não está ativa agora, então não posso prometer esse "
                    "desconto. Se quiser, mostro as promoções que estão ativas.")
        return "Não há nenhuma promoção ativa agora."
    linhas = []
    for i in r.dados["promocoes"]:
        extra = "" if i["situacao_venda"] == "disponivel" else f" ({SITUACAO.get(i['situacao_venda'])})"
        if i["conflito"]:
            linhas.append(f"- {i['produto_nome']}: {i['percentual']}% de desconto, preço original "
                          f"{formatar(i['original_centavos'])}; há mais de uma promoção ativa, então não consigo confirmar o valor{extra}")
        else:
            linhas.append(f"- {i['produto_nome']}: de {formatar(i['original_centavos'])} por "
                          f"{formatar(i['final_centavos'])} ({i['percentual']}% de desconto){extra}")
    a = aviso(e, "pix_nao_soma", "O desconto do PIX não soma com preço promocional.")
    if p.get("citado"):
        return (f"Não consigo confirmar um desconto de {p['citado']}% prometido por fora: só valem as promoções "
                "ativas.\nPromoções ativas:\n" + "\n".join(linhas) + (("\n" + a) if a else ""))
    return "Promoções ativas:\n" + "\n".join(linhas) + (("\n" + a) if a else "")


def recusa_manipulacao(e: Estado, p: dict) -> str:
    pix = _condicoes(e).get("pagamento.pix_desconto_percentual")
    extra = f" e o desconto de {pix}% no PIX" if pix else ""
    return ("Não consigo atender esse pedido. Os descontos que eu informo são só os das promoções ativas"
            f"{extra}. Quer ver as promoções ativas?")


def recusa_pedido_indevido(e: Estado, p: dict) -> str:
    return ("Não consigo atender esse pedido, porque ele está fora do que posso fazer por aqui. Posso ajudar com "
            "produtos e preços, pedidos, pagamento, frete, trocas e devoluções, horário e endereço.")


def seguro_envio(e: Estado, p: dict) -> str:
    """Seguro dos envios: a frase da seção de frete do manual (5.2), sem acrescentar nada."""
    for passo in e.passos:
        if passo.ferramenta == "consultar_politica" and passo.resultado.estado == "ok":
            for sec in passo.resultado.dados["secoes"]:
                for frase in re.split(r"(?<=\.)\s+", sec.get("texto") or ""):
                    n = normalizar(frase)
                    if "seguro" in n and "envios" in n:
                        return frase.strip()
    return sem_dado(e, p)


def endereco_pedido_privado(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    canais = [f"{rot} {c[chave]}" for chave, rot in (("contato.whatsapp_secao_7", "WhatsApp"),
                                                       ("contato.telefone_capa", "telefone")) if chave in c]
    onde = f" Para conferir ou alterar, fale com um atendente: {_lista(canais)}." if canais else ""
    return ("Por privacidade, eu não mostro o endereço de entrega de um pedido por aqui, nem confirmo o endereço de "
            "quem comprou." + onde)


ROTULO_SPEC = {"top": "tampo", "back_sides": "fundo e laterais", "neck": "braço", "strings": "cordas", "scale": "escala",
               "electronics": "eletrônica", "color": "cor", "body": "corpo"}


def _spec_texto(chave: str, valor: Any) -> str:
    if chave == "electronics":
        return "com eletrônica" if str(valor).lower() in ("yes", "sim", "true") else "sem eletrônica"
    return str(valor)


def comparacao(e: Estado, p: dict) -> str:
    """Os dois produtos com preço de tabela, promoção ativa e as diferenças da ficha do catálogo. Sem veredito."""
    produtos = [x.resultado.dados for x in e.passos if x.ferramenta == "ver_produto" and x.resultado.estado == "ok"][-2:]
    a, b = produtos
    linhas = []
    for d in produtos:
        promo = d.get("promocao") or {}
        extra = f" (em promoção: {promo['percentual']}% de desconto)" if promo and not promo.get("ambigua") else ""
        linhas.append(f"- {d['nome']}: {formatar(d['preco_centavos'])}{extra}")
    ea, eb = a.get("especificacoes") or {}, b.get("especificacoes") or {}
    difs = [f"{ROTULO_SPEC.get(k, k)}: {_spec_texto(k, ea[k])} no {a['nome']} e {_spec_texto(k, eb[k])} no {b['nome']}"
            for k in ea if k in eb and ea[k] != eb[k] and k in ROTULO_SPEC]
    txt = "Comparando os dois, preço de tabela:\n" + "\n".join(linhas)
    if difs:
        txt += "\nDiferenças da ficha do catálogo:\n" + "\n".join(f"- {x}" for x in difs)
    for d in produtos:
        if d.get("descricao"):
            txt += f"\n{d['nome']}: {d['descricao']}"
    return txt + "\nNão consigo dizer qual é melhor para o seu uso, só mostrar o que o catálogo informa. Quer ver as condições de algum deles?"


def _frases(descricao: str | None) -> list[str]:
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", descricao or "") if f.strip()]


def _numero_na_descricao(descricao: str | None, palavra: str) -> str | None:
    m = re.search(rf"\b(\d+)\s+(?:{palavra})\b", descricao or "", re.I)
    return m.group(1) if m else None


def ficha_atributo(d: dict, atributo: str) -> str | None:
    """Resposta de um atributo do produto pela ficha (especificacoes) e pela descrição do cadastro; None se não há dado.
    Quando a ficha e a descrição divergem, os dois valores aparecem, sem escolher um."""
    esp, desc, nome = d.get("especificacoes") or {}, d.get("descricao") or "", d["nome"]
    if atributo in ("teclas", "cordas", "pecas"):
        chave, palavra, rotulo = {"teclas": ("keys", "teclas", "teclas"), "cordas": ("strings", "cordas", "cordas"),
                                  "pecas": ("pieces", "pecas|peças", "peças")}[atributo]
        ficha = str(esp.get(chave, "")).strip()
        ficha = ficha if ficha.isdigit() else ""
        descrita = _numero_na_descricao(desc, palavra)
        if ficha and descrita and ficha != descrita:
            return (f"a ficha do catálogo indica {ficha} {rotulo}, mas a descrição fala em {descrita}; como os dois "
                    "dados divergem, prefiro não afirmar qual vale")
        if ficha or descrita:
            return f"tem {ficha or descrita} {rotulo}"
        if atributo == "cordas" and str(esp.get("strings", "")).lower() in ("nylon", "steel", "aco", "aço"):
            return "usa cordas de " + ("nylon" if str(esp["strings"]).lower() == "nylon" else "aço")
        return None
    if atributo == "ferragem":
        valor = str(esp.get("hardware", "")).lower()
        if valor in ("included", "incluida", "incluída", "sim", "yes"):
            return "vem com as ferragens incluídas"
        if valor in ("none", "no", "nao", "não", "excluded"):
            return "não vem com ferragens"
        frase = next((f for f in _frases(desc) if re.search(r"ferragen", f, re.I)), None)
        return f"a descrição do catálogo diz: \"{frase.rstrip('.')}\"" if frase else None
    if atributo == "captacao":
        eletronica = str(esp.get("electronics", "")).lower()
        if eletronica in ("no", "nao", "não", "false"):
            return "não tem captação nem eletrônica, segundo a ficha do catálogo"
        frase = next((f for f in _frases(desc) if re.search(r"captac|captad|eletroac|pr[eé] ?amplif|\bpr[eé]\b", f, re.I)), None)
        if eletronica in ("yes", "sim", "true"):
            return "tem captação, segundo a ficha do catálogo" + (f". A descrição diz: \"{frase.rstrip('.')}\"" if frase else "")
        return f"a descrição do catálogo diz: \"{frase.rstrip('.')}\"" if frase else None
    if atributo == "nivel":
        frase = next((f for f in _frases(desc) if vocabulario.NIVEL_NA_DESCRICAO.search(f)), None)
        return f"a descrição do catálogo diz: \"{frase.rstrip('.')}\"" if frase else None
    return None


ROTULO_ATRIBUTO = {"teclas": "o número de teclas", "pecas": "o número de peças", "ferragem": "as ferragens",
                   "cordas": "as cordas", "captacao": "a captação", "nivel": "o nível indicado"}


def ficha_produto(e: Estado, p: dict) -> str:
    """Pergunta sobre o produto: cada atributo pedido sai da ficha ou da descrição do cadastro, sem inferência."""
    d = _dados(e, "ver_produto")
    nome, achados, faltam = d["nome"], [], []
    for a in p.get("atributos") or []:
        r = ficha_atributo(d, a)
        (achados if r is not None else faltam).append((a, r))
    partes = []
    if achados:
        partes.append(f"{nome}: " + "; ".join(r for _, r in achados) + ".")
    if faltam:
        itens = " e ".join(ROTULO_ATRIBUTO[a] for a, _ in faltam)
        partes.append(f"Não tenho essa informação sobre {itens} do {nome}, então prefiro não afirmar nada.")
    if p.get("propor_registro"):
        partes.append(f"Quer que um atendente confirme para você? {CONFIRMA}")
    return " ".join(partes)


def preco_pix_e_parcelas(e: Estado, p: dict) -> str:
    """PIX e parcelas do mesmo produto, uma frase para cada, com os valores devolvidos pela ferramenta."""
    calc = [x.resultado.dados for x in e.passos if x.ferramenta == "calcular_condicoes" and x.resultado.estado == "ok"]
    pix = next(d for d in reversed(calc) if d["forma"] == "pix")
    cred = next(d for d in reversed(calc) if d["forma"] == "credito")
    nome = pix["produto_nome"]
    if pix.get("percentual"):
        a = aviso(e, "pix_nao_soma", "O desconto do PIX não soma com promoção.")
        p1 = (f"{nome}: preço de tabela {formatar(pix['original_centavos'])}, promoção de {pix['percentual']}% e preço "
              f"final {formatar(pix['final_centavos'])}." + (" " + a if a else ""))
    else:
        p1 = (f"{nome}: no PIX ({pix.get('pix_percentual')}% de desconto) fica {formatar(pix['final_centavos'])} "
              f"(preço de tabela {formatar(pix['original_centavos'])}).")
    p2 = f"No crédito em {cred['parcelas']}x, cada parcela fica em {formatar(cred['parcela_centavos'])}."
    if cred["permitido"] == "sim":
        p2 += " Esse parcelamento atende a nossa parcela mínima."
    elif cred["permitido"] == "nao":
        p2 += " Esse parcelamento não atende a nossa parcela mínima."
    else:
        p2 += (f" Esse parcelamento eu não consigo confirmar daqui: a parcela mínima é "
               f"{formatar(cred['minimo_tabela_centavos'])} em uma regra e {formatar(cred['minimo_faixa_centavos'])} "
               f"na faixa de {cred['parcelas']}x.")
    return f"{p1} {p2}"


def combinacao_formas(e: Estado, p: dict) -> str:
    """Combinar formas de pagamento: a regra do manual (acima de um valor) aplicada ao preço de tabela do produto."""
    limite = _condicoes(e).get("pagamento.combinacao_formas_acima_centavos")
    if not limite:
        return sem_dado(e, p)
    if p["preco"] > limite:
        return (f"Pode, sim: é possível combinar formas de pagamento (por exemplo PIX e cartão) em compras acima de "
                f"{formatar(limite)}, e o {p['produto']} custa {formatar(p['preco'])} (preço de tabela). "
                "Para calcular os valores de cada parte, me diga quanto vai no PIX e quanto no cartão.")
    return (f"A combinação de formas de pagamento vale para compras acima de {formatar(limite)}, e o {p['produto']} custa "
            f"{formatar(p['preco'])} (preço de tabela). Então, só com esse produto, não dá para dividir entre PIX e cartão.")


def acolhimento(e: Estado, p: dict) -> str:
    return f"Sinto muito por isso. Quer que um atendente te ajude? {CONFIRMA}"


def so_portugues(e: Estado, p: dict) -> str:
    tema = p.get("tema")
    entendi = f" Entendi que o assunto é {tema}." if tema else ""
    return f"O atendimento aqui é em português.{entendi} Pode escrever sua pergunta em português?"


def cupom_inexistente(e: Estado, p: dict) -> str:
    pix = _condicoes(e).get("pagamento.pix_desconto_percentual")
    extra = f" e o desconto de {pix}% no PIX" if pix else ""
    return ("Não existe esse cupom: eu só conheço as promoções ativas" + extra + ". Quer ver as promoções ativas?")


def recusa_dado_de_terceiro(e: Estado, p: dict) -> str:
    return ("Não passo dados pessoais de clientes, como telefone, e-mail, endereço ou nome. Se o pedido é seu, posso "
            "consultar o andamento com o número do pedido e os 4 últimos dígitos do telefone cadastrado.")


def fora_escopo_geral(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if not c.get("escopo.somente_instrumentos"):
        return sem_dado(e, p)
    return ("Esse assunto foge do que eu consigo ajudar por aqui, já que trabalhamos só com instrumentos "
            "musicais. Posso ajudar com produtos, preços, pedidos, trocas e devoluções?")


def _unidades_em_estoque(estoque: int) -> str:
    return f"Temos {estoque} {'unidade' if estoque == 1 else 'unidades'} em estoque agora"


def disponibilidade(e: Estado, p: dict) -> str:
    d = _dados(e, "ver_produto")
    txt = f"{d['nome']}: {SITUACAO.get(d['situacao_venda'], d['situacao_venda'])}, conforme o estoque agora."
    n, estoque = e.slots.get("quantidade"), d.get("estoque_unidades")
    if n and estoque is not None:  # "tem 20 no estoque?": compara o pedido com o estoque do produto
        txt = (f"{d['nome']}: {_unidades_em_estoque(estoque)}, " + ("menos que as %d que você pediu." % n if n > estoque
               else "o bastante para as %d que você pediu." % n))
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
            partes.append("Esse parcelamento atende a nossa parcela mínima.")
        elif d["permitido"] == "nao":
            partes.append("Esse parcelamento não atende a nossa parcela mínima.")
        else:
            partes.append(f"Esse parcelamento eu não consigo confirmar daqui: a parcela mínima é "
                          f"{formatar(d['minimo_tabela_centavos'])} em uma regra e {formatar(d['minimo_faixa_centavos'])} "
                          f"na faixa de {d['parcelas']}x. Quer que eu registre a dúvida para um atendente avaliar? {CONFIRMA}")
    if p.get("promo_inativa"):
        partes.insert(0, f"A promoção {str(p['promo_inativa']).title()} não está ativa para este produto, "
                         "então não posso prometer esse desconto.")
    elif p.get("desconto_citado"):
        partes.insert(0, f"Não consigo confirmar um desconto de {p['desconto_citado']}%: só vale a promoção ativa, "
                         "e é isto que vale para este produto.")
    if p.get("pergunta_promocao") and not d.get("percentual") and not p.get("promo_inativa"):
        partes.append("Esse produto não está em promoção ativa agora.")
    acima_do_estoque = False
    if p.get("quantidade"):
        n = p["quantidade"]
        estoque = _dados(e, "ver_produto").get("estoque_unidades")
        if estoque is not None and n > estoque:
            acima_do_estoque = True  # pedido maior que o estoque: diz quantas há e não cota a quantidade pedida
            partes.append(f"{_unidades_em_estoque(estoque)}, menos que as {n} que você pediu, "
                          "então não consigo cotar essa quantidade.")
        else:
            if d["forma"] == "credito":
                partes.append(f"Para {n} unidades, são {formatar(d['parcela_centavos'] * n)} por mês em {d['parcelas']}x "
                              f"(total {formatar(d['final_centavos'] * n)}).")
            else:
                rotulo = " no PIX" if d["forma"] == "pix" and not d.get("percentual") else ""
                partes.append(f"Para {n} unidades{rotulo}: {formatar(d['final_centavos'] * n)}.")
    if d.get("situacao_venda") not in (None, "disponivel"):
        partes.append(f"Atenção: o produto está {SITUACAO.get(d['situacao_venda'])}.")
        return " ".join(partes)
    if p.get("valor_frete"):  # uma condição que ajuda por vez, e só uma vez na conversa
        partes.append(f"Em {str(p['valor_frete']).title()}, o frete desse produto é grátis.")
        e.valores_citados.append("frete_gratis")
    if p.get("compra") and not acima_do_estoque:  # o passo seguinte é o botão: a Lia nunca adiciona nada sozinha
        partes.append("Para comprar, toque em Adicionar ao carrinho; eu não adiciono nada por você.")
    elif d["forma"] != "credito" and p.get("oferta_parcelas"):
        partes.append("Quer ver as parcelas no cartão de crédito?")
    return " ".join(partes)


def preco_promocao_conflitante(e: Estado, p: dict) -> str:
    return ("Esse produto aparece com mais de uma promoção ativa, e eu não vou chutar o preço. "
            f"Quer que eu registre para um atendente confirmar o valor? {CONFIRMA}")


def item_nao_elegivel(e: Estado, p: dict) -> str:
    return (f"Esse item não entra em troca: {p['trecho']}. "
            "Se o seu caso for outro, é só me contar.")


def pedir_pedido(e: Estado, p: dict) -> str:
    regra = e.coletados.get("regra")
    if regra and p.get("com_regra") and e.objetivo in ROTULOS_REGRA:
        v = regra["valor"]
        online = ", e vale para compra online" if v.get("aplica_a") == "compra_online" else ""
        return (f"Pela nossa regra, {ROTULOS_REGRA[e.objetivo]}: {_prazo(v)}{online}. {NAO_CONFIRMO} "
                "Para consultar o pedido, me diga o número do pedido e os 4 últimos dígitos do "
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
    etapa = frase_lia(etapas_do_pedido(ped["status"], data_pedido=ped.get("data_pedido"), rastreio=ped.get("rastreio"),
                                       previsao=ped.get("previsao"), nota=ped.get("nota")))
    if etapa:
        txt += f"\n{etapa}"
    if p.get("oferta") == "previsao_vencida":
        txt += f"\nQuer que eu registre para um atendente verificar o atraso? {CONFIRMA}"
    return txt


def status_pedido_demo(e: Estado, p: dict) -> str:
    d = e.coletados["pedido_demo"]
    itens = ", ".join(f"{i['quantidade']}x {i['nome']}" for i in d["itens"])
    etapa = frase_lia(etapas_do_site(d))
    return (f"Pedido {d['numero']}: feito no site. {d['aviso']}\n"
            f"Itens: {itens}.\n{d['frete_linha']}.\n{d['total_rotulo']}: {formatar(d['total_gravado_centavos'])}."
            + (f"\n{etapa}" if etapa else ""))


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
    return f"{achei}{_nota_prazo_defeito(e)} Para organizar sua solicitação, me conte: {_lista(campos)}.".strip()


def propor_posvenda(e: Estado, p: dict) -> str:
    ped, regra = e.coletados["pedido"], e.coletados["regra"]["valor"]
    itens = ", ".join(f"{i['quantidade']}x {i['nome']}" for i in ped["itens"])
    consta = (f"pedido {ped['pedido_id']}, status {STATUS_PEDIDO.get(ped['status'], ped['status'])}, {itens}, "
               f"total gravado {formatar(ped['total_gravado_centavos'])}")
    if ped.get("data_pedido"):
        consta += f", feito em {_data_br(ped['data_pedido'])}"
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
    nota = f" Não consigo confirmar daqui {pontos[0]}." if pontos else ""
    return (  # quatro linhas: pedido, o que o cliente informou, regra, pergunta de registro
        f"O que consta no seu pedido: {consta}.{_nota_prazo_defeito(e)}\n"
        f"O que você me informou (não verificado): {'; '.join(decl)}.\n"
        f"O que um atendente precisa confirmar: se o seu caso se enquadra na nossa regra ({condicao}, {marco_txt}{aplica}).{exigido}"
        f"{nota} Eu não consigo garantir a elegibilidade; a decisão é de um atendente.\n"
        f"Posso registrar essa solicitação para um atendente avaliar? {CONFIRMA}")


def reclamacao_empatia(e: Estado, p: dict) -> str:
    return ("Sinto muito pelo que aconteceu. Quero que um atendente veja o seu caso com atenção. "
            f"Posso registrar uma reclamação com o que você me contou? {CONFIRMA}")


def pedir_relato(e: Estado, p: dict) -> str:
    return ("Entendo. Pode me contar em poucas palavras o que aconteceu? "
            "Não precisa passar telefone nem e-mail: ao registrar, eu te passo um protocolo para acompanhar.")


def negacao_reclamacao(e: Estado, p: dict) -> str:
    return "Tudo bem, não vou abrir reclamação. Posso ajudar com mais alguma coisa?"


def negacao_atendente(e: Estado, p: dict) -> str:
    return "Tranquilo, sigo te ajudando por aqui. O que você precisa?"


def chamado_registrado(e: Estado, p: dict) -> str:
    d = _dados(e, "registrar_encaminhamento")
    txt = f"Registrei o seu chamado. Protocolo: {d['protocolo']}."
    if d.get("repetido"):
        txt += " Esse chamado já estava registrado com esse protocolo."
    if d.get("prazo_retorno_horas_uteis"):
        txt += f" Você recebe o retorno de um atendente em até {d['prazo_retorno_horas_uteis']} horas úteis."
    txt += _retorno_e_canais(e, txt)  # todo chamado: protocolo, prazo de retorno e canais
    txt += " Ao falar com a loja, cite o protocolo."
    if d.get("tipo") == "reclamacao" and e.sentimento in ("irritado", "frustrado"):
        # reclamação com irritação: acolhimento curto antes do registro, sem pedir desculpa por fato não verificado
        acolhe = reconhecimento(e)
        txt = f"{acolhe}\n{txt}" if acolhe else txt
    aviso = _aviso_expediente(e)
    return f"{txt} {aviso}".strip()


def _retorno_e_canais(e: Estado, ja_dito: str) -> str:
    c = _condicoes(e)
    partes = []
    prazo = c.get("atendimento.prazo_retorno_reclamacao_horas_uteis")
    if not prazo:  # o chamado de qualquer tipo informa o prazo do manual, mesmo sem a seção 7.3 carregada
        from ..politicas import manual

        try:
            fato = manual.fato("atendimento.prazo_retorno_reclamacao_horas_uteis")
        except Exception:  # manual indisponível: o chamado já foi gravado, então só omite o prazo
            fato = None
        prazo = fato.valor if fato is not None else None
    if prazo and "horas úteis" not in ja_dito:
        partes.append(f" O retorno de um atendente é em até {prazo} horas úteis.")
    canais = [f"WhatsApp {c['contato.whatsapp_secao_7']}"] if "contato.whatsapp_secao_7" in c else []
    if "contato.telefone_capa" in c:
        canais.append(f"telefone {c['contato.telefone_capa']}")
    if canais:
        faixas = [f"{expediente.descrever_dias(f['dias'])}, das {expediente.hora_br(f['abre'])} às {expediente.hora_br(f['fecha'])}"
                  for f in c.get("horario.funcionamento", []) if not f.get("fechado")]
        horario = f" ({'; '.join(faixas)})" if faixas else ""
        partes.append(f" Se preferir falar agora, os canais são {' e '.join(canais)}{horario}.")
    return "".join(partes)


def registro_falhou(e: Estado, p: dict) -> str:
    r = e.ultimo("registrar_encaminhamento")
    if r is not None and r.estado == "negado":
        return ("Não consegui registrar porque o texto tinha telefone ou e-mail, e isso eu não guardo. "
                "Ao registrar, eu te passo um protocolo para acompanhar. Pode repetir sem esses dados?")
    return ("Não consegui registrar o chamado agora, então ainda não existe protocolo. "
            "Pode tentar de novo em instantes?")


def registro_cancelado(e: Estado, p: dict) -> str:
    return "Combinado, não registrei nada. Se mudar de ideia, é só me avisar. Posso ajudar em mais alguma coisa?"


def falha_ferramenta(e: Estado, p: dict) -> str:
    base = ("Tive um problema na consulta e não vou arriscar uma resposta sem confirmar. "
            "Pode tentar de novo em instantes?")
    if e.falhas_seguidas >= 2:
        return base[:-len("Pode tentar de novo em instantes?")] + f"Se preferir, registro o problema para um atendente. {CONFIRMA}"
    return base


def identidade(e: Estado, p: dict) -> str:
    nome = _condicoes(e).get("empresa.nome_fantasia")
    de = f" do {nome}" if nome else ""
    return (f"Sou a Lia, assistente virtual{de}. Não sou uma pessoa: respondo de forma automática, com as informações "
            "que tenho da nossa loja. Posso ajudar com produtos e preços, pedidos, pagamento, frete, trocas e devoluções, horário e "
            "endereço. Se quiser falar com um atendente, é só pedir.")


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


def carrinho_chat(e: Estado, p: dict) -> str:
    return ("Eu não altero o carrinho por aqui. No carrinho do site você consegue mudar as quantidades, tirar itens "
            "e ver o total. É só abrir o link abaixo.")


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
        txt = f"Na devolução por arrependimento, {corpo}."
    else:
        txt = f"Na devolução por arrependimento, o reembolso sai em até {dias} dias úteis."
    arrep = _condicoes(e).get("regra.arrependimento")
    if arrep:  # a condição de elegibilidade vai junto da forma e do prazo
        online = " em compra online" if arrep.get("aplica_a") == "compra_online" else ""
        estado = f", com o produto {arrep['estado_exigido']}" if arrep.get("estado_exigido") else ""
        txt += f" Vale{online}, em até {_prazo(arrep)}{estado}."
    return f"{txt} {NAO_CONFIRMO}"


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
        txt += f"\nQuer que eu registre para um atendente verificar o atraso? {CONFIRMA}"
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
            f"Quer que eu registre a dúvida para um atendente? {CONFIRMA}")


def pix_sobre_promocao(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if c.get("promocoes.pix_sobre_preco_promocional") is not False:
        return sem_dado(e, p)
    return ("Não: o desconto do PIX não se aplica sobre preço promocional. Produto em promoção vale o preço "
            "promocional, e o desconto do PIX só vale para produto sem promoção.")


def sem_info(e: Estado, p: dict) -> str:
    tema = p.get("tema") or "esse assunto"
    return (f"Não tenho essa informação sobre {tema}, então prefiro não afirmar nada. "
            f"Quer que um atendente confirme para você? {CONFIRMA}")


def perguntas_repetidas(e: Estado, p: dict) -> str:
    return ("Parece que não estou conseguindo avançar com essa informação, desculpe. "
            f"Posso registrar o seu caso para um atendente te ajudar? {CONFIRMA}")


def atendente_ja_registrado(e: Estado, p: dict) -> str:
    txt = (f"Você já tem um chamado registrado, protocolo {p['protocolo']}. "
           "Ele já está na fila de atendimento, então não abri outro.")
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
    return f"Posso registrar isso para um atendente? {CONFIRMA}"


def nao_entendi(e: Estado, p: dict) -> str:
    return ("Não entendi bem. Posso ajudar com produtos e preços, pedidos, pagamento, frete, trocas e devoluções, "
            "horário e endereço. Pode me dizer de outro jeito?")


def nao_entendi_de_novo(e: Estado, p: dict) -> str:
    return f"Ainda não consegui entender, desculpe. Quer que um atendente te ajude? {CONFIRMA}"


def ok_sem_retomar(e: Estado, p: dict) -> str:
    return "Tudo bem, deixei esse assunto de lado. Em que mais posso ajudar?"


def retomar(e: Estado, p: dict) -> str:
    assunto = ROTULOS_ASSUNTO.get(p["assunto"], "o assunto anterior")
    return f"Antes estávamos falando sobre {assunto}. Quer retomar? {CONFIRMA}"


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
    return (f"Pelas nossas regras, a garantia não cobre: {_sentenca(achados[0])}. Por isso esse caso não entra em troca por "
            "defeito nem por preferência. Se o seu caso for outro, é só me contar.")


def avaria_recebimento(e: Estado, p: dict) -> str:
    return ("Se o produto chegou com avaria, o certo é recusar o recebimento e falar com a nossa loja imediatamente. "
            f"Quer que eu registre o problema para um atendente? {CONFIRMA}")


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
        partes.append("Dependendo do caso, cabe " + " ou ".join(cabe) + ". " + NAO_CONFIRMO)
    return " ".join(partes)


def defeito_apos_prazo(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    regra = c.get("regra.defeito")
    if not regra or not c.get("defeito.apos_prazo_aciona_fabricante"):
        return sem_dado(e, p)
    ped = e.coletados.get("pedido") or {}
    quando = f"O pedido é de {_data_br(ped['data_pedido'])} e passaram os" if ped.get("data_pedido") else "Passados os"
    inter = (" Nós podemos intermediar o processo, se você pedir."
             if c.get("defeito.loja_pode_intermediar_mediante_solicitacao") else "")
    legal, fab = c.get("regra.garantia_legal"), c.get("garantia.fabricante_prazo_meses")
    garantias = ""
    if legal:
        garantias = (f" Há também a garantia legal de {legal['prazo_dias']} dias contra defeito de fabricação, contados do "
                     f"{legal['marco_inicial']}")
        garantias += (f", e a garantia do fabricante, de {fab['min']} meses a {fab['max'] // 12} anos, descrita no certificado "
                      "do produto." if fab else ".")
        if "prazo_30_x_90" in _ambiguidades(e):
            garantias += " Como esses prazos se combinam, um atendente confirma o seu caso."
    return (f"{quando} {regra['prazo_dias']} dias para troca por defeito. Depois desse prazo a garantia é acionada "
            f"direto com o fabricante.{garantias}{inter} Quer que eu registre o pedido de intermediação para um atendente? {CONFIRMA}")


def cancelar_pedido(e: Estado, p: dict) -> str:
    return ("O cancelamento de pedido não é feito por aqui; só um atendente consegue fazer. "
            f"Quer que eu registre o pedido de cancelamento para um atendente? {CONFIRMA}")


def retorno_prazo(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    prazo = c.get("atendimento.prazo_retorno_reclamacao_horas_uteis")
    if not prazo:
        return sem_dado(e, p)
    return f"O retorno de um atendente é em até {prazo} horas úteis." + _retorno_e_canais(e, "horas úteis")


def intermediacao(e: Estado, p: dict) -> str:
    if not _condicoes(e).get("defeito.loja_pode_intermediar_mediante_solicitacao"):
        return sem_dado(e, p)
    return ("Sim, nós podemos intermediar o processo da garantia com o fabricante, mediante a sua solicitação. "
            f"Quer que eu registre o pedido de intermediação para um atendente? {CONFIRMA}")


def posvenda_fora_do_prazo(e: Estado, p: dict) -> str:
    """Aplica o prazo do manual ao tempo que o cliente disse, sem repetir a regra inteira."""
    c = _condicoes(e)
    dias, prazo = p["dias"], p["prazo"]
    if p["objetivo"] == "devolucao":
        regra = f"a devolução por arrependimento vale por {prazo} dias corridos, contados do recebimento"
    else:
        regra = f"a troca por preferência vale por {prazo} dias"
    txt = f"Pelo que você contou, já se passaram {dias} dias, e {regra}; por isso esse caso está fora do prazo."
    if p.get("usado"):
        txt += " Além disso, o produto precisa estar na embalagem original e sem sinais de uso."
    defeito = c.get("regra.defeito")
    txt += (f" Se houver defeito de fabricação, a troca vale por {defeito['prazo_dias']} dias da compra, e depois disso há a garantia."
            if defeito else " Se houver defeito de fabricação, é outro caminho, com outro prazo.")
    return txt + f" Se tiver outra data de recebimento, me diga. Quer que um atendente avalie o seu caso? {CONFIRMA}"


def devolucao_frete(e: Estado, p: dict) -> str:
    if not _condicoes(e).get("devolucao.arrependimento_frete_por_conta_da_loja"):
        return sem_dado(e, p)
    return ("Na devolução por arrependimento, o frete de devolução é por nossa conta. "
            + NAO_CONFIRMO)


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
        txt += f" pelo nosso WhatsApp ou e-mail ({' / '.join(canais)})." if canais else "."
    return txt


def empresa_dados(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    nome, foco = c.get("empresa.nome_fantasia"), p.get("foco") or ["fundacao"]
    partes = []
    if "fundacao" in foco and c.get("empresa.fundacao_ano"):
        end = c.get("empresa.endereco") or {}
        onde = f" em {end['cidade']}" if end.get("cidade") else ""
        partes.append(f"O {nome} foi fundado em {c['empresa.fundacao_ano']}{onde}.")
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
    base = c.get("frete.cidade_base", "a nossa cidade")
    return (f"{m['nome']}: {prazo['min']} a {prazo['max']} dias úteis{extra}. Vale para envios fora de {base}. "
            "Para estimar o valor, me diga o produto e o CEP de entrega.")


def frete_mais_rapido(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    mods = sorted(c.get("frete.outras_cidades_modalidades") or [],
                  key=lambda m: (m["prazo_dias_uteis"]["max"], m["prazo_dias_uteis"]["min"]))
    if not mods:
        return sem_dado(e, p)
    base = str(c.get("frete.cidade_base", ""))
    prazo_base = c.get("frete.prazo_dias_uteis")
    if p.get("cidade") and base and normalizar(str(p["cidade"])) == normalizar(base) and prazo_base:
        return (f"Em {base} a entrega é feita por motoboy próprio, em {prazo_base['min']} a {prazo_base['max']} dias úteis.")
    rapida, outras = mods[0], mods[1:]
    destino = f"Para {str(p['cidade']).title()}, o" if p.get("cidade") else "O"
    txt = f"{destino} mais rápido é o {_modalidade_com_prazo(rapida)}."
    if outras:
        txt += " Os outros são " + _lista([_modalidade_com_prazo(m) for m in outras]) + "."
    return txt + " O prazo vale para envios fora de " + (base or "a nossa cidade") + "; o valor depende do CEP."


def frete_grande_porte(e: Estado, p: dict) -> str:
    return (f"Para {str(p['cidade']).title()}, {p['item']} são instrumentos de grande porte e o frete tem cotação "
            "individual, e daqui eu não consigo informar o valor.")


def motivo_cancelamento(e: Estado, p: dict) -> str:
    ped = e.coletados["pedido"]
    if ped["status"] != "cancelled":
        return (f"O pedido {ped['pedido_id']} não está cancelado: ele {FRASE_STATUS.get(ped['status'], 'está em andamento')}.")
    if ped.get("nota"):
        return f"Pelo registro do pedido {ped['pedido_id']}: {ped['nota']}."
    return (f"O registro do pedido {ped['pedido_id']} não traz o motivo do cancelamento, e eu não vou supor um. "
            f"Quer que eu registre a dúvida para um atendente? {CONFIRMA}")


def reembolso_cancelado(e: Estado, p: dict) -> str:
    ped = e.coletados["pedido"]
    dias = _condicoes(e).get("devolucao.arrependimento_reembolso_dias_uteis_max")
    forma = _forma_pedido(ped.get("forma_pagamento") or "")
    pago = f" no {forma}" if forma and forma.startswith("PIX") else (f" no {forma}" if forma else "")
    if not dias:
        return sem_dado(e, p)
    return (f"O pedido {ped['pedido_id']} está cancelado e foi pago{pago}. Pela nossa regra de reembolso, o valor volta "
            f"na mesma forma de pagamento em até {dias} dias úteis. Se o prazo passar, um atendente pode avaliar o seu caso, é só pedir.")


def soma_dois(e: Estado, p: dict) -> str:
    """Soma das condições dos dois últimos produtos citados, com os valores que a ferramenta devolveu."""
    calc = [x.resultado.dados for x in e.passos if x.ferramenta == "calcular_condicoes" and x.resultado.estado == "ok"]
    forma = p.get("forma", "pix")
    linhas, total, tabela = [], 0, 0
    for d in calc[-2:]:
        total += d["final_centavos"]
        tabela += d["original_centavos"]
        linhas.append(f"- {d['produto_nome']}: {formatar(d['final_centavos'])}")
    if forma == "credito":
        parcela = sum(d["parcela_centavos"] for d in calc[-2:])
        fecho = f"Os dois juntos, no crédito em {p.get('parcelas', 1)}x: {formatar(parcela)} por mês (total {formatar(total)})."
    elif forma == "pix":
        fecho = f"Os dois juntos, no PIX: {formatar(total)} (preço de tabela somado: {formatar(tabela)})."
    else:
        fecho = f"Os dois juntos: {formatar(total)}."
    return "Somando os dois últimos produtos que você viu:\n" + "\n".join(linhas) + "\n" + fecho


def diferenca_dois(e: Estado, p: dict) -> str:
    """Diferença de preço entre os dois últimos produtos citados, calculada sobre os valores das ferramentas."""
    calc = [x.resultado.dados for x in e.passos if x.ferramenta == "calcular_condicoes" and x.resultado.estado == "ok"][-2:]
    a, b = calc
    maior, menor = (a, b) if a["original_centavos"] >= b["original_centavos"] else (b, a)
    dif = maior["original_centavos"] - menor["original_centavos"]
    if dif == 0:
        return f"{a['produto_nome']} e {b['produto_nome']} têm o mesmo preço de tabela, {formatar(a['original_centavos'])}."
    txt = (f"O {maior['produto_nome']} custa {formatar(dif)} a mais que o {menor['produto_nome']} no preço de tabela "
           f"({formatar(maior['original_centavos'])} contra {formatar(menor['original_centavos'])}).")
    dif_final = maior["final_centavos"] - menor["final_centavos"]
    if p.get("forma", "pix") == "pix" and dif_final != dif:
        txt += f" No PIX, a diferença é de {formatar(dif_final)}."
    return txt


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
        negacao_atendente, chamado_registrado, registro_falhou, registro_cancelado, falha_ferramenta, sem_dado, sem_info, pix_sobre_promocao,
        nao_entendi, nao_entendi_de_novo, ok_sem_retomar, confirmar_registro, produto_indisponivel, promocoes,
        recusa_manipulacao, recusa_pedido_indevido, seguro_envio, recusa_dado_de_terceiro, fora_escopo_geral, perguntas_repetidas,
        atendente_ja_registrado, trocas_info, trocas_detalhe, dado_recusado, frete_prazo,
        item_nao_elegivel, identidade, encerramento, confirmacao_solta, recusa_instrucoes, carrinho_chat, reembolso_prazo,
        previsao_entrega, extremo_lista, frete_outra_cidade, frete_estimado, frete_cotacao_individual,
        frete_cep_indisponivel, frete_cep_nao_encontrado, frete_pedir_produto, frete_pedir_cep, frete_cidade_base,
        escolha_produto_curta, objecao_preco, vou_pensar, garantia_excluida, avaria_recebimento, devolucao_loja_fisica,
        defeito_apos_prazo, devolucao_frete, rain_check, rastreio_como, privacidade, empresa_dados, frete_modalidade,
        frete_grande_porte, parecidos, soma_dois, diferenca_dois, motivo_cancelamento, reembolso_cancelado, frete_produto,
        cupom_inexistente, endereco_pedido_privado, acolhimento, so_portugues, comparacao,
        preco_pix_e_parcelas, combinacao_formas, ficha_produto, frete_mais_rapido, frete_gratis_valor, cancelar_pedido,
        retorno_prazo, intermediacao, posvenda_fora_do_prazo)
}


def renderizar(chave: str, estado: Estado, parametros: dict[str, Any]) -> str:
    return TEXTOS[chave](estado, parametros)
