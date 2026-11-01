"""Léxico para reconhecer intenção e dados na fala do cliente.

São palavras da conversa, não afirmações sobre a loja: nada aqui diz o que a loja vende,
cobra ou promete. Tudo já normalizado (sem acento, minúsculo).
"""
from __future__ import annotations

import re

# Ordem importa: a primeira que casar vence (com ajustes em percepcao.py).
PADROES_INTENCAO: list[tuple[str, re.Pattern[str]]] = [
    # quem é a Lia: vem antes de pedir_atendente, porque "você é humano?" não é pedido de atendente
    ("identidade", re.compile(
        r"\b(quem (e|eh|seria) (voce|vc|tu|ai|a lia)|quem (esta|ta) (falando|ai|me atendendo|atendendo)|"
        r"com quem (eu )?(estou|to|tou|falo|converso)|"
        r"(isso|isto|aqui|aqui e|isso aqui) (e|eh) (um |uma )?(robo|bot|ia|maquina|pessoa|humano|gente)|"
        r"(voce|vc|tu) (e|eh|seria) (um |uma |o |a )?(robo|bot|chatbot|humano|humana|pessoa|gente|real|ia|"
        r"inteligencia artificial|maquina|atendente virtual|assistente)|"
        r"^(e|eh) (um |uma )?(robo|bot|chatbot|ia|maquina|pessoa de verdade|gente de verdade|humano|humana)\b|"
        r"(qual|como) (e )?(o )?(seu|teu) nome|como (voce )?(se chama|te chamo|posso te chamar)|seu nome|"
        r"o que (voce|vc|a lia) (faz|sabe|pode|consegue)|o que (voces|vcs) (fazem|sabem|podem|conseguem)|"
        r"(voce|vc) (faz|sabe fazer|serve para|serve pra) o que|para que (voce )?serve|"
        r"(em|com) o que (voce|vc) (pode|consegue) (me )?ajudar|como (voce|vc) pode (me )?ajudar)\b")),
    # "vou pensar": responde com respeito, manda o link do produto e não insiste
    ("vou_pensar", re.compile(
        r"\b(vou pensar|vou pensando|deixa eu pensar|deixe-me pensar|preciso pensar|vou ver isso|vou analisar|"
        r"vou avaliar|vou ver com calma|depois eu (vejo|volto|decido)|talvez depois|quero pensar)\b")),
    # seção 9 do manual: privacidade e dados pessoais (antes de "dado de terceiro" e de "fora de escopo")
    ("privacidade", re.compile(
        r"\b(privacidade|lgpd|dados pessoais|(meus|nossos) dados|(exclu\w+|apag\w+|delet\w+|remov\w+|elimin\w+) .{0,20}(dados|cadastro|conta|informacoes)|(nao quero|parar de|deixar de|cancel\w+|sair d\w+) .{0,25}(receber|recebo|recebendo) .{0,12}(promoc\w+|novidades|e-?mails?|mensagens|ofertas)|(nao quero|parar de) .{0,6}receber promoc\w+|"
        r"compartilh\w+ .{0,15}dados)\b")),
    ("empresa_dados", re.compile(
        r"\b(desde quando (a loja|voces|vcs|existe|funciona)|quando (a loja )?(foi )?(fundad\w+|criad\w+|aberta)|"
        r"fundad[oa]|fundacao|razao social|cnpj|quantos anos (a loja|de loja|de mercado|de atuacao)|"
        r"ha quanto tempo (a loja|voces|vcs) (existe|funciona|atua\w*))\b")),
    ("rain_check", re.compile(
        r"\b(rain check|(segurar|guardar|reservar|congelar|manter) (o |esse |este |isso |meu |nesse )?(preco|valor|promocao)|garantir (o )?(preco|valor) da promocao|"
        r"manter (o )?(preco|valor) da promocao|reservar (o )?(preco|valor)|congelar (o )?(preco|valor))\b")),
    ("devolucao_frete", re.compile(r"\b(frete\b.{0,40}\bdevol\w*|devol\w*.{0,40}\bfrete)\b")),
    ("rastreio_como", re.compile(
        r"\bcomo\b.{0,25}\b(recebo|receber|ganho|consigo|acompanho|acho|vejo|sei)\b.{0,30}\b(rastre\w*|codigo)\b|"
        r"\bonde\b.{0,20}\bcodigo de rastre\w*")),
    ("pedir_atendente", re.compile(
        r"\b(atendente|atendimento humano|humano|pessoa de verdade|gerente|responsavel|"
        r"falar com (alguem|uma pessoa|um humano|gente)|passa (pra|para) (alguem|um))\b")),
    ("reclamacao", re.compile(
        r"\b(reclam\w*|insatisf\w*|pessim\w*|horrivel|absurdo|inadmissivel|descaso|decepcion\w*|"
        r"indignad\w*|revoltad\w*|mau atendimento|atendimento ruim|"
        # queixa de atendimento: o conteúdo é a queixa, não um assunto de produto
        r"(vendedor|atendente|funcionari[oa]|gerente|atendimento)\b.{0,40}\b(grosso|grossa|grosseir\w+|rude|mal educad\w+|"
        r"debochou|ignorou|maltrat\w+|desrespeit\w+|ofendeu|despreparad\w+)|"
        r"\b(grosseria|grosseiro|grosseira|desrespeito|maltratad[oa]|mal atendid[oa])\b)\b")),
    # quanto tempo para o dinheiro voltar: informação do manual, antes de abrir fluxo de devolução
    ("reembolso_prazo", re.compile(
        r"\b((quanto tempo|quando|em quantos dias|em quanto tempo|qual o prazo|que prazo|prazo)\b.{0,40}"
        r"\b(dinheiro|reembols\w*|estorno|valor de volta|restitu\w*|receber de volta|pagamento de volta)|"
        r"(reembols\w*|estorno|dinheiro de volta)\b.{0,30}\b(quanto tempo|quantos dias|quando|prazo|demora\w*)|"
        r"(recebo|volta|devolvem|devolve|caem?|cai) (o |meu |de volta o )?(meu )?(dinheiro|reembolso|estorno|valor)\b)")),
    ("devolucao", re.compile(r"\b(devol\w*|reembols\w*|arrepend\w*|estorno|dinheiro de volta)\b")),
    ("defeito", re.compile(
        r"\b(defeit\w*|(entregador|transportadora|motoboy|carteiro)\b.{0,40}\b(amass\w+|danific\w+|quebr\w+|rasg\w+|estrag\w+)|"
        r"(amass\w+|danific\w+|quebr\w+|rasg\w+|estrag\w+)\b.{0,25}\bno (transporte|caminho|frete|envio)|quebrou|quebrad\w*|nao (funciona|liga|afina|toca|sai som)|parou de funcionar|"
        r"danificad\w*|avaria\w*|chegou (riscad|amassad|quebrad|danificad)\w*|"
        r"(caixa|embalagem|tampo|corpo|braco|violao|guitarra|instrumento|produto|case)\b.{0,25}\b"
        r"(amassad\w*|rachad\w*|trincad\w*|rasgad\w*|furad\w*|torto|torta))\b")),
    ("troca_preferencia", re.compile(r"\b(troc\w+)\b")),
    ("garantia", re.compile(r"\bgarantia\b")),
    # endereço de entrega de um pedido (dado do cliente): a Lia não mostra, e nunca o troca pelo endereço da loja
    ("endereco_pedido", re.compile(
        r"\b(endereco (?:de |da |do )?(?:entrega|cadastrad\w+|do pedido|do meu pedido|de envio)|"
        r"(?:em|pra|para) onde (?:vai|foi|sera|esta indo|vao) (?:ser )?(?:entreg\w+|enviad\w+|mandad\w+)|"
        r"onde (?:vai|foi|sera) (?:ser )?(?:entreg\w+|enviad\w+)|confirm\w+ (?:o )?endereco)\b")),
    ("frete", re.compile(r"\b(frete|entregam|enviam|entrega (para|pra|em)|cep)\b")),
    # quando o pedido chega: usa o pedido já consultado na conversa, se houver
    ("previsao_entrega", re.compile(
        r"\b(quando (chega|vai chegar|chegara|chegam|entrega|entregam|vou receber|recebo|sai|saiu)|"
        r"(qual|e a) (a )?previsao( de entrega| de chegada)?|ja (saiu|foi enviado|foi despachado)|chega (quando|que dia|hoje|amanha))\b")),
    # por que o pedido foi cancelado: responde com a observação gravada no pedido
    ("motivo_cancelamento", re.compile(
        r"\b(pq|por ?que|porque|motivo|razao)\b.{0,30}\bcancel\w+|\bcancel\w+.{0,20}\b(motivo|porque|razao)\b")),
    ("status_pedido", re.compile(r"\b(pedido|rastre\w*|encomenda|onde esta (meu|minha)|status)\b")),
    # produto parecido com o que está em foco: a mesma categoria, sem acessório
    ("parecido", re.compile(r"\b(parecid\w+|similar\w*|semelhante\w*|alternativ\w+|outro (modelo|igual)|algo assim)\b")),
    ("fora_escopo", re.compile(
        r"\b((?<!\d )(?<!\d)cordas?(?! orquestrais?)(?!\s+(?:\w+\s+)?(?:arrebent|rebent|estour|romp|partiu|soltou|enferruj|"
        r"oxid|gast|desgast))|palhetas?|cabos?|cases?|capas?|pedal|pedais|pedaleiras?|amplificador\w*|ampli|"
        r"afinador\w*|suporte|estante|correia|caixas? de som|fone\w*|microfone\w*)\b")),
    ("cupom", re.compile(r"\b(cupom|cupon|cupons|cupoes|voucher|codigo (?:promocional|de desconto|de cupom))\b")),
    ("promocao", re.compile(
        r"\b(promocao|promocoes|desconto\w*|black friday|oferta\w*|liquidacao|queima de estoque|"
        r"valendo|vigente)\b")),
    # objeção de preço ("tá caro"); "o mais caro" é pergunta de lista, não objeção
    ("objecao_preco", re.compile(
        r"(?<!mais )\b(ta |esta |achei |muito |bem |meio |super |um pouco )+(caro|salgado)\b|\bcaro demais\b|"
        r"\bsem condicoes de pagar\b|\bnao cabe no (meu )?(bolso|orcamento)\b|"
        r"\bfora do (meu )?orcamento\b|\bpesado no bolso\b|^(?:\w+ ){0,2}(?<!mais )(?:caro|carissimo|puxado)\W*$|"
        r"\b(precinho|fazer um preco|melhorar (o )?preco|baixar (o )?preco|abaixar (o )?preco|negociar|negociacao|"
        r"fazer (uma )?oferta|abatimento)\b")),
    ("preco_produto", re.compile(
        r"\b(preco\w*|valor|quanto (ele |ela |eles |elas |isso |esse |essa |os dois |as duas )?(custa|sai|fica|e|esta|ta)|custa)\b")),
    ("pagamento", re.compile(
        r"\b(pagamento\w*|pagar|pix|boleto|cartao|credito|debito|parcel\w*|financia\w*)\b")),
    ("disponibilidade", re.compile(r"\b(disponivel|disponibilidade|disponiveis|estoque|tem (ai|ainda|ai ainda))\b")),
    ("horario", re.compile(r"\b(horario\w*|abre|abrem|fecha|fecham|funcionamento|aberto|aberta|que horas)\b")),
    ("endereco", re.compile(r"\b(endereco|onde fica|onde ficam|localiza\w*|como chegar)\b")),
    ("contato", re.compile(r"\b(telefone|whatsapp|zap|e-?mail|contato|ligar)\b")),
    # característica técnica do instrumento: o catálogo não traz ficha técnica; última antes da saudação
    ("caracteristica", re.compile(
        r"\b(captac\w+|captador\w*|cutaway|ficha tecnica|especificac\w+|diferenca entre|timbre|slap|"
        r"qual (e )?(o )?melhor (pra|para))\b")),
    ("saudacao", re.compile(r"\b(oi|ola|bom dia|boa tarde|boa noite|e ai|opa|tudo bem|eai)\b")),
]

