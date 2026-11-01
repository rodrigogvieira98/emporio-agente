"""Redação delimitada: o modelo só escreve abertura ou fechamento curtos em volta do bloco factual.

O bloco vem de respostas.py e nunca é alterado. O texto livre só passa se não tiver dígito, moeda,
nome de produto fora do bloco, verbo de ação não confirmada, mais de 2 frases ou mais de 1 pergunta.
Reprovado, o texto livre é descartado e a resposta é só o bloco controlado.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from ..texto import normalizar, tokens
from . import catalogo, llm, persona
from . import vocabulario as v
from .concisao import deduplicar_frases, tem_saudacao
from .estado import Estado

SISTEMA = (
    "Escreva uma abertura curta e/ou um fechamento "
    "curto em volta do texto da loja que será mostrado ao cliente. Regras: no máximo 2 frases no total e no máximo "
    "1 pergunta; informal e educado; sem números, sem valores, sem nomes de produto, sem prometer nem dizer que fez "
    "algo (transferir, reservar, cancelar, aprovar). Se não houver nada útil a acrescentar, devolva null nos dois "
    "campos. Responda só com o JSON pedido."
)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"abertura": {"type": ["string", "null"]}, "fechamento": {"type": ["string", "null"]}},
    "required": ["abertura", "fechamento"],
}
VERBOS_NAO_CONFIRMADOS = re.compile(
    r"\b(transferi|reservei|cancelei|aprovei|estornei|reembolsei|enviei|agendei|liberei|registrei|encaminhei|"
    r"confirmei|devolvi|garanto|garantimos|prometo|vou reservar|vou transferir|vou cancelar)\b")
MOEDA = re.compile(r"R\$|\breais?\b|\bcentavos?\b|%")
# Rótulos do prompt (chaves do JSON de entrada e campos da saída) que o modelo às vezes devolve como texto.
ECO_DE_ROTULO = re.compile(
    r"\b(texto[ _]da[ _]loja|mensagem[ _]do[ _]cliente)\b|(?:^|\n)\s*(?:abertura|fechamento)\s*[:=-]|[{}]", re.I)
# Oferta genérica de ajuda: não diz nada que o bloco factual já não diga, e a Lia não fecha com fórmula pronta.
OFERTA_GENERICA = re.compile(
    r"\b(qualquer duvida|fique a vontade|estou (aqui|por aqui|a disposicao)|estamos a disposicao|"
    r"caso (precise|queira|tenha)|se (precisar|tiver|houver)|conte comigo|conte com a gente|"
    r"posso ajudar (em )?(mais|algo|alguma)|mais alguma coisa|mais alguma duvida|precisando|sempre que (precisar|quiser)|"
    r"para o que precisar|no que precisar|foi um prazer)\b")
# Afirmação ou oferta sobre a loja (falha a): só passa se tudo o que a frase diz já está no bloco factual.
AFIRMACAO_SOBRE_A_LOJA = re.compile(
    r"\b(temos|oferecemos|trabalhamos|aceitamos|fazemos|possuimos|dispomos|vendemos|entregamos|parcelamos|"
    r"disponivel|disponiveis|garantimos|atende|atendemos|verificar|conferir|checar|analisar|consultar|"
    r"vamos (ver|olhar)|condicao de credito|aprovacao)\b")
CAIXA_ALTA = re.compile(r"\b[A-ZÀ-Ý]{2,}\b")  # trecho em caixa alta: eco de "DAN ATIVO", sigla inventada
LIMIAR_REPETE_BLOCO = 0.8
LIMIAR_COBERTURA = 0.75  # parte das palavras de conteúdo da frase que já estão numa frase do bloco
# "null" em texto (o modelo às vezes devolve a palavra no lugar do JSON null) nunca chega ao cliente.
NULO_LITERAL = re.compile(r"\b(null|none|undefined|nan)\b")
NULOS = {"null", "none", "undefined", "nan", "nil"}
NEGACAO = {"nao", "nunca", "jamais", "nenhum", "nenhuma", "sem", "impossivel", "ninguem"}
PALAVRAS_VAZIAS = {"a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "nos", "nas",
                   "para", "pra", "por", "com", "que", "se", "eu", "voce", "te", "me", "ao", "aos", "ou", "mas", "ja",
                   "esse", "essa", "isso", "este", "esta", "isto", "ser", "sao", "foi", "esta", "estao", "tem", "ter",
                   "mais", "muito", "so", "aqui", "la", "como", "qual", "quais", "seu", "sua", "meu", "minha"}
# Pares que se excluem: se o bloco diz um lado, a frase do modelo não pode dizer o outro.
ANTONIMOS = (
    ({"disponivel", "disponiveis"}, {"esgotado", "esgotada", "indisponivel", "descontinuado", "descontinuada"}),
    ({"gratis", "gratuito", "gratuita"}, {"cobrado", "cobrada", "pago", "paga"}),
    ({"aberta", "aberto"}, {"fechada", "fechado"}),
)
# Saudação solta: a frase inteira é só "Olá", "Oi" e afins. A abertura da conversa é da persona, não da redação.
SAUDACOES = {"ola", "oi", "opa", "alo", "eai", "ei", "hey", "salve"}
# Palavras comuns que só existem com acento: sem ele, o texto saiu sem revisão de português. Lista curta e de palavras
# que nunca têm outra leitura sem acento ("esta", "pais", "e" ficam de fora de propósito).
SEM_ACENTO = {
    "voce": "você", "voces": "vocês", "nao": "não", "tambem": "também", "entao": "então", "ate": "até", "ja": "já",
    "ola": "olá", "preco": "preço", "precos": "preços", "opcao": "opção", "opcoes": "opções",
    "informacao": "informação", "informacoes": "informações", "duvida": "dúvida", "duvidas": "dúvidas",
    "horario": "horário", "horarios": "horários", "possivel": "possível", "disponivel": "disponível",
    "disponiveis": "disponíveis", "facil": "fácil", "util": "útil", "orcamento": "orçamento", "pagina": "página",
    "atencao": "atenção", "condicao": "condição", "condicoes": "condições", "promocao": "promoção",
    "promocoes": "promoções", "violao": "violão", "violoes": "violões", "musica": "música", "endereco": "endereço",
    "credito": "crédito", "debito": "débito", "codigo": "código", "numero": "número", "sao": "são", "estao": "estão",
    "alem": "além", "porem": "porém", "ninguem": "ninguém", "apos": "após", "atraves": "através",
}
# Formas verbais comuns (irregulares e de uso corrente na redação) e radicais de verbos que a Lia usa.
FORMAS_VERBAIS = {
    "é", "são", "foi", "era", "será", "seria", "está", "estão", "estou", "estamos", "estava", "tem", "têm", "tenho",
    "temos", "tinha", "vou", "vai", "vamos", "vão", "posso", "pode", "podem", "podemos", "pôde", "quer", "quero",
    "queremos", "queria", "fico", "fica", "ficou", "faço", "faz", "fazemos", "fez", "dá", "dou", "damos", "sei", "sabe",
    "sabemos", "vejo", "vê", "veja", "vem", "venho", "vêm", "deixa", "deixo", "segue", "sigo", "diga", "fale", "conte",
    "peça", "pergunte", "confira", "aproveite", "escreva", "olhe", "espere", "há", "houve", "existe", "cabe", "serve",
    "vale", "parece", "precisa", "preciso", "fique", "seja", "sejam", "saiba", "traga", "mande", "use", "tente", "diz",
    "digo", "falo", "conto", "peço", "pergunto", "entendo", "entende", "combinado"}
RADICAIS_VERBAIS = ("ajud", "mostr", "explic", "olh", "confer", "compar", "busc", "procur", "separ", "indic", "pergunt",
                    "respond", "encontr", "resolv", "entend", "confirm", "pass", "segu", "comec", "cont", "fal", "recomend",
                    "sugir", "sugere", "lembr", "avis", "mand", "envi", "ach", "cheg", "precis", "gost", "prefer")
FINAIS_VERBAIS = ("o", "a", "e", "ar", "er", "ir", "ei", "ou", "amos", "emos", "imos", "am", "em", "ando", "endo", "indo",
                  "aria", "ariam", "arei", "erei", "irei", "ava", "avam", "ado", "ido")
NAO_E_VERBO = {"qualquer", "prazer", "mulher", "lugar", "militar", "particular", "popular", "similar", "regular",
               "singular", "exemplar", "colher", "comum", "mesmo", "mesma"}
MAX_FRASES = 2
MAX_PERGUNTAS = 1
MAX_CARACTERES = 220


def sistema() -> str:
    """Instruções de cada turno redigido: a persona primeiro, depois as regras da redação."""
    return f"{persona.instrucoes()} {SISTEMA}"


def _frases(texto: str) -> list[str]:
    return [f for f in re.split(r"(?<=[.!?])\s+", texto.strip()) if f]


def _conteudo(texto: str) -> set[str]:
    return {t for t in tokens(texto) if t not in PALAVRAS_VAZIAS and t not in NEGACAO}


def _partes_do_bloco(bloco: str) -> list[str]:
    return [parte for linha in bloco.splitlines() for parte in _frases(linha) if normalizar(parte)]


def repete_o_bloco(frase: str, bloco: str) -> bool:
    """Frase do modelo que só repete, com outras palavras ou por inteiro, o que o bloco factual já diz."""
    n = normalizar(frase)
    palavras = len(n.split())
    conteudo = _conteudo(frase)
    for parte in _partes_do_bloco(bloco):
        b = normalizar(parte)
        if palavras >= 3 and (n in b or (len(b.split()) >= 3 and b in n)):
            return True
        if SequenceMatcher(None, n, b).ratio() >= LIMIAR_REPETE_BLOCO:
            return True
        # mesma informação com outras palavras: quase tudo o que a frase diz já está numa frase do bloco
        if len(conteudo) >= 3 and len(conteudo & _conteudo(parte)) / len(conteudo) >= LIMIAR_COBERTURA:
            return True
    return False


def contradiz_o_bloco(frase: str, bloco: str) -> bool:
    """Frase do modelo que diz o oposto do bloco factual: antônimo do dado ou a mesma afirmação com polaridade
    trocada ("o frete não é grátis" contra "o frete é grátis"). Heurística conservadora: exige palavras em comum."""
    nt = set(tokens(frase))
    for parte in _partes_do_bloco(bloco):
        bt = set(tokens(parte))
        for lado_a, lado_b in ANTONIMOS:
            if (nt & lado_a and bt & lado_b) or (nt & lado_b and bt & lado_a):
                return True
        comuns = _conteudo(frase) & _conteudo(parte)
        if len(comuns) >= 2 and bool(nt & NEGACAO) != bool(bt & NEGACAO):
            return True
    return False


def tem_verbo(frase: str) -> bool:
    """Heurística de verbo em português: forma verbal comum, radical de verbo da Lia com terminação verbal, ou infinitivo.
    Conservadora no sentido de descartar na dúvida: a redação é opcional, e o bloco factual sempre responde."""
    for t in re.findall(r"[a-zà-ÿ]+", frase.lower()):
        if t in NAO_E_VERBO:
            continue
        if t in FORMAS_VERBAIS:
            return True
        n = normalizar(t)
        if len(n) >= 5 and re.search(r"(ar|er|ir)$", n):
            return True  # infinitivo
        if any(n.startswith(r) and n[len(r):] in FINAIS_VERBAIS for r in RADICAIS_VERBAIS):
            return True
    return False


def _saudacao_solta(frase: str) -> bool:
    palavras = tokens(frase)
    return bool(palavras) and all(p in SAUDACOES for p in palavras)


def _campo_livre(valor: Any) -> str:
    """Texto do campo do modelo; a palavra "null" no lugar do JSON null conta como campo vazio."""
    texto = (valor or "").strip() if isinstance(valor, (str, type(None))) else ""
    return "" if normalizar(texto).strip(" .\"'`") in NULOS else texto


def afirma_o_que_o_bloco_nao_diz(frase: str, bloco: str) -> bool:
    """Frase com verbo de afirmação ou oferta sobre a loja cujo conteúdo não está inteiro no bloco factual."""
    if not AFIRMACAO_SOBRE_A_LOJA.search(normalizar(frase)):
        return False
    return not _conteudo(frase) <= set(tokens(bloco))


def validar(livre: str, bloco: str, estado: Estado, mensagem: str = "") -> str | None:
    """Devolve o motivo da reprovação, ou None se o texto livre pode ser exibido."""
    norm = normalizar(livre)
    if ECO_DE_ROTULO.search(normalizar(livre)) or ECO_DE_ROTULO.search(livre):
        return "eco_de_rotulo"
    if NULO_LITERAL.search(norm):
        return "null_literal"
    if re.search(r"\d", livre):
        return "digito"
    if MOEDA.search(livre):
        return "moeda"
    if VERBOS_NAO_CONFIRMADOS.search(norm):
        return "verbo_de_acao"
    if len(livre) > MAX_CARACTERES:
        return "longo"
    if any(_saudacao_solta(f) for f in _frases(livre)):
        return "saudacao_solta"
    if any(p in SEM_ACENTO for p in re.findall(r"[a-zà-ÿ]+", livre.lower())):
        return "sem_acento"
    for frase in _frases(livre):
        primeira = next((c for c in frase if c.isalpha()), "")
        if primeira and primeira.islower():
            return "minuscula"  # frase que começa em minúscula é resto de eco ou de continuação do bloco
    if CAIXA_ALTA.search(livre):
        return "caixa_alta"
    if OFERTA_GENERICA.search(norm):
        return "oferta_generica"
    if len(_frases(livre)) > MAX_FRASES:
        return "frases"
    if any(contradiz_o_bloco(f, bloco) for f in _frases(livre)):
        return "contradiz_bloco"
    if any(afirma_o_que_o_bloco_nao_diz(f, bloco) for f in _frases(livre)):
        return "afirmacao_fora_do_bloco"
    if livre.count("?") + bloco.count("?") > MAX_PERGUNTAS:
        return "perguntas"
    if estado.ja_saudou and tem_saudacao(livre):
        return "saudacao_repetida"
    voc = catalogo.vocabulario()
    do_bloco = set(tokens(bloco))
    for t in tokens(livre):
        identifica = t in voc.df and (voc.df[t] <= 4 or re.search(r"\d", t)) and t not in v.PALAVRAS_SOLTAS
        if identifica and t not in do_bloco:
            return "produto_fora_do_bloco"
    # eco de termo do cliente que não está no bloco nem no vocabulário da loja ("DAN ATIVO"): na dúvida, descartar
    da_mensagem = set(tokens(mensagem))
    for t in tokens(livre):
        if len(t) >= 3 and t in da_mensagem and t not in do_bloco and t not in voc.df and t not in PALAVRAS_VAZIAS:
            return "eco_da_mensagem"
    return None


class Redator:
    def __init__(self, modelo: str, cliente: Any = None) -> None:
        self.modelo = modelo
        self.cliente = cliente or llm
        self.telemetria: list[dict[str, Any]] = []
        self.contagens: dict[str, int] = {}

    def _contar(self, chave: str) -> None:
        self.contagens[chave] = self.contagens.get(chave, 0) + 1

    def envolver(self, estado: Estado, mensagem: str, bloco: str, permitir_fechamento: bool,
                 anteriores: list[str] | None = None) -> str:
        reg: dict[str, Any] = {"componente": "redacao", "modelo": self.modelo}
        entrada = json.dumps({"mensagem_do_cliente": mensagem[:300], "texto_da_loja": bloco}, ensure_ascii=False)
        self._contar("redacao_tentada")  # denominador dos descartes: só turno com chamada ao modelo
        try:
            r = self.cliente.conversar(self.modelo, llm.mensagens_do_modelo(self.modelo, sistema(), entrada),
                                       formato=SCHEMA, maximo_tokens=120)
        except llm.TimeoutModelo as erro:
            self._contar("timeout")
            reg.update(resultado="bloco_apenas:timeout", detalhe=str(erro))
            self.telemetria.append(reg)
            return bloco
        except llm.ErroModelo as erro:
            self._contar("erro_modelo")
            reg.update(resultado="bloco_apenas:erro_modelo", detalhe=str(erro))
            self.telemetria.append(reg)
            return bloco
        reg.update(texto_bruto=r.conteudo, tokens_prompt=r.tokens_prompt, tokens_resposta=r.tokens_resposta,
                   latencia_ms=r.latencia_ms, num_ctx=getattr(r, "num_ctx", None))
        try:
            dados = json.loads(r.conteudo)
            abertura = _campo_livre(dados.get("abertura"))
            fechamento = _campo_livre(dados.get("fechamento")) if permitir_fechamento else ""
            if not isinstance(dados.get("abertura"), (str, type(None))) or not isinstance(dados.get("fechamento"), (str, type(None))):
                raise ValueError("campos com tipo errado")
        except (ValueError, AttributeError):
            self._contar("redacao_descartada")
            reg.update(resultado="descartada:formato")
            self.telemetria.append(reg)
            return bloco
        # contradição vem antes da repetição: "o frete não é grátis" parece cópia do bloco, mas diz o oposto
        if any(contradiz_o_bloco(f, bloco) for f in _frases(f"{abertura} {fechamento}")):
            self._contar("redacao_descartada")
            reg.update(resultado="descartada:contradiz_bloco")
            self.telemetria.append(reg)
            return bloco
        # frase do modelo que repete o bloco sai; o bloco nunca é alterado
        abertura = " ".join(f for f in _frases(abertura) if not repete_o_bloco(f, bloco))
        fechamento = " ".join(f for f in _frases(fechamento) if not repete_o_bloco(f, bloco))
        if anteriores:  # frase livre já dita antes não se repete (o bloco factual nunca passa por aqui)
            abertura, _ = deduplicar_frases(abertura, anteriores)
            fechamento, _ = deduplicar_frases(fechamento, anteriores)
        livre = " ".join(x for x in (abertura, fechamento) if x)
        if not livre:
            reg.update(resultado="vazia")
            self.telemetria.append(reg)
            return bloco
        motivo = validar(livre, bloco, estado, mensagem)
        if motivo:
            self._contar("redacao_descartada")
            reg.update(resultado=f"descartada:{motivo}")
            self.telemetria.append(reg)
            return bloco
        reg["resultado"] = "aceita"
        self._contar("redacao_exibida")
        self.telemetria.append(reg)
        partes = [abertura, bloco, fechamento]
        return "\n".join(p for p in partes if p)

    def drenar(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        t, c = self.telemetria, self.contagens
        self.telemetria, self.contagens = [], {}
        return t, c
