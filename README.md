# Agente da Empório da Música

Lia é a assistente virtual da Empório da Música, loja fictícia de instrumentos em Campo Grande/MS. Ela responde sobre catálogo, preços, formas de pagamento, frete, status de pedidos e políticas da loja, leva a compra até o carrinho, registra reclamações e encaminha para um atendente. Junto vem um site da loja (catálogo, produto, carrinho, checkout, rastreio, políticas) com a Lia em todas as páginas, instalável como PWA.

Aviso do repositório: a loja é fictícia e os pedidos não são reais. Nenhum valor é cobrado e nada é entregue. O site não diz isso ao cliente, por decisão de produto. Os links de WhatsApp, telefone e e-mail são gerados dos dados do manual da loja fictícia e não são contatos reais (`EMPORIO_WHATSAPP_URL`, `EMPORIO_TELEFONE_LINK` e `EMPORIO_EMAIL_LINK` substituem). O Fale Conosco só envia e-mail com `EMPORIO_SMTP_HOST` e `EMPORIO_SMTP_PARA`. Fotos e retrato da Lia: ver `docs/CREDITOS_IMAGENS.md`.

## Como a Lia funciona

1. **Percepção por regras:** o código identifica a intenção e os dados da mensagem (produto, pedido, CEP, parcelas, sentimento) e mantém o estado da conversa.
2. **Ferramentas determinísticas:** consultam o SQLite carregado dos CSV e o manual transcrito em YAML (`src/emporio/politicas/manual_v2_1.yaml`): buscar produtos, ver produto, calcular condições, estimar frete, consultar pedido, consultar política, registrar encaminhamento.
3. **Resposta escrita pelo código:** preço, prazo, regra, protocolo e link saem sempre do resultado das ferramentas.
4. **Redação pelo modelo, opcional e limitada:** um modelo local (`qwen3:4b`) pode acrescentar até 2 frases curtas, sem números. Um validador descarta qualquer frase com fato fora do bloco factual, eco da mensagem do cliente, caixa alta ou oferta não apoiada nos dados, e não há redação em recusas, pedidos, pós-venda e compra. Na dúvida, descarta.

O modelo nunca decide ações nem escreve fatos. Isso foi uma decisão medida, explicada abaixo.

## Executar com Docker

```
docker compose up -d --build
```

Site em http://localhost:8000 e estado em http://localhost:8000/saude. O modelo `qwen3:4b` (cerca de 2,5 GB) é baixado na primeira subida; enquanto isso, a Lia responde só com as regras. Com GPU NVIDIA: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`. Parar: `docker compose down`.

O Docker sobe com `EMPORIO_REDACAO=1` (redação ligada) e `EMPORIO_RESERVA=0` (reserva desligada, ver resultados). `EMPORIO_REDACAO=0` desliga a redação.

## Executar sem Docker

