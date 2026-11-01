"""Léxico para reconhecer intenção e dados na fala do cliente.

São palavras da conversa, não afirmações sobre a loja: nada aqui diz o que a loja vende,
cobra ou promete. Tudo já normalizado (sem acento, minúsculo).
"""
from __future__ import annotations

import re

# Ordem importa: a primeira que casar vence (com ajustes em percepcao.py).
PADROES_INTENCAO: list[tuple[str, re.Pattern[str]]] = [
    ("pedir_atendente", re.compile(
        r"\b(atendente|atendimento humano|humano|pessoa de verdade|gerente|responsavel|"
        r"falar com (alguem|uma pessoa|um humano|gente)|passa (pra|para) (alguem|um))\b")),
    ("reclamacao", re.compile(
        r"\b(reclam\w*|insatisf\w*|pessim\w*|horrivel|absurdo|inadmissivel|descaso|decepcion\w*|"
        r"indignad\w*|revoltad\w*|mau atendimento|atendimento ruim)\b")),
    ("devolucao", re.compile(r"\b(devol\w*|reembols\w*|arrepend\w*|estorno)\b")),
    ("defeito", re.compile(
        r"\b(defeit\w*|quebrou|quebrad\w*|nao (funciona|liga|afina|toca|sai som)|parou de funcionar|"
        r"danificad\w*|avaria\w*|chegou (riscad|amassad|quebrad|danificad)\w*)\b")),
    ("troca_preferencia", re.compile(r"\b(troc\w+)\b")),
    ("garantia", re.compile(r"\bgarantia\b")),
    ("frete", re.compile(r"\b(frete|entregam|enviam|entrega (para|pra|em)|cep)\b")),
    ("status_pedido", re.compile(r"\b(pedido|rastre\w*|encomenda|onde esta (meu|minha)|status)\b")),
    ("fora_escopo", re.compile(
        r"\b(cordas?(?! orquestrais?)|palhetas?|cabos?|cases?|capas?|pedais?|pedaleiras?|amplificador\w*|ampli|"
        r"afinador\w*|suporte|estante|correia|caixas? de som|fone\w*|microfone\w*)\b")),
    ("promocao", re.compile(
        r"\b(promocao|promocoes|desconto\w*|black friday|oferta\w*|liquidacao|queima de estoque|"
        r"valendo|vigente)\b")),
    ("preco_produto", re.compile(r"\b(preco\w*|valor|quanto (custa|sai|fica|e|esta|ta)|custa)\b")),
    ("pagamento", re.compile(
        r"\b(pagamento\w*|pagar|pix|boleto|cartao|credito|debito|parcel\w*|financia\w*)\b")),
    ("disponibilidade", re.compile(r"\b(disponivel|disponibilidade|disponiveis|estoque|tem (ai|ainda|ai ainda))\b")),
    ("horario", re.compile(r"\b(horario\w*|abre|abrem|fecha|fecham|funcionamento|aberto|aberta|que horas)\b")),
    ("endereco", re.compile(r"\b(endereco|onde fica|onde ficam|localiza\w*|como chegar)\b")),
    ("contato", re.compile(r"\b(telefone|whatsapp|zap|e-?mail|contato|ligar)\b")),
    ("saudacao", re.compile(r"\b(oi|ola|bom dia|boa tarde|boa noite|e ai|opa|tudo bem|eai)\b")),
]

# Pergunta de informação geral sobre troca, devolução ou garantia (sem caso próprio do cliente)
PERGUNTA_GERAL_TROCAS = re.compile(
    r"\b(como funciona\w*|qual (e )?a (politica|regra)\w*|quais (sao )?as (politicas|regras)|politica\w* (de|da|do|para)|"
    r"regras? (de|da|do|para)|voces (trocam|aceitam|fazem|tem|oferecem)|aceita(m)? (troca|devolucao)|"
    r"existe (troca|devolucao|garantia)|prazo (de|para|da|do) (troca|devolucao|garantia)|"
    r"(quero|queria|gostaria de) saber (como|se|qual|quais)|(como|quando) (e|sao) (a|as|o|os) )")
CASO_PROPRIO = re.compile(
    r"\b(meu|minha|meus|minhas|comprei|recebi|chegou|veio|me arrependi|preciso|"
    r"(quero|queria|gostaria de|vou|posso|consigo) (trocar|devolver)|pedido (n|no|numero)? ?\d+)\b")

# Pedido concreto: se vier junto de um desabafo, a intenção concreta manda e o desabafo só muda o tom.
CONCRETAS = {"preco_produto", "disponibilidade", "status_pedido", "horario", "endereco", "contato", "pagamento",
             "frete", "promocao", "garantia"}
RECLAMACAO_EXPLICITA = re.compile(r"\b(reclam\w*|mau atendimento|atendimento ruim)\b")

# palavra do cliente -> termo de categoria entendido por buscar_produtos
CATEGORIAS = {
    "violao": "violao", "violoes": "violao", "guitarra": "guitarra", "guitarras": "guitarra",
    "baixo": "baixo", "baixos": "baixo", "bateria": "bateria", "baterias": "bateria",
    "percussao": "percussao", "teclado": "teclado", "teclados": "teclado", "piano": "piano",
    "pianos": "piano", "sintetizador": "teclado", "sintetizadores": "teclado",
    "ukulele": "ukulele", "ukuleles": "ukulele", "ukelele": "ukulele", "ukeleles": "ukulele",
    "sax": "madeiras", "flauta": "madeiras", "flautas": "madeiras", "saxofone": "madeiras", "saxofones": "madeiras",
    "clarinete": "madeiras", "clarinetes": "madeiras", "oboe": "madeiras",
    "trompete": "metais", "trompetes": "metais", "trombone": "metais", "trombones": "metais",
    "tuba": "metais", "trompa": "metais", "sopro": "sopro",
    "violino": "cordas orquestrais", "violinos": "cordas orquestrais", "violoncelo": "cordas orquestrais",
    "violoncelos": "cordas orquestrais", "contrabaixo": "cordas orquestrais",
}

