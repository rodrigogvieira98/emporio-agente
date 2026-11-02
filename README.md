# Agente da Empório da Música

Lia é a assistente virtual da Empório da Música, loja fictícia de instrumentos em Campo Grande/MS. Ela responde sobre catálogo, preços, formas de pagamento, frete, status de pedidos e políticas da loja, leva a compra até o carrinho, registra reclamações e encaminha para um atendente. Junto vem um site da loja (catálogo, produto, carrinho, checkout, rastreio, políticas) com a Lia em todas as páginas, instalável como PWA.

## Resumo para quem avalia

- **Rodar:** `docker compose up -d --build` e abrir http://localhost:8000 (detalhes em [Executar com Docker](#executar-com-docker)).
- **Arquitetura:** o código entende a mensagem e busca os fatos com ferramentas determinísticas (dados dos CSV e manual da loja). Preço, pedido, prazo e regra nunca saem da cabeça do modelo.
- **Pronta para modelo por API:** `EMPORIO_PROVEDOR=anthropic` liga o Claude (Haiku 5.5 por padrão) na redação e, sem `EMPORIO_DECISOR=regras`, também na decisão das ações, sem mudar a arquitetura. Se a API falhar ou estiver mal configurada, a Lia segue com as regras. Outro provedor é uma classe nova em `provedores.py`. Custo estimado: de centavos a poucos dólares por mês nesta loja ([Trocar de modelo](#trocar-de-modelo)). A integração tem testes com o SDK simulado; a qualidade com a API real não foi medida.
- **Por que a entrega roda com regras:** sem GPU e com pouca memória, só modelos locais pequenos cabiam. Medidos no mesmo harness, eles erravam a escolha das ações, então a decisão ficou com as regras e o modelo local só pode acrescentar até 2 frases, sob um validador estrito.
- **Resultado medido:** no teste às cegas, executado uma vez (holdout 2), a Lia acertou 30 de 40 conversas e errou 5 de 22 fatos críticos, abaixo da barra pré-registrada. Os erros estão listados em [docs/RESULTADOS.md](docs/RESULTADOS.md). Frases novas são o ponto fraco das regras, e é aí que um modelo por API deve ajudar; essa hipótese ainda não foi testada.
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
| Regras decidem; modelo só redige | Medido: modelos locais decidindo erraram mais fatos que as regras (ver Resultados) | Deixar o modelo decidir com hardware sem GPU piorou conclusão e fatos |
| Modelo local `qwen3:4b` para redação | Escolhido pelo critério pré-registrado entre `qwen2.5:3b` e `qwen3:4b`: mesmos fatos, mais frases exibidas, menos descartes, mais rápido, licença Apache 2.0. Na versão final a redação quase não aparece (ver resultados) | Modelos de 8B passam de 4 GB e já mediram pior; modelos por API não foram medidos |
| Validador de redação estrito | O modelo inventou "estacionamento", ecoou um ataque e criou "verificação de crédito" | Confiar no prompt não garante a saída |
| Reserva de intenção desligada | Não passou na barra pré-registrada (ver resultados) | Ligar sem evidência contrariaria o critério |
| FastAPI, Jinja2 e HTMX, sem build de front-end, PWA | Simples de rodar e de auditar; site e Lia usam as mesmas ferramentas | SPA exigiria build e segunda fonte de dados |
| SQLite e trace JSONL sem texto do cliente | Estado da conversa, chamados e tentativas; observabilidade sem dado pessoal | Banco externo seria peso sem ganho no protótipo |
| CSV originais intactos | Inconsistências aparecem como gravadas e cobertas por teste | Corrigir em silêncio esconderia o problema do dado |

### Por que este caminho e o que faríamos com mais recursos

Rodamos tudo em uma máquina com 16 GB de RAM e sem GPU dedicada, com site, testes e modelo ao mesmo tempo. Nessas condições, modelos que cabem localmente (3B a 8B) não decidem bem: medimos quatro deles decidindo as ações e todos ficaram abaixo das regras. Por isso o código decide e o modelo só redige. Escolhemos também rodar local, sem chave e sem custo; um modelo grande por API decidindo a intenção é o candidato mais provável a melhorar a compreensão de frases livres, mas não foi testado, então é hipótese. O próximo passo seria medir `claude-haiku-5-5` e depois `claude-sonnet-5-5` na intenção, no mesmo harness e critério.

## Resultados

Resumo. As tabelas completas, os dez casos que falharam no holdout 2 e a verificação de instalação e Docker estão em [docs/RESULTADOS.md](docs/RESULTADOS.md).

| Medição | Resultado |
|---|---|
| Modelos locais decidindo as ações (dev, 62 casos) | Os quatro ficaram abaixo das regras: 38 a 40/62 concluídos e 10 a 13/31 fatos críticos errados, contra 49/62 e 4/31 das regras |
| Holdout 2, execução única (40 casos, commit fafe24c) | **30/40 (75%) e 5/22 fatos críticos errados: reprovado** (barras pré-registradas: ≥ 80% e 0) |
| Holdout original, execução única (20 casos, commit e0f35d6) | 18/20, mas **1/10 fato crítico errado: reprovado** |
| QA independente com frases inéditas | 30,1%, 33,9% e 35,4% dos turnos corretos em três rodadas: as regras chegaram ao limite para linguagem livre |
| Conjuntos de desenvolvimento, versão final | dev 62/62, variações 14/14, conversas 108/108, zero fatos críticos errados e zero chamados indevidos |

Nada foi ajustado depois de uma execução de holdout. Depois de fafe24c mudaram só o banner, o rodapé e o tom de quatro respostas da Lia; o holdout 2 não rodou de novo.

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