Requer Python 3.11 ou superior.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set PYTHONPATH=src
.venv\Scripts\python -m emporio.dados.carga
.venv\Scripts\python -m uvicorn emporio.web.app:app --port 8000
```

No Linux ou macOS, use `.venv/bin/` e `export PYTHONPATH=src`. Sem modelo, a Lia funciona só com as regras. Para a redação local: instale o [Ollama](https://ollama.com), rode `ollama pull qwen3:4b` e defina `EMPORIO_MODELO=qwen3:4b`, `EMPORIO_DECISOR=regras`, `EMPORIO_REDACAO=1` e `EMPORIO_RESERVA=0`. Fora do Docker o padrão do código é redação desligada.

Conversa pelo terminal: `.venv\Scripts\python -m emporio.cli --origem demo`. O PWA só instala em `localhost` ou HTTPS. `EMPORIO_DATA_REFERENCIA=2026-03-25T10:00:00` fixa a data da loja, útil porque os pedidos dos dados são de 2025 e 2026.

## Trocar de modelo

A Lia está pronta para outro provedor, inclusive pago por API, sem mudar a arquitetura: decisão, ferramentas e redação são separadas.

| Variável | Efeito |
|---|---|
| `EMPORIO_PROVEDOR` | `ollama` (padrão) ou `anthropic` |
| `EMPORIO_MODELO` | modelo do provedor; no `anthropic` o padrão é `claude-haiku-5-5` |
| `ANTHROPIC_API_KEY` | chave lida pelo SDK (ou perfil do `ant auth login`); nunca vai para o código |
| `EMPORIO_LLM_TIMEOUT` | segundos por chamada |

```
.venv\Scripts\pip install -r requirements-api.txt
set ANTHROPIC_API_KEY=...
set EMPORIO_PROVEDOR=anthropic
set EMPORIO_DECISOR=regras
set EMPORIO_REDACAO=1
.venv\Scripts\python -m uvicorn emporio.web.app:app
```

Se a API falhar ou o provedor estiver mal configurado, a Lia segue só com as regras. Outro provedor é uma implementação nova em `src/emporio/agente/provedores.py`.

**Nenhum modelo por API foi medido neste projeto.** A troca deve passar pelo mesmo harness e critério (`eval/rodar.py`, `eval/PREREGISTRO.md`) antes de virar padrão.

### Modelos recomendados e custo estimado

| Modelo | Entrada / saída por 1M tokens (US$) | Papel indicado |
|---|---|---|
| Claude Haiku 5.5 (`claude-haiku-5-5`) | 0,10 / 0,50 | Primeira opção: redação e, a medir, classificação de intenção |
| Gemini 2.5 Flash-Lite | 0,10 / 0,40 | Alternativa de mesmo custo (não implementada) |
| GPT-5.4 nano | 0,20 / 1,25 | Alternativa (não implementada) |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | 2,00 / 10,00 | Se for preciso o modelo decidir ações |

Preços: tabela da Anthropic de outubro de 2026; Gemini e GPT vêm de agregadores de preço, não das páginas oficiais, e devem ser conferidos.

Estimativa, com premissas declaradas: uma chamada de redação mediu cerca de 360 tokens de entrada; supus 40 de saída para um modelo por API, 5 mensagens por conversa e uma chamada por mensagem. Não encontrei média confiável de conversas para lojas do segmento; uma referência de mercado sem data clara fala em cerca de 1.400 pessoas por mês por bot no Brasil.

| Volume | Conversas/mês | Redação com Haiku 5.5 | Modelo classificando intenção (~1.500 tokens) |
|---|---|---|---|
| Loja pequena | 1.000 | cerca de US$ 0,30 | cerca de US$ 1 |
| Referência de mercado | 1.400 | cerca de US$ 0,40 | cerca de US$ 1,40 |
| Volume alto | 20.000 | cerca de US$ 6 | cerca de US$ 18 |

O custo é desprezível para esta loja. O que decide é a qualidade, e ela não foi medida com modelos por API.

## Testes e avaliação

```
python -m pytest
pip install -r requirements-e2e.txt && playwright install chromium
python -m pytest -m e2e
python eval/rodar.py --conjunto dev --rotulo meu_teste
python eval/comparar.py eval/resultados/dev_a.json eval/resultados/dev_b.json
```

Na versão entregue: 1.248 testes unitários e 194 de navegador (Playwright, inclusive celular emulado).

Conjuntos: `casos_dev.jsonl` (62), `casos_variacoes.jsonl` (14) e `casos_conversas.jsonl` (70, achados de revisão e QA) são de desenvolvimento; `casos_frescos.jsonl` (18) foi escrito antes das correções para medir às cegas; `casos_holdout.jsonl` (20) roda uma vez, com hash conferido. Critérios em `eval/PREREGISTRO.md` e `eval/PREREGISTRO_RESERVA.md`; toda correção de instrumento ou gabarito está em `eval/CORRECOES.md`.

## Decisões técnicas

| Decisão | Por que | Por que não a alternativa |
|---|---|---|
| Ferramentas determinísticas com dados estruturados, sem RAG | Preço, estoque e pedido exigem valor exato | Busca por semelhança traria o produto parecido em vez do certo |
| Regras decidem; modelo só redige | Medido: modelos locais decidindo erraram mais fatos que as regras (tabela abaixo) | Deixar o modelo decidir com hardware sem GPU piorou conclusão e fatos |
| Modelo local `qwen3:4b` para redação | Escolhido pelo critério pré-registrado entre `qwen2.5:3b` e `qwen3:4b`: mesmos fatos, mais frases exibidas, menos descartes, mais rápido, licença Apache 2.0 | Modelos de 8B passam de 4 GB e já mediram pior; modelos por API não foram medidos |
| Validador de redação estrito | O modelo inventou "estacionamento", ecoou um ataque e criou "verificação de crédito" | Confiar no prompt não garante a saída |
| Reserva de intenção desligada | Não passou na barra pré-registrada (ver resultados) | Ligar sem evidência contrariaria o critério |
| FastAPI, Jinja2 e HTMX, sem build de front-end, PWA | Simples de rodar e de auditar; site e Lia usam as mesmas ferramentas | SPA exigiria build e segunda fonte de dados |
| SQLite e trace JSONL sem texto do cliente | Estado da conversa, chamados e tentativas; observabilidade sem dado pessoal | Banco externo seria peso sem ganho no protótipo |
| CSV originais intactos | Inconsistências aparecem como gravadas e cobertas por teste | Corrigir em silêncio esconderia o problema do dado |

### Por que este caminho e o que faríamos com mais recursos

Rodamos tudo em uma máquina com 16 GB de RAM e sem GPU dedicada, com site, testes e modelo ao mesmo tempo. Nessas condições, modelos que cabem localmente (3B a 8B) não decidem bem: medimos quatro deles decidindo as ações e todos ficaram abaixo das regras. Por isso o código decide e o modelo só redige. Escolhemos também rodar local, sem chave e sem custo; um modelo grande por API decidindo a intenção é o candidato mais provável a melhorar a compreensão de frases livres, mas não foi testado, então é hipótese. O próximo passo seria medir `claude-haiku-5-5` e depois `claude-sonnet-5-5` na intenção, no mesmo harness e critério.

## Resultados

### Comparação de modelos decidindo as ações (dev, 62 casos, `num_ctx` 8192, commit 41b8a9f)

| Configuração | Conclusão | Fatos críticos errados |
|---|---|---|
| Regras decidem (controle) | 49/62 | 4/31 |
| `qwen3:4b` decide | 40/62 | 11/31 |
| `qwen2.5:3b` decide | 39/62 | 10/31 |
| `qwen3:8b` decide | 39/62 | 13/31 |
| `llama3.1:8b` decide | 38/62 | 10/31 |

Um segundo experimento, com o modelo classificando a intenção antes das regras, deu 47/62 e 5/31 contra 62/62 e 0/31 das regras no mesmo commit, de 5 a 9 vezes mais lento. Foi descartado.

### Medição congelada (commit 735bb85, `qwen3:4b`, decisor de regras)

| Conjunto | Só regras | Regras e redação (entregue) | Com reserva |
|---|---|---|---|
| dev (62) | 62/62, 0/31 | 62/62, 0/31 | 62/62, 0/31 |
| variações (14) | 14/14, 0/12 | 14/14, 0/12 | 14/14, 0/12 |
| conversas (70) | 70/70, 0/3 | 70/70, 0/3 | 70/70, 0/3 |
| frescos, às cegas (18) | 16/18, 0/1 | 16/18, 0/1 | 17/18, 0/1 |

Formato: conclusão, fatos críticos errados. Zero chamados indevidos e zero falhas técnicas em todas. Dev, variações e conversas foram usados para ajuste, então medem regressão, não qualidade. Redação no dev: 55 tentadas, 4 exibidas, 3 descartadas; nas conversas: 83, 4 e 0. A redação aparece pouco.

A reserva não passou: a barra pedia pelo menos 2 casos de "não entendi" a menos nos frescos, e ela teve 1. Fica desligada.

Depois de ver os frescos, corrigi um defeito real (f02, "isso aqui é uma pessoa de verdade?", abria chamado) antes do holdout. A partir daí os frescos passam a ser de desenvolvimento: os números acima são da versão anterior à correção e não avaliam de forma independente a versão corrigida.

### Holdout, execução única (commit e0f35d6)

| Critério pré-registrado | Barra | Entregue | Só regras |
|---|---|---|---|
| Conclusão | ≥ 80% | 18/20 (90%) | 18/20 |
| Fatos críticos errados | 0 | **1/10, reprovado** | 1/10 |
| Escolha de ações | ≥ 85% | 20/20 | 20/20 |
| Bloqueios indevidos | ≤ 10% | 1/20 | 1/20 |
| Pedido de atendente | todos | 1/1 | 1/1 |

A versão e0f35d6 concluiu 18 de 20 casos, mas reprovou na exigência de zero erros factuais críticos. Mantivemos a versão congelada e documentamos as falhas:

- **h12, contado como fato crítico** (categoria cruzada): "paguei com cartão, o reembolso da devolução cai como?". O gabarito exigia "mesma forma", porque o manual diz que o reembolso é feito na mesma forma de pagamento original em até 10 dias úteis. A Lia respondeu só a regra de arrependimento e pediu o pedido, sem dizer como o reembolso cai. É omissão da informação pedida, não uma afirmação falsa.
- **h06**, que reduz a conclusão mas não está nas categorias de fato crítico: "ainda dá pra comprar o Baixo Ibanez 2X?". O gabarito exigia "descontinuado"; a Lia respondeu que não encontrou produtos disponíveis.

Comparação caso a caso entre só regras e entregue: nenhum caso melhorou ou piorou; o texto final mudou em 1 de 20 (h20), sem mudar o resultado. O mesmo 18/20 indica igualdade no agregado, confirmada caso a caso.

O registro do holdout marca `arvore_alterada: true`. O marcador veio de um arquivo de imagem não rastreado, sem uso, em `src/emporio/web/static/` (o retrato original da Lia, depois removido). `git diff e0f35d6` em `src/` e `eval/rodar.py` não mostra mudança de código.

### Versão avaliada e verificação da entrega

- Código avaliado no holdout: **e0f35d6**. Documentação final: **38b8370** e posteriores. `git diff e0f35d6 38b8370` altera só `README.md`, `exemplos/*.md` e `eval/resultados/*.json`: nenhuma linha de `src/`, `tests/`, `docker-compose.yml` ou `requirements*.txt`, então o comportamento avaliado é o entregue.
- Instalação limpa sem Docker, a partir de um clone do GitHub em 38b8370 e seguindo só este README: site e `/saude` no ar, Lia respondendo só com regras, 1.248 testes passando (01/11/2026, 20h13).
- Instalação limpa com Docker, mesmo clone, `docker compose up -d --build`: a Lia respondeu só com regras durante o download do modelo, e com `qwen3:4b` e redação depois dele, cerca de 4 minutos (01/11/2026, 20h21).

## Exemplos de conversa

Cinco conversas em [`exemplos/`](exemplos), geradas pelo agente com `python exemplos/gerar_conversas.py` na configuração entregue (`qwen3:4b`, redação ligada): catálogo com orçamento e sugestão, informações da loja e fora do escopo, preço com nome ambíguo, promoção e parcela em conferência, devolução com consulta ao pedido e às políticas, e reclamação com chamado. Na conversa 05 a redação abriu a resposta com "Ola", sem acento, em linha solta: o validador deixou passar. Não corrigi para não alterar a versão avaliada.

## Suposições documentadas

- Frete grátis em Campo Grande a partir de R$ 500,00, inclusive, apurado sobre o preço com promoção e antes do desconto do PIX. O manual diz "acima de" e "abaixo de" sem definir o valor exato.
- "Em Campo Grande" vale só para a cidade; o manual cita região metropolitana sem listar municípios.
- Frete fora de Campo Grande é uma estimativa simulada (tabela por zona a partir de MS e caixas estimadas por categoria), não tarifa dos Correios; grande porte fica em cotação individual.
- Contatos: telefone e e-mail da capa do manual e WhatsApp da seção 7; as divergências do manual aparecem em Políticas.
- Parcela mínima com duas leituras no manual: a Lia mostra as duas e oferece encaminhar.
- A Lia não usa o nome do cliente nem mostra endereço de entrega, por privacidade.
- Retirada na loja não existe no manual e não foi criada.

## Limitações conhecidas

- A compreensão de frases livres é limitada às regras e ao vocabulário. Num QA com 35 conversas novas, só 30% dos turnos estavam corretos antes das últimas correções; não medimos de novo com frases inéditas depois delas.
- Holdout reprovado em fatos críticos (h12) e com um produto descontinuado não identificado (h06).
- A redação raramente aparece e já deixou passar "Ola" sem acento.
- Pedir atendente registra o chamado na hora, sem oferecer antes WhatsApp e telefone.
- Não entende pelo chat: tirar item do carrinho, "tele" para Telecaster, diferença de preço depois de uma comparação.
- Horário escrito pela Lia em "09:00", e o site em "9h".
- Sete produtos têm marca no nome diferente da descrição nos dados originais; os CSV não foram alterados.
- Celular e PWA testados só em Chromium emulado, sem aparelho real nem Safari.
- Produção: faltam cabeçalhos de segurança, segredo de sessão obrigatório e proteção ao cabeçalho Host; `/saude` mostra o nome do modelo; o limite de tentativas de rastreio fica em memória.
- Sem compra real nem pagamento; identificação do cliente simulada.

## Uso de assistentes de código

Usei o Claude Code com papéis separados. Um modelo mais forte (Claude Opus) explorou os dados, escreveu a especificação (`docs/SPEC.md`), pré-registrou os critérios, revisou e integrou cada entrega. Modelos mais econômicos (Claude Sonnet) implementaram cada etapa a partir da especificação aprovada, com área de arquivos delimitada e proibição de ler os conjuntos às cegas. Agentes separados fizeram auditorias somente leitura: QA de cliques, QA de conversas, QA de celular e PWA, auditoria de segurança e conformidade com o manual; os achados viraram etapas da especificação. Eu aprovei a especificação e as mudanças de testes existentes; na reta final autorizei um modo automático em que as decisões que dependiam de mim ficaram registradas para o fim. Entregas foram reprovadas e refeitas, um experimento (modelo classificando a intenção) foi medido e descartado, e os erros de medição foram declarados em `eval/CORRECOES.md`.