PALAVRAS_SOLTAS = set("""
a o as os um uma uns umas de do da dos das no na nos nas em para pra por com sem ao aos e ou que qual quais
quero queria gostaria preciso saber ver vejo mostra mostrar mostre procuro procurando busco buscando tem ter
tinha voces vcs ai ainda sobre meu minha meus minhas me te se la aqui esse essa isso isto este esta
pode poderia podem favor obrigado obrigada valeu informar informacao informacoes
preco precos valor valores custa custam quanto quantos sai fica ficam desconto promocao
pix boleto cartao credito debito vista vezes vez parcela parcelas parcelar parcelado parcelamento x
real reais r ate maximo minimo abaixo acima menos mais mil
disponivel disponiveis disponibilidade estoque modelo modelos opcao opcoes indica indicar recomenda recomendar
bom boa dia tarde noite oi ola tudo bem e ai
hoje agora atualmente mesmo la aquele aquela aquilo coisa negocio
instrumento instrumentos iniciante iniciantes barato baratos barata baratas melhor melhores
""".split())

AFIRMATIVO = re.compile(
    r"^(sim|s|pode|pode sim|pode ser|claro|ok|okay|isso|isso mesmo|confirmo|confirmado|quero|quero sim|"
    r"por favor|registra|registre|pode registrar|positivo|vamos|bora|com certeza|uhum|aham)\b")
NEGATIVO = re.compile(
    r"^(nao|n|negativo|agora nao|deixa|deixa pra la|melhor nao|cancela|cancelar|nao quero|nao precisa|nao obrigado)\b")

NEGA_RECLAMACAO = re.compile(r"\b(nao|sem|nem)\b(?:\s+\w+){0,4}?\s+(?:reclam\w*)")
ABRIR_RECLAMACAO = re.compile(
    r"\b(abrir|fazer|registrar|dar entrada|protocolar|formalizar|quero|queria|gostaria|preciso)\b"
    r"(?:\s+\w+){0,4}?\s+(?:reclam\w*)")
NEGA_ATENDENTE = re.compile(
    r"\b(nao|sem|nem)\b(?:\s+\w+){0,5}?\s+(?:atendente|humano|falar com|gerente|pessoa)")

CANAL_ONLINE = re.compile(r"\b(online|on-line|site|internet|app|aplicativo|pelo celular|ecommerce|e-commerce)\b")
CANAL_LOJA = re.compile(r"\b(na loja|loja fisica|presencial|presencialmente|fisica|no balcao)\b")
ESTADO_BOM = re.compile(
    r"\b(lacrad\w*|na caixa|embalagem original|na embalagem|sem uso|nunca usad\w*|novo|nova|intact\w*|"
    r"sem abrir|fechad\w*|perfeito estado|nem abri|nao abri|nunca abri|nem usei|nao usei|nunca usei|nem usad\w*|"
    r"sem nenhum uso|zerad\w*)\b")
ESTADO_RUIM = re.compile(
    r"\b(usad\w*|riscad\w*|arranhad\w*|sem caixa|sem embalagem|aberto|aberta|amassad\w*|ja toquei|ja usei)\b")

DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
PEDIDO_EXPLICITO = re.compile(r"\b(?:pedido|numero|nro|num)\s*(?:no\s*|n\s*)?#?\s*(\d{1,6})\b|#\s*(\d{1,6})\b")
FINAL_EXPLICITO = re.compile(r"\b(?:final|ultimos|terminad\w*|terminando)\s*(?:em|com|de|do telefone|e)?\s*(\d{4})\b")
TELEFONE_COMPLETO = re.compile(r"\(?\b\d{2}\)?[\s.-]*9?\d{4}[\s.-]?\d{4}\b")

# Pedidos que o agente recusa sem consultar nada.
MANIPULACAO = re.compile(
    r"\b(ignor\w+|esquec\w+|desconsider\w+)\b.{0,40}\b(instruc\w*|regras?|prompt|anterior\w*|orientac\w*)\b"
    r"|\b(system prompt|prompt|suas instrucoes|suas regras|modo desenvolvedor|jailbreak|finja que)\b")
DADO_DE_TERCEIRO = re.compile(
    r"\b(telefone|celular|fone|e-?mail|endereco|cpf|nome|sobrenome|dados|contato)\b.{0,30}"
    r"\b(do cliente|da cliente|do comprador|do dono|do titular|de outro cliente|de outra pessoa|de quem comprou)\b"
    r"|\bquem (comprou|fez o pedido|e o dono|e o cliente)\b")
FORA_DO_ASSUNTO = re.compile(
    r"\b(copa|futebol|campeonato|time de|jogo de|presidente|eleicao|eleicoes|politica|previsao do tempo|"
    r"vai chover|clima|receita de|filme|serie|novela|noticia\w*|bitcoin|piada|horoscopo|signo|loteria|"
    r"quem (ganhou|descobriu|inventou|foi)|qual a capital|quanto e \d|traduz\w*|escreva um|poema|codigo em)\b")