# Assunto que a loja não registra nos dados (QA 2): a Lia diz que não tem a informação e oferece atendente.
# Cada tema é lido por intenção ("tem onde estacionar"), nunca por frase inteira.
SEM_INFO = (
    ("estacionamento", re.compile(r"\b(estacionamento\w*|estacionar|onde estaciono|vagas? (de|pra|para) (carro|moto|estacion\w+))\b")),
    ("retirada na loja", re.compile(
        r"\b(retirada|retirar|retiro|retira\w*|(buscar|pegar|busco|pego|buscam|buscamos) (na|a) (loja|compra|encomenda)|"
        r"vcs buscam|voces buscam|(preciso|tenho que|tem que) levar na loja|levar na loja)\b")),
    ("instrumento usado", re.compile(
        r"\b((compr\w+|aceit\w+|vend\w+|troc\w+|recebem|pegam|negoci\w+)\b.{0,30}\b(usad[oa]s?|seminov[oa]s?|segunda mao)|"
        r"(usad[oa]s?|seminov[oa]s?|segunda mao)\b.{0,25}\b(voces|vcs|a loja)\b.{0,15}\b(compr\w+|aceit\w+|vend\w+))\b")),
    ("nota fiscal", re.compile(r"\b(nota fiscal|notas fiscais|nf-?e|nfe|danfe|nota no cnpj|nota em nome)\b")),
    # seguro dos envios (manual 5.2): tem resposta pela regra do manual; seguro de roubo ou de queda segue sem dado
    ("seguro_envio", re.compile(
        r"(?<!\be )\bseguro\b.{0,40}\b(envios?|frete|entrega\w*|transporte|extravi\w+|danos?|encomendas?)\b"
        r"|\b(envios?|frete|entrega\w*|transporte|encomendas?)\b.{0,40}(?<!\be )\bseguro\b")),
    ("extravio", re.compile(
        r"\b(extravi\w+|(se|caso) (o pedido |ele |ela |a encomenda |o produto )?(nao|nunca) chegar\w*|nunca chegou|"
        r"pedido (se )?perd\w+|perdeu (o )?pedido)\b")),
    ("seguro", re.compile(
        r"\b(seguro (cobre|cobrem|contra|do produto|do instrumento|de roubo|de queda)|(tem|ha|existe|contrat\w+|fazer|faz) (um )?seguro|o seguro)\b")),
)

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
CONCRETAS = {"preco_produto", "disponibilidade", "status_pedido", "previsao_entrega", "horario", "endereco", "contato",
             "pagamento", "frete", "promocao", "garantia"}
