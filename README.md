# Agente da Empório da Música

Lia é a assistente virtual da Empório da Música, loja fictícia de instrumentos em Campo Grande/MS. Ela responde sobre catálogo, preços, formas de pagamento, frete, status de pedidos e políticas da loja, leva a compra até o carrinho, registra reclamações e encaminha para um atendente. Junto vem um site da loja (catálogo, produto, carrinho, checkout, rastreio, políticas) com a Lia em todas as páginas, instalável como PWA.

## Resumo para quem avalia

- **Rodar:** `docker compose up -d --build` e abrir http://localhost:8000 (detalhes em [Executar com Docker](#executar-com-docker)).
- **Arquitetura:** o código entende a mensagem e busca os fatos com ferramentas determinísticas (dados dos CSV e manual da loja). Preço, pedido, prazo e regra nunca saem da cabeça do modelo.
- **Pronta para modelo por API:** `EMPORIO_PROVEDOR=anthropic` liga o Claude (Haiku 5.5 por padrão) na redação e, sem `EMPORIO_DECISOR=regras`, também na decisão das ações, sem mudar a arquitetura. Se a API falhar ou estiver mal configurada, a Lia segue com as regras. Outro provedor é uma classe nova em `provedores.py`. Custo estimado: de centavos a poucos dólares por mês nesta loja ([Trocar de modelo](#trocar-de-modelo)). A integração tem testes com o SDK simulado; a qualidade com a API real não foi medida.
- **Por que a entrega roda com regras:** sem GPU e com pouca memória, só modelos locais pequenos cabiam. Medidos no mesmo harness, eles erravam a escolha das ações, então a decisão ficou com as regras e o modelo local só pode acrescentar até 2 frases, sob um validador estrito.
- **Resultado medido:** no teste às cegas, executado uma vez (holdout 2), a Lia acertou 30 de 40 conversas e errou 5 de 22 fatos críticos, abaixo da barra pré-registrada. Os erros estão listados em [Resultados](#resultados). Frases novas são o ponto fraco das regras, e é aí que um modelo por API deve ajudar; essa hipótese ainda não foi testada.
- **Próximo passo:** rodar o Haiku nos mesmos conjuntos e critérios (`eval/rodar.py`, `eval/PREREGISTRO.md`), comparar com as regras e só então trocar o padrão.

Aviso do repositório: a loja é fictícia e os pedidos não são reais. Nenhum valor é cobrado e nada é entregue. O site não diz isso ao cliente, por decisão de produto. Os links de WhatsApp, telefone e e-mail são gerados dos dados do manual da loja fictícia e não são contatos reais (`EMPORIO_WHATSAPP_URL`, `EMPORIO_TELEFONE_LINK` e `EMPORIO_EMAIL_LINK` substituem). O Fale Conosco só envia e-mail com `EMPORIO_SMTP_HOST` e `EMPORIO_SMTP_PARA`. Fotos e retrato da Lia: ver `docs/CREDITOS_IMAGENS.md`.

## Como a Lia funciona

1. **Percepção por regras:** o código identifica a intenção e os dados da mensagem (produto, pedido, CEP, parcelas, sentimento) e mantém o estado da conversa.
2. **Ferramentas determinísticas:** consultam o SQLite carregado dos CSV e o manual transcrito em YAML (`src/emporio/politicas/manual_v2_1.yaml`): buscar produtos, ver produto, calcular condições, estimar frete, consultar pedido, consultar política, registrar encaminhamento.
3. **Resposta escrita pelo código:** preço, prazo, regra, protocolo e link saem sempre do resultado das ferramentas.
4. **Redação pelo modelo, opcional e limitada:** um modelo local (`qwen3:4b`) pode acrescentar até 2 frases curtas, sem números. Um validador descarta qualquer frase com fato fora do bloco factual, eco da mensagem do cliente, caixa alta ou oferta não apoiada nos dados, e não há redação em recusas, pedidos, pós-venda e compra. Na dúvida, descarta.

Na configuração entregue, o modelo nunca decide ações nem escreve fatos. Isso foi uma decisão medida, explicada abaixo; com um modelo por API, a decisão das ações pode ser ligada (ver [Trocar de modelo](#trocar-de-modelo)), e os fatos continuam vindo das ferramentas.

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

A Lia está pronta para outro provedor, inclusive pago por API, sem mudar a arquitetura: decisão, ferramentas e redação são separadas. Com `EMPORIO_DECISOR=regras` o modelo só redige; sem essa variável, o modelo do provedor também decide as ações, e as ferramentas continuam escrevendo os fatos.

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

Na versão entregue: 1.515 testes unitários e 210 de navegador (Playwright, inclusive celular emulado).

Conjuntos: `casos_dev.jsonl` (62), `casos_variacoes.jsonl` (14) e `casos_conversas.jsonl` (108, achados de revisão e QA) são de desenvolvimento; `casos_frescos.jsonl` (18) foi escrito antes das correções para medir às cegas e depois passou a desenvolvimento; `casos_holdout.jsonl` (20) e `casos_holdout2.jsonl` (40) rodam uma vez cada, com hash conferido. Critérios em `eval/PREREGISTRO.md` e `eval/PREREGISTRO_RESERVA.md`; toda correção de instrumento ou gabarito está em `eval/CORRECOES.md`.

## Decisões técnicas

| Decisão | Por que | Por que não a alternativa |
|---|---|---|
| Ferramentas determinísticas com dados estruturados, sem RAG | Preço, estoque e pedido exigem valor exato | Busca por semelhança traria o produto parecido em vez do certo |
| Regras decidem; modelo só redige | Medido: modelos locais decidindo erraram mais fatos que as regras (tabela abaixo) | Deixar o modelo decidir com hardware sem GPU piorou conclusão e fatos |
| Modelo local `qwen3:4b` para redação | Escolhido pelo critério pré-registrado entre `qwen2.5:3b` e `qwen3:4b`: mesmos fatos, mais frases exibidas, menos descartes, mais rápido, licença Apache 2.0. Na versão final a redação quase não aparece (ver resultados) | Modelos de 8B passam de 4 GB e já mediram pior; modelos por API não foram medidos |
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

### Versão final: holdout 2, execução única (commit fafe24c)

O holdout 2 tem 40 casos escritos por um avaliador independente, sem acesso ao código, antes das últimas correções, com hash publicado em `eval/PREREGISTRO.md`. Quem implementou não leu o arquivo.

| Critério pré-registrado | Barra | Entregue | Só regras |
|---|---|---|---|
| Conclusão | ≥ 80% | **30/40 (75%), reprovado** | 30/40 |
| Fatos críticos errados | 0 | **5/22, reprovado** | 5/22 |
| Escolha de ações | ≥ 85% | 39/40 | 39/40 |
| Bloqueios indevidos | ≤ 10% | 0/40 | 0/40 |
| Pedido de atendente | todos | 2/2 | 2/2 |

A versão fafe24c concluiu 30 de 40 casos e reprovou em conclusão e em fatos críticos. Nada foi ajustado depois da execução. Os dez casos que falharam:

| Caso | Pergunta | O que aconteceu | Natureza |
|---|---|---|---|
| hb18 (crítico) | "meu pedido 1 ja foi entregue? final do cel 1098" | Pediu de novo os 4 dígitos | Identificação não reconhecida ("final do cel") |
| hb21 (crítico) | "pq meu pedido 18 foi cancelado? final 7654" | Deu o motivo, sem a palavra "cancelado" | Omissão parcial; o motivo está certo |
| hb34 (crítico) | "e no pix? e em 12x?" depois do Crafter D-8 | Listou as regras gerais | Pergunta dupla de seguimento sem cálculo |
| hb35 (crítico) | Arrependimento mais frete da devolução | Respondeu o frete, sem os 7 dias | Pergunta dupla respondida pela metade |
| hb36 (crítico) | "pedido 2, final 6543: [...] posso trocar por outra cor?" | "Tive um problema na consulta" | Defeito no fluxo |
| hb04 | "contrabaixo eletrico mais barato" | Leu contrabaixo como cordas orquestrais | Vocabulário |
| hb14 | "martin d28e eletrica" | Não encontrou o produto | Nome parcial |
| hb17 | "aquele shelby de 7 cordas, ainda tem?" | Respondeu a ficha, sem dizer descontinuado | Regressão da pergunta sobre produto |
| hb26 | "qual o horario de segunda a sexta?" | Respondeu "das 9h às 18h" | O gabarito exigia "09:00": formato, não fato. Mantido como falha, sem mudar gabarito depois da execução |
| hb29 | "moro em Corumbá, quais as opções de envio?" | Listou categorias | Intenção errada |

Comparação caso a caso entre só regras e entregue: nenhum caso melhorou ou piorou, e o texto final foi idêntico nos 40 casos. Na versão final, a redação foi tentada 37 vezes, nenhuma exibida e 1 descartada; nas demais tentativas o modelo devolveu vazio. Com o validador reforçado, a redação ligada não alterou nenhuma resposta medida.

Nos conjuntos de desenvolvimento, usados para ajuste e que medem regressão, não qualidade: dev 62/62 e 0/31, variações 14/14 e 0/12, conversas 105/105 e 0/3, com zero chamados indevidos e zero falhas técnicas.

### Compreensão de frases novas (QA independente)

| Rodada | Conversas / turnos | Turnos corretos | Críticos | Altos |
|---|---|---|---|---|
| QA 2 | 35 / 163 | 30,1% | 4 | 60 |
| QA 3 | 35 / 174 | 33,9% | 0 | 53 |
| QA 4 | 35 / 181 | 35,4% | 1 | 57 |

Conversas inéditas, simuladas por agentes independentes como caixa-preta; a classificação é de um único avaliador por rodada, então a comparação é aproximada. Três rodadas de correção renderam cerca de 5 pontos: as regras chegaram ao limite para linguagem natural. O QA 4 mediu a versão anterior às correções finais de risco, e não medimos de novo.

### Holdout original, execução única (commit e0f35d6)

| Critério pré-registrado | Barra | Entregue | Só regras |
|---|---|---|---|
| Conclusão | ≥ 80% | 18/20 (90%) | 18/20 |
| Fatos críticos errados | 0 | **1/10, reprovado** | 1/10 |
| Escolha de ações | ≥ 85% | 20/20 | 20/20 |
| Bloqueios indevidos | ≤ 10% | 1/20 | 1/20 |
| Pedido de atendente | todos | 1/1 | 1/1 |

Aquela versão reprovou por omitir a forma do reembolso (h12); além disso, não identificou um produto descontinuado (h06). O prazo foi estendido depois dessa execução, e o conjunto não rodou de novo. As causas foram corrigidas e a versão final foi medida pelo holdout 2. O conjunto de 40 casos é maior e mais difícil, então 90% e 75% não são comparáveis diretamente. A medição congelada de 735bb85 e os frescos (controle 16/18, redação 16/18, reserva 17/18) estão em `eval/resultados`; a reserva não passou na barra pré-registrada e ficou desligada, e os frescos viraram desenvolvimento depois de corrigir o caso f02 (`eval/CORRECOES.md`).

### Versão avaliada e verificação da entrega

- Código avaliado no holdout 2: **fafe24c**. Depois dele, por decisão do Rodrigo em 02/11/2026, mudaram: o banner (bolinhas indicadoras e foto de violão sem pessoa), o rodapé (sem Perguntas frequentes) e o tom de quatro respostas da Lia (acolhimento curto em reclamação irritada; todo chamado informa protocolo, prazo de 24 horas úteis e canais; pergunta sobre um dia responde só aquele dia; resumo de devolução em até 4 linhas). Saiu também a frase "um atendente já tem como falar com você", que não era verdadeira num chat anônimo. Os números do holdout 2 valem para fafe24c, e o holdout não rodou de novo; depois das mudanças, dev 62/62, variações 14/14 e conversas 108/108, com zero fatos críticos e zero chamados indevidos.
- Instalação limpa sem Docker e Docker verificados em f12c19f (01/11/2026, 23h46): 1.500 testes passando, site, modelo `qwen3:4b` e Lia respondendo. A versão final com as mudanças acima passou em 1.515 testes unitários e 210 de navegador (02/11/2026, 01h30).
- Docker, no mesmo commit, com `docker compose up -d --build`: site no ar, modelo `qwen3:4b` carregado e Lia respondendo. O download do zero foi verificado antes, em 38b8370, com cerca de 4 minutos, e nesta rodada o modelo já estava no volume.

## Exemplos de conversa

Cinco conversas em [`exemplos/`](exemplos), geradas pelo agente com `python exemplos/gerar_conversas.py` na configuração entregue (`qwen3:4b`, redação ligada): catálogo com orçamento e sugestão, informações da loja e fora do escopo, preço com nome ambíguo, promoção e parcela em conferência, devolução com consulta ao pedido e às políticas, e reclamação com chamado. Na versão e0f35d6 a redação abriu a conversa 05 com "Ola", sem acento; o validador da versão final barra saudação solta, e as conversas foram geradas de novo. As conversas 02, 04 e 05 foram geradas de novo depois dos ajustes de tom de 02/11/2026.

## Suposições documentadas

- Frete grátis em Campo Grande a partir de R$ 500,00, inclusive, apurado sobre o preço com promoção e antes do desconto do PIX. O manual diz "acima de" e "abaixo de" sem definir o valor exato.
- "Em Campo Grande" vale só para a cidade; o manual cita região metropolitana sem listar municípios.
- Frete fora de Campo Grande é uma estimativa simulada (tabela por zona a partir de MS e caixas estimadas por categoria), não tarifa dos Correios; grande porte fica em cotação individual.
- Contatos: telefone e e-mail da capa do manual e WhatsApp da seção 7; as divergências do manual aparecem em Políticas.
- Parcela mínima com duas leituras no manual: a Lia mostra as duas e oferece encaminhar.
- A Lia não usa o nome do cliente nem mostra endereço de entrega, por privacidade.
- Retirada na loja não existe no manual e não foi criada.

## Limitações conhecidas

- **Os dois holdouts reprovaram nas barras pré-registradas.** A versão final concluiu 75% contra a barra de 80%, com 5 falhas em casos de fato crítico.
- A compreensão de frases livres é o limite real: cerca de 35% dos turnos corretos em conversas novas. O teste com um modelo maior por API não foi feito.
- A Lia pode omitir parte da resposta em perguntas duplas, mas nos QAs os preços e os dados de pedido conferidos estavam certos, salvo o total por quantidade abaixo.
- A redação quase não aparece com o validador atual; a experiência da entrega é, na prática, a das regras.
- O tom da Lia não teve revisão por pessoa: o formulário previsto ficou em branco e foi retirado. O tom foi ajustado a partir da leitura das conversas de exemplo durante o desenvolvimento.
- Total por quantidade é unidade vezes quantidade, igual ao checkout; o PIX pode diferir em centavos do cálculo sobre o total.
- A consulta de produto pode citar dois valores quando a ficha contradiz a descrição nos dados originais.
- Sete produtos têm marca no nome diferente da descrição nos dados originais; os CSV não foram alterados.
- Celular e PWA testados só em Chromium emulado, sem aparelho real nem Safari.
- Produção: faltam cabeçalhos de segurança, segredo de sessão obrigatório e proteção ao cabeçalho Host; `/saude` mostra o nome do modelo; o limite de tentativas de rastreio fica em memória.
- Sem compra real nem pagamento; identificação do cliente simulada.

## Uso de assistentes de código

Usei o Claude Code com papéis separados. Um modelo mais forte (Claude Opus) explorou os dados, escreveu a especificação (`docs/SPEC.md`), pré-registrou os critérios, revisou e integrou cada entrega. Modelos mais econômicos (Claude Sonnet) implementaram cada etapa a partir da especificação aprovada, com área de arquivos delimitada e proibição de ler os conjuntos às cegas. Agentes separados fizeram auditorias somente leitura: QA de cliques, QA de conversas, QA de celular e PWA, auditoria de segurança e conformidade com o manual; os achados viraram etapas da especificação. Eu aprovei a especificação e as mudanças de testes existentes; na reta final autorizei um modo automático em que as decisões que dependiam de mim ficaram registradas para o fim. Entregas foram reprovadas e refeitas, um experimento (modelo classificando a intenção) foi medido e descartado, e os erros de medição foram declarados em `eval/CORRECOES.md`.
