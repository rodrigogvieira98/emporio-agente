"""Textos da Lia. Todo fato de loja vem de resultados de ferramenta, nunca de literais aqui.

Persona: assistente virtual, informal mas profissional. Sem travessão.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from .. import config
from ..dinheiro import formatar
from . import expediente
from .estado import Estado

ROTULOS_ASSUNTO = {
    "devolucao": "a devolução", "troca_preferencia": "a troca por preferência", "defeito": "o produto com defeito",
    "status_pedido": "a consulta do pedido", "preco_produto": "o preço do produto", "disponibilidade": "a disponibilidade",
    "busca_produto": "a busca de produtos", "frete": "o frete", "reclamacao": "a reclamação", "garantia": "a garantia",
    "pagamento": "as formas de pagamento",
}
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
ROTULO_FORMA = {"pix": "PIX", "debito": "cartão de débito", "boleto": "boleto", "credit": "cartão de crédito"}
CONFIRMA = "Responda sim ou não."


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
    return f"No momento a loja está fora do expediente. A equipe volta {r['quando']} às {r['hora']}."


# --- textos --------------------------------------------------------------------------------

def saudacao(e: Estado, p: dict) -> str:
    nome = _condicoes(e).get("empresa.nome_fantasia")
    de = f" da {nome}" if nome else ""
    txt = (f"Oi! Eu sou a Lia, assistente virtual{de}. Posso ajudar com produtos, preços, pedidos, trocas e "
           "devoluções. Como posso ajudar?")
    aviso = _aviso_expediente(e)
    return f"{txt} {aviso}".strip()


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
        txt += "\nEu não tenho o calendário de feriados, então em feriado vale confirmar com a equipe."
    sit = expediente.situacao(c["horario.funcionamento"], config.agora())
    txt += "\nAgora a loja está aberta." if sit["aberto"] else "\n" + _aviso_expediente(e)
    return txt


def endereco(e: Estado, p: dict) -> str:
    end = _condicoes(e).get("empresa.endereco")
    if not end:
        return sem_dado(e, p)
    return (f"Estamos na {end['logradouro']}, {end['numero']}, bairro {end['bairro']}, "
            f"{end['cidade']} - {end['uf']}, CEP {end['cep']}.")


def contato(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    telefones: dict[str, list[str]] = {}
    for chave, onde in (("contato.telefone_whatsapp_dados_empresa", "telefone e WhatsApp nos dados da empresa"),
                        ("contato.whatsapp_secao_7", "canal de WhatsApp para atendimento remoto"),
                        ("contato.telefone_capa", "telefone na capa do manual")):
        if chave in c:
            telefones.setdefault(c[chave], []).append(onde)
    emails: dict[str, list[str]] = {}
    for chave, onde in (("contato.email_capa", "grafia da capa do manual"),
                        ("contato.email_dados_empresa", "grafia dos dados da empresa")):
        if chave in c:
            emails.setdefault(c[chave], []).append(onde)
    if not telefones and not emails:
        return sem_dado(e, p)
    linhas = [f"- {num} ({_lista(ondes)})" for num, ondes in telefones.items()]
    linhas += [f"- e-mail {mail} ({_lista(ondes)})" for mail, ondes in emails.items()]
    txt = "Estes são os contatos que constam no manual da loja:\n" + "\n".join(linhas)
    amb = _ambiguidades(e)
    if "telefone_whatsapp" in amb or "email" in amb:
        txt += ("\nO manual traz mais de um número e mais de uma grafia de e-mail, e eu não consigo confirmar "
                "qual é o oficial. Se não funcionar, posso pedir para a equipe confirmar.")
    return txt


def pagamento(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if "pagamento.pix_desconto_percentual" not in c:
        return sem_dado(e, p)
    linhas = [f"- PIX: {c['pagamento.pix_desconto_percentual']}% de desconto sobre o preço de tabela"]
    if c.get("pagamento.debito_a_vista"):
        linhas.append("- Cartão de débito: à vista")
    if "pagamento.credito_parcelas_max" in c:
        sem = " sem juros" if c.get("pagamento.credito_sem_juros") else ""
        linhas.append(f"- Cartão de crédito: até {c['pagamento.credito_parcelas_max']}x{sem}")
    if c.get("pagamento.boleto_a_vista"):
        compensa = c.get("pagamento.boleto_compensacao_dias_uteis_max")
        linhas.append("- Boleto: à vista" + (f", compensação em até {compensa} dias úteis" if compensa else ""))
    txt = "Formas de pagamento:\n" + "\n".join(linhas)
    if "pagamento.parcelamento_faixas" in c:
        faixas = [f"{f['de']}x a {f['ate']}x: parcela mínima {formatar(f['parcela_minima_centavos'])}"
                  for f in c["pagamento.parcelamento_faixas"]]
        txt += "\nParcela mínima por faixa: " + "; ".join(faixas) + "."
    if "parcela_minima" in _ambiguidades(e) and "pagamento.credito_parcela_minima_tabela_centavos" in c:
        txt += (f" A tabela de pagamento fala em {formatar(c['pagamento.credito_parcela_minima_tabela_centavos'])} "
                "por parcela, então em casos de limite a equipe confirma.")
    return txt + "\nSe quiser, me diga o produto e o número de parcelas que eu calculo."


def frete_info(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if "frete.gratis_acima_centavos" not in c:
        return sem_dado(e, p)
    prazo = c.get("frete.prazo_dias_uteis", {})
    base = c.get("frete.cidade_base", "a cidade da loja")
    txt = (f"Para {base}: frete grátis em pedidos acima de {formatar(c['frete.gratis_acima_centavos'])}; abaixo "
           f"disso, taxa fixa de {formatar(c['frete.taxa_abaixo_centavos'])}.")
    if prazo:
        txt += f" Prazo de {prazo['min']} a {prazo['max']} dias úteis."
    mods = c.get("frete.outras_cidades_modalidades", [])
    if mods:
        txt += " Para outras cidades o envio é por " + _lista([m["nome"] for m in mods]) + ", com valor calculado pelo CEP."
    return txt + "\nMe diga a cidade e o valor do pedido que eu confirmo o frete."


def pedir_valor_pedido(e: Estado, p: dict) -> str:
    return "Para calcular o frete, qual é o valor aproximado do pedido?"


def frete_calculado(e: Estado, p: dict) -> str:
    r = _dados(e, "calcular_condicoes")
    f = r.get("frete", {})
    cidade = e.coletados.get("cidade", "").title()
    prazo = f.get("prazo_dias_uteis")
    prazo_txt = f" Prazo de {prazo['min']} a {prazo['max']} dias úteis." if prazo else ""
    sit = f.get("situacao")
    if sit == "gratis":
        return f"Para {cidade}, com esse valor o frete é grátis.{prazo_txt}"
    if sit == "taxa":
        return f"Para {cidade}, o frete é uma taxa fixa de {formatar(f['taxa_centavos'])}.{prazo_txt}"
    if sit == "requer_confirmacao":
        return (f"Esse valor é exatamente o limite do frete grátis e o manual não diz o que vale nesse caso, "
                f"então a equipe precisa confirmar.{prazo_txt} Quer que eu registre a dúvida para eles? {CONFIRMA}")
    mods = _condicoes(e).get("frete.outras_cidades_modalidades")
    extra = f" Os envios são por {_lista([m['nome'] for m in mods])}." if mods else ""
    return (f"Para {cidade} o frete depende de cotação: ele é calculado pelo CEP, peso e dimensões do produto, "
            f"e eu ainda não consigo informar o valor.{extra}")


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
        txt += " O manual não explica como esses dois prazos se combinam, então a equipe confirma o seu caso."
    fab = c.get("garantia.fabricante_prazo_meses")
    if fab:
        txt += (f" Os fabricantes costumam ter garantia própria, de {fab['min']} meses a {fab['max'] // 12} anos, "
                "descrita no certificado que acompanha o produto.")
    nao = c.get("garantia.nao_cobre")
    if nao:
        txt += " Não cobre: " + "; ".join(x[0].lower() + x[1:] for x in nao) + "."
    return txt + "\nSe estiver com problema em algum produto, me conta que eu te ajudo a abrir a solicitação."


def busca(e: Estado, p: dict) -> str:
    r = e.ultimo("buscar_produtos")
    if r is None:
        return falha_ferramenta(e, p)
    if r.estado == "vazio":
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
    return cab + "\n" + "\n".join(linhas) + "\nOs valores são o preço de tabela. Quer ver as condições de algum deles?"


def pedir_categoria(e: Estado, p: dict) -> str:
    return "Que tipo de instrumento você procura? Pode dizer também uma marca ou uma faixa de preço."


def pedir_produto(e: Estado, p: dict) -> str:
    return "Qual produto? Me diga a marca e o modelo."


def produto_nao_encontrado(e: Estado, p: dict) -> str:
    return "Não encontrei esse produto no sistema. Pode me dizer a marca e o modelo do jeito que está no anúncio?"


def escolha_produto(e: Estado, p: dict) -> str:
    opcoes = e.coletados.get("opcoes", [])
    linhas = [f"{i}) {o['nome']}" for i, o in enumerate(opcoes, start=1)]
    return "Achei mais de um modelo parecido:\n" + "\n".join(linhas) + "\nQual deles? Pode responder com o número."


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
    else:
        txt += " Não consegui consultar alternativas agora."
    return txt


def promocoes(e: Estado, p: dict) -> str:
    r = e.ultimo("listar_promocoes")
    if r is None:
        return falha_ferramenta(e, p)
    if r.estado == "vazio":
        termo = r.dados.get("termo")
        if termo:
            return (f"A promoção {termo.title()} não está ativa no sistema agora, então não posso prometer esse "
                    "desconto. Se quiser, mostro as promoções que estão ativas.")
        return "No sistema não há nenhuma promoção ativa agora."
    linhas = []
    for i in r.dados["promocoes"]:
        extra = "" if i["situacao_venda"] == "disponivel" else f" ({SITUACAO.get(i['situacao_venda'])})"
        if i["conflito"]:
            linhas.append(f"- {i['produto_nome']}: {i['percentual']}% de desconto, preço original "
                          f"{formatar(i['original_centavos'])}; há mais de uma promoção ativa e a equipe confirma o valor{extra}")
        else:
            linhas.append(f"- {i['produto_nome']}: de {formatar(i['original_centavos'])} por "
                          f"{formatar(i['final_centavos'])} ({i['percentual']}% de desconto){extra}")
    return "Promoções ativas no sistema:\n" + "\n".join(linhas) + "\nO desconto do PIX não soma com preço promocional."


def recusa_manipulacao(e: Estado, p: dict) -> str:
    pix = _condicoes(e).get("pagamento.pix_desconto_percentual")
    extra = f" e o desconto de {pix}% no PIX" if pix else ""
    return ("Não consigo atender esse pedido. Os descontos que eu informo são só os das promoções ativas no sistema"
            f"{extra}. Quer ver as promoções ativas?")


def recusa_dado_de_terceiro(e: Estado, p: dict) -> str:
    return ("Não passo dados pessoais de clientes, como telefone, e-mail, endereço ou nome. Se o pedido é seu, posso "
            "consultar o andamento com o número do pedido e os 4 últimos dígitos do telefone cadastrado.")


def fora_escopo_geral(e: Estado, p: dict) -> str:
    c = _condicoes(e)
    if not c.get("escopo.somente_instrumentos"):
        return sem_dado(e, p)
    return ("Esse assunto foge do que eu consigo ajudar por aqui. Sou a assistente da loja, que trabalha só com "
            "instrumentos musicais. Posso ajudar com produtos, preços, pedidos, trocas e devoluções?")


def disponibilidade(e: Estado, p: dict) -> str:
    d = _dados(e, "ver_produto")
    return f"{d['nome']}: {SITUACAO.get(d['situacao_venda'], d['situacao_venda'])}, conforme o estoque do sistema agora."


def preco(e: Estado, p: dict) -> str:
    d = _dados(e, "calcular_condicoes")
    nome = d["produto_nome"]
    partes = []
    if d.get("percentual"):
        partes.append(f"{nome}: preço de tabela {formatar(d['original_centavos'])}, promoção de {d['percentual']}% "
                      f"e preço final {formatar(d['final_centavos'])}. O desconto do PIX não soma com promoção.")
    elif d["forma"] == "pix":
        partes.append(f"{nome}: preço de tabela {formatar(d['original_centavos'])}. No PIX "
                      f"({d.get('pix_percentual')}% de desconto) fica {formatar(d['final_centavos'])}.")
    else:
        partes.append(f"{nome}: preço de tabela {formatar(d['original_centavos'])}.")
    if d["forma"] == "credito":
        partes.append(f"No crédito em {d['parcelas']}x, cada parcela fica em {formatar(d['parcela_centavos'])}.")
        if d["permitido"] == "sim":
            partes.append("Esse parcelamento atende a parcela mínima do manual.")
        elif d["permitido"] == "nao":
            partes.append("Esse parcelamento não atende a parcela mínima do manual.")
        else:
            partes.append(f"O manual tem duas leituras para a parcela mínima ({formatar(d['minimo_tabela_centavos'])} "
                          f"na tabela e {formatar(d['minimo_faixa_centavos'])} na faixa de {d['parcelas']}x), "
                          f"então a equipe precisa confirmar. Quer que eu registre a dúvida para eles? {CONFIRMA}")
    if d.get("situacao_venda") not in (None, "disponivel"):
        partes.append(f"Atenção: o produto está {SITUACAO.get(d['situacao_venda'])}.")
    return " ".join(partes)


def preco_promocao_conflitante(e: Estado, p: dict) -> str:
    return ("Esse produto aparece com mais de uma promoção ativa no sistema, e eu não vou chutar o preço. "
            f"Quer que eu registre para a equipe confirmar o valor? {CONFIRMA}")


def pedir_pedido(e: Estado, p: dict) -> str:
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
    status = STATUS_PEDIDO.get(ped["status"], ped["status"])
    forma = _forma_pedido(ped["forma_pagamento"])
    txt = (f"Pedido {ped['pedido_id']}: status {status}.\nItens: {itens}.\n"
           f"Total gravado no sistema: {formatar(ped['total_gravado_centavos'])} ({forma}).")
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


def _forma_pedido(bruto: str) -> str:
    if bruto.startswith("credit_"):
        return f"cartão de crédito em {bruto.split('_')[1]}"
    return ROTULO_FORMA.get(bruto, bruto)


def pedir_dados_posvenda(e: Estado, p: dict) -> str:
    ped = e.coletados["pedido"]
    campos = [CAMPOS.get(c, c) for c in p["campos"]]
    return (f"Encontrei o pedido {ped['pedido_id']}. Para organizar sua solicitação, me conta: {_lista(campos)}.")


def propor_posvenda(e: Estado, p: dict) -> str:
    ped, regra = e.coletados["pedido"], e.coletados["regra"]["valor"]
    itens = ", ".join(f"{i['quantidade']}x {i['nome']}" for i in ped["itens"])
    sistema = (f"pedido {ped['pedido_id']}, status {STATUS_PEDIDO.get(ped['status'], ped['status'])}, {itens}, "
               f"total gravado {formatar(ped['total_gravado_centavos'])}")
    if ped.get("previsao"):
        sistema += f", previsão de entrega {_data_br(ped['previsao'])}"
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
    amb = e.coletados["regra"].get("ambiguidades", [])
    nota = f" Ponto em aberto no manual: {amb[0]}" if amb else ""
    return (
        "Resumo da sua solicitação, separado por origem:\n"
        f"1) O que o sistema mostra: {sistema}.\n"
        f"2) O que você me informou (não verificado): {'; '.join(decl)}.\n"
        f"3) O que a equipe confirma: se o seu caso se enquadra na regra do manual ({condicao}, {marco_txt}{aplica}).{exigido}"
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
    base = ("Tive um problema ao consultar o sistema e não vou arriscar uma resposta sem confirmar. "
            "Pode tentar de novo em instantes?")
    if e.falhas_seguidas >= 2:
        return base[:-len("Pode tentar de novo em instantes?")] + f"Se preferir, registro o problema para a equipe. {CONFIRMA}"
    return base


def sem_dado(e: Estado, p: dict) -> str:
    return ("Não encontrei essa informação nos dados que eu tenho, e prefiro não inventar. "
            f"Quer que eu registre a dúvida para a equipe? {CONFIRMA}")


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


TEXTOS: dict[str, Callable[[Estado, dict], str]] = {
    f.__name__: f for f in (
        saudacao, horario, endereco, contato, pagamento, frete_info, pedir_valor_pedido, frete_calculado,
        fora_escopo, garantia_info, busca, pedir_categoria, pedir_produto, produto_nao_encontrado, escolha_produto,
        disponibilidade, preco, preco_promocao_conflitante, pedir_pedido, pedido_negado, pedido_negado_limite,
        status_pedido, pedir_dados_posvenda, propor_posvenda, reclamacao_empatia, pedir_relato, negacao_reclamacao,
        negacao_atendente, chamado_registrado, registro_falhou, registro_cancelado, falha_ferramenta, sem_dado,
        nao_entendi, nao_entendi_de_novo, ok_sem_retomar, confirmar_registro, produto_indisponivel, promocoes,
        recusa_manipulacao, recusa_dado_de_terceiro, fora_escopo_geral)
}


def renderizar(chave: str, estado: Estado, parametros: dict[str, Any]) -> str:
    return TEXTOS[chave](estado, parametros)