RECLAMACAO_EXPLICITA = re.compile(r"\b(reclam\w*|mau atendimento|atendimento ruim)\b")

# Despedida e agradecimento: só valem quando a mensagem não traz outro pedido.
ENCERRAMENTO = re.compile(
    r"\b(obrigad[oa]s?|brigad[oa]|valeu|vlw|agradec\w*|grat[oa]|tchau|xau|ate (logo|mais|breve|amanha|a proxima|depois)|"
    r"era so isso|e so isso|so isso mesmo|era isso|por hoje (e|eh) so|tudo certo|falou|flw|"
    r"boa (tarde|noite) pra voce|ate mais)\b")
# Pedido de instruções internas (sem tentativa de burlar regra): recusa própria, sem falar de desconto.
PEDIDO_INSTRUCOES = re.compile(
    r"\b(system prompt|prompt( de sistema| do sistema| inicial)?|suas instrucoes|tuas instrucoes|suas regras internas|"
    r"instrucoes (internas|do sistema|que voce recebeu)|como (voce )?foi (programad[oa]|configurad[oa]|treinad[oa])|"
    r"(mostre|mostra|me mostra|revele|revela|repita|repete|cole) .{0,25}(instrucoes|prompt|regras))\b")

# "o mais barato" / "o mais caro": só tem sentido sobre uma lista já mostrada
EXTREMO_MIN = re.compile(r"\b(mais barat\w+|mais em conta|menor preco|menor valor|mais economic\w+|mais acessiv\w+)\b")
EXTREMO_MAX = re.compile(r"\b(mais car[oa]s?|maior preco|maior valor)\b")
# Perguntas de informação simples que podem vir junto de outra na mesma mensagem
SECUNDARIAS = ("horario", "endereco", "contato")
# Palavras que indicam pergunta geral sobre pagamento (não é "e em 12x" de um produto)
PAGAMENTO_GERAL = re.compile(r"\b(quais|formas|aceita\w*|aceitam|como|posso|voces|vcs|quantas|ate quanto|parcelam|trabalham)\b")

PERGUNTA_PRAZO = re.compile(r"\b(prazo|demora\w*|quanto tempo|quantos dias|dias uteis|chega em)\b")

# Pedido de produto sem dizer qual: a Lia lista as categorias que têm o que vender.
PEDIDO_GENERICO = (r"\b((dar|presentear\w*|escolher|ganhar|comprar)\s+(um|uma|algum)\s+instrumentos?|"
                   r"instrumentos? (de|como) presente|me ajuda\w* (a|na|com a) escolh\w+|ajuda\w* (a|na) escolh\w+|"
                   r"o que (voces|vcs) (tem|vendem|trabalham)|(quais|que) (instrumentos|produtos) (voces )?(tem|vendem|existem)|"
                   r"(quero|queria|gostaria de|preciso de|procuro|busco|estou procurando) (encontrar|ver|comprar|achar)?\s*"
                   r"(um|uma|algum|alguns)?\s*instrumentos?)\b")

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
vende vendem vendo vender existe existem trabalha trabalham confirma confirmar confirmo
so apenas somente fala falar fale diga diz dizer estou estava sou nao nem pergunta perguntar duvida
ser seria sai comprar levar levo fechar carrinho adicionar adicione adiciona vou
pro faz ha so semana semanas dia dias mes meses ano anos
entregam entregar entrega enviam enviar envio frete envia entregamos coloca coloque colocar poe ponha joga bota manda mande pego pegar fechou
outro outra outros outras nossa nossa entao tambem ele ela dele dela deles delas dois duas ambos ambas cada mas ne hmm
ah poxa puxa caramba putz gostei legal otimo show beleza pois certo entendi tipo assim uns volta voltando ok
agora ainda talvez ja eu nos gente tambem outra vez fico ficar fica ficaria dar da dou
ta caro salgado super pouco muito achei meio demais pensar analisar avaliar depois talvez calma volto vejo decido
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
FINAL_EXPLICITO = re.compile(r"\b(?:final|ultimos|termina|terminad\w*|terminando|acaba|acabando)\s*(?:em|com|de|do telefone|e)?\s*(\d{4})\b")
TELEFONE_COMPLETO = re.compile(r"\(?\b\d{2}\)?[\s.-]*9?\d{4}[\s.-]?\d{4}\b")

# Pedidos que o agente recusa sem consultar nada.
MANIPULACAO = re.compile(
    r"\b(ignor\w+|esquec\w+|desconsider\w+)\b.{0,40}\b(instruc\w*|regras?|prompt|anterior\w*|orientac\w*)\b"
    r"|\b(modo desenvolvedor|jailbreak|finja que)\b")
# Autoridade alegada e pedido indevido: recusa, nunca chamado nem "não entendi". Ler a intenção, não a frase.
AUTORIDADE = re.compile(
    r"\b(aqui e|sou|eu sou|falo como|falo em nome d\w+)\s+(o |a |um |uma )?(gerente|dono|dona|diretor\w*|proprietari\w+|"
    r"administrador\w*|supervisor\w*|socio|ceo|funcionari\w+ da loja|da diretoria)\b"
    r"|\bautorizo\b|\b(modo|painel) admin\w*|\b(sistema|admin)\b\s*[\]:]|\[\s*sistema\s*\]|\batualizacao de preco\b")
PEDIDO_INDEVIDO = re.compile(
    r"\b(escreve|escreva|registre|registra|anote|anota|prometa|promete|assine|assina|confirme ao cliente)\b.{0,30}"
    r"\b(garant\w+|vend\w+|\d+\s*reais|gratis|desconto)\b"
    r"|\breserv\w+\b.{0,30}\bsem (pagar|pagamento|sinal|entrada)\b|\bsem pagar\b.{0,20}\breserv\w+")
# Pedido indevido que fala de preço ou desconto: a recusa cita as promoções; sem isso, a recusa é a curta.
TERMO_DE_DESCONTO = re.compile(r"\b(desconto\w*|promoc\w+|cupom\w*|preco\w*|valor\w*|gratis|reais|barat\w+|pix)\b|%")
DADO_DE_TERCEIRO = re.compile(
    r"\b(telefone|celular|fone|e-?mail|endereco|cpf|nome|sobrenome|dados|contato)\b.{0,30}"
    r"\b(do cliente|da cliente|do comprador|do dono|do titular|de outro cliente|de outra pessoa|de quem comprou)\b"
    r"|\bquem (comprou|fez o pedido|e o dono|e o cliente)\b"
    # dado pessoal de uma pessoa nomeada ("o e-mail do Bruno Martins"), não da loja
    r"|\b(telefone|celular|fone|e-?mail|cpf)\b\s+d[oae]s?\s+(?!loja\b|empresa\b|site\b|atendimento\b|suporte\b|"
    r"setor\b|financeiro\b|vendas\b|voces\b|vcs\b|pedido\b|entrega\b|gerente da loja\b)[a-z]{3,}")
FORA_DO_ASSUNTO = re.compile(
    r"\b(copa|futebol|campeonato|time de|jogo de|presidente|eleicao|eleicoes|politica|previsao do tempo|"
    r"vai chover|clima|receita de|filme|serie|novela|noticia\w*|bitcoin|piada|horoscopo|signo|loteria|"
    r"quem (ganhou|descobriu|inventou|foi)|qual a capital|quanto e \d|traduz\w*|escreva um|poema|codigo em)\b")

# Conformidade com o manual: sinais lidos na fala do cliente, nunca fatos da loja.
MAU_USO = re.compile(r"\b(caiu|cair|queda|derrub\w+|mau uso|molhou|molhad[oa]|umidade|chuva|bati|batida)\b")
NEGA_MAU_USO = re.compile(
    r"\b(sem|nem|nunca|nenhum[a]?|nao (?:teve|houve|sofreu|levou|deu|foi|caiu|bati|molhou))\b(?:\s+\w+){0,2}?\s+"
    r"(caiu|cair|queda|quedas|derrub\w+|molhou|molhad[oa]|umidade|chuva|bati|batida|mau uso)\b|"
    r"\b(?:nao|nunca)\s+(?:caiu|cai|bati|molhou)\b")
AVARIA = re.compile(
    r"\b(entregador|transportadora|motoboy|carteiro|transporte)\b.{0,40}\b(amass\w+|danific\w+|quebr\w+|rasg\w+|estrag\w+|derrub\w+|avari\w+)|"
    r"\b(amass\w+|danific\w+|quebr\w+|rasg\w+|estrag\w+)\b.{0,25}\bno (transporte|caminho|frete|envio)\b|"
    r"\b(chegou|veio|recebi|entregaram)\b.{0,30}\b(amassad\w*|riscad\w*|quebrad\w*|danificad\w*|avariad\w*|rasgad\w*|"
    r"furad\w*|torto|torta|trincad\w*)\b|\bavaria\w*|"
    r"\b(caixa|embalagem|tampo|corpo|braco|violao|guitarra|instrumento|produto|case)\b.{0,25}\b"
    r"(amassad\w*|rachad\w*|trincad\w*|rasgad\w*|furad\w*)\b")
# "esse", "essa guitarra", "ele": remetem ao produto em foco; "os dois" e a quantidade somam/multiplicam
DEMONSTRATIVO = re.compile(r"\b(esse|essa|esses|essas|este|esta|desse|dessa|deste|desta|dele|dela|nele|nela|ele|ela|"
                           r"o mesmo|a mesma)\b")
OS_DOIS = re.compile(r"\b(os dois|as duas|ambos|ambas|dos dois|das duas|o dois)\b")
_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6}
QUANTIDADE = re.compile(
    r"\b(?:comprar|levar|levo|quero|pegar|pego|fechar|compro)\s+(?:mais\s+)?(\d{1,2}|dois|duas|tres|quatro|cinco|seis)\b"
    r"(?!\s*(?:x|vezes|parcelas|reais|real|dias))|"
    r"\b(\d{1,2}|dois|duas|tres|quatro|cinco|seis)\s+(?:unidades?|pecas?|instrumentos?)\b")
# Pergunta em inglês: palavras que não existem em português; duas ou mais, e nenhuma palavra comum do português.
INGLES = {"the", "is", "what", "you", "ship", "shipping", "how", "much", "hi", "hello", "thanks", "thank", "open", "hours",
          "where", "can", "your", "are", "have", "buy", "delivery", "deliver", "return", "refund", "does", "store",
          "cost", "with", "for", "this", "that", "please", "price", "do", "time", "any", "guitar", "want", "need",
          "help", "ok", "order"}
INGLES_FORTE = INGLES - {"do", "ok", "order", "price", "time", "hi", "help", "any"}
PORTUGUES_COMUM = {"os", "as", "de", "da", "que", "para", "pra", "uma", "um", "nao", "quero", "preco",
                   "quanto", "voce", "voces", "vcs", "tem", "na", "por", "oi", "ola", "pedido", "obrigado",
                   "obrigada", "qual", "como", "isso", "esse", "essa", "meu", "minha", "custa", "quanto"}
TEMAS_INGLES = (
    (re.compile(r"\b(ship\w*|deliver\w*|freight|postage)\b"), "frete e entrega"),
    (re.compile(r"\b(price\w*|cost\w*|how much)\b"), "preço"),
    (re.compile(r"\b(open|opens|hours|close|closing|schedule)\b|what time"), "horário"),
    (re.compile(r"\b(return\w*|refund\w*|exchange|warranty)\b"), "troca, devolução ou garantia"),
    (re.compile(r"\b(order|tracking|track)\b"), "pedido"),
    (re.compile(r"\b(guitar\w*|bass|drum\w*|piano|keyboard|ukulele|violin|buy|product\w*)\b"), "produtos"),
)
AGRADECIMENTO_INGLES = re.compile(r"^\W*(?:ok\W+)?(?:thanks?|thank you|thx|bye|goodbye)\b")
PALAVRAS_COMPARACAO = {"diferenca", "diferencas", "entre", "comparar", "comparacao", "compara", "versus", "vs", "melhor",
                       "pior", "slap", "quero"}
COMPARACAO = re.compile(r"\b(diferenca entre|diferencas entre|comparar|comparacao|compara\w*|versus|vs|"
                        r"qual (?:e )?(?:o )?melhor entre|qual (?:a |o )?diferenca)\b")
# "Taylor 214ce ou Martin D-28E", "entre o X e o Y": só vale como comparação se as duas pontas forem produtos
ENTRE_OU = re.compile(r"\bentre\b|\bou\b")
SEPARADOR_COMPARACAO = re.compile(r"\s+(?:e|vs|versus|ou|x|contra|com)\s+(?:o |a |os |as )?|,\s*")
# Campanha sazonal citada pelo cliente (palavra da conversa, não afirmação sobre a loja): a ferramenta diz se está ativa.
CAMPANHA_CITADA = re.compile(
    r"\b(black friday|cyber monday|pascoa|natal|carnaval|ano novo|dia d[aeo]s? (?:maes|pais|criancas|namorados|mulheres|mae|pai)|"
    r"volta as aulas|aniversario da loja|semana do consumidor|liquida\w+ de \w+)\b")
CUPOM = re.compile(r"\b(cupom|cupon|cupons|cupoes|voucher|codigo (?:promocional|de desconto|de cupom))\b")
DESCONTO_CITADO = re.compile(r"\b(\d{1,2})\s*(?:%|por cento)")
# "e agora?", "o que eu faço?": pede o próximo passo do assunto de pós-venda em andamento
PROXIMO_PASSO = re.compile(r"\b(e agora|o que (eu )?faco|o que fazer|como (eu )?faco|e depois)\b")
DESGASTE = re.compile(
    r"\b(cordas?|palhetas?|trastes?|feltros?)\b.{0,25}\b(arrebent\w*|rebent\w*|estour\w*|romp\w*|partiu|gast\w*|desgast\w*|"
    r"enferruj\w*)|\b(arrebent\w*|rebent\w*|estour\w*|romp\w*)\b.{0,20}\b(cordas?|palhetas?)\b")
DIAS_DESDE_COMPRA =re.compile(r"\b(?:ha|faz|fazem|tem|completou|passou de|passaram)\s+(\d{1,3})\s+(dias?|semanas?|mes(?:es)?)\b")
EMPRESA_CNPJ = re.compile(r"\b(cnpj)\b")
EMPRESA_RAZAO = re.compile(r"\b(razao social)\b")
EMPRESA_FUNDACAO = re.compile(r"\b(desde quando|fundad\w+|fundacao|quantos anos|ha quanto tempo|quando (a loja )?(foi )?criad\w+)\b")
PIX_SOBRE_PROMO = re.compile(r"\b(promoc\w+|promociona\w+|em oferta|com desconto|ja tem desconto|em liquidacao)\b")
DEBITO_BANDEIRA = re.compile(r"\bbandeiras?\b")

# Intenção de compra ("quero comprar o Yamaha C40"): o texto segue sendo o preço; o botão de carrinho é gerado por código.
COMPRA = re.compile(
    r"\b((quero|queria|vou|gostaria de|posso|pretendo|decidi|bora|vamos|preciso) (comprar|levar|fechar)|"
    r"comprar (o|a|esse|essa|ele|ela|este|esta)|adicion\w+ (ao|no|o) carrinho|fechar (a )?compra|quero levar|"
    r"vou levar|levo (o|a|esse|essa|ele|ela)|"
    r"(quero|queria|vou querer|pego|vou pegar|fico com) (esse|essa|este|esta|ele|ela|o mesmo|a mesma)|"
    r"(quero|queria|vamos|bora|pode|posso|vou) fechar|fechar (o pedido|a venda)|"
    r"(coloc\w+|poe|ponha|pon\w+|por|adicion\w+|joga|bota|mand\w+) (ele |ela |esse |essa |isso |duas |dois |um |uma )?(no|ao|pro|para o) carrinho|"
    r"como (eu )?(faco |posso |consigo |faz |fa)?(pra |para )?(finaliz\w+|fechar|concluir)( a| o| minha| meu)?( compra| pedido)?)\b")
# Nível e orçamento ditos em palavras: qualificam a busca sem perguntar de novo.
NIVEL_INICIANTE = re.compile(r"\b(iniciantes?|principiantes?|comecando|comecar|aprender|aprendendo|estudantes?|"
                             r"primeiro (violao|instrumento|teclado|baixo|ukulele|bateria|guitarra))\b")
NIVEL_OUTRO = re.compile(r"\b(intermediari\w+|avancad\w+|profissional|profissionais|palco|banda|igreja|estudio|gravar)\b")
# Resposta que dispensa a pergunta de qualificação ("tanto faz", "sem preferência").
SEM_PREFERENCIA = re.compile(r"\b(tanto faz|qualquer (um|uma|coisa|modelo)|sem preferencia|nao tenho preferencia|nao sei)\b")
ORCAMENTO_BAIXO = re.compile(r"\b(barat\w+|em conta|economic\w+|pouco dinheiro|sem gastar muito)\b")
