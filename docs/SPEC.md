# Spec aprovada: agente da Empório da Música

Versão aprovada pelo Rodrigo em 31/10/2026.
Resumo aprovado, sha256: 73479354ed5c57210002af30cf24462732862665ea956b41b61dd400fc34db83.
Mudança material nesta spec exige parar e pedir aprovação. Sem travessão em textos gerados.

## Regras gerais

- Python >= 3.11. Código, nomes e mensagens em português. Tudo local, sem API paga.
- O modelo nunca executa SQL, nunca calcula e nunca escreve fatos críticos.
- Fato de loja fica só em `src/emporio/politicas/manual_v2_1.yaml` e no banco, nunca em `.py`.
- Dado inconsistente não é corrigido em silêncio. Total, status e histórico aparecem como gravados.
- Falha aparece ao cliente com explicação e próximo passo, sem resposta inventada.
- Dinheiro: centavos INTEGER no banco, `Decimal` no cálculo, ROUND_HALF_UP ao centavo.
- Fuso da loja `America/Campo_Grande`. Data de referência por `EMPORIO_DATA_REFERENCIA` (ISO), para demos.

## Dados

`python -m emporio.dados.carga` cria `var/emporio.db` de `data/raw/*.csv` e falha com mensagem clara em chave órfã, preço inválido ou JSON inválido em specs. Tabelas: categorias, produtos, promocoes, clientes, pedidos, itens_pedido, tentativas_pedido, chamados, conversas, mensagens_exibidas, execucoes.

`tests/test_dados_conhecidos.py` reafirma a evidência, sem corrigir nada:

- 65 produtos; categorias 6, 7 e 8 vazias; status não ativos 113, 130, 136; 96 ativo com estoque 0.
- 25 promoções, ativas nos produtos 127, 121, 90, 94; promoção 4 do produto 95 inativa.
- Totais divergentes: pedido 3 (3450 x 3498) e 20 (1400 x 1488). PIX sem 5%: 1, 5, 10, 13, 17.
- Parcela abaixo do mínimo: 9, 16, 18. Clientes 11 e 43 com mesmo e-mail. Pedido 8 enviado com previsão 2026-02-28.
- 12 violões vendáveis até R$ 1000.

## Envelope das ferramentas (Pydantic)

`Resultado(estado, dados, fontes, motivo, id_consulta)`, com `estado` em ok, vazio, ambiguo, negado, falha.
`Fonte(tipo, referencia, versao)`. `Fato(entidade_tipo, entidade_id, atributo, valor, condicao, fonte)`.
Exceção interna vira `falha`, nunca sobe ao laço. Entrada inválida vira `falha` com motivo `entrada_invalida`.

## Ferramentas

**buscar_produtos(categoria, termo, preco_min, preco_max, limite=5, incluir_indisponiveis=False)**. Normaliza acento e caixa. Limite máximo 5. Ordena por preço. Saída: itens com id, nome, preço em centavos, situacao_venda (disponivel, esgotado, descontinuado, em_breve), promoção ativa, e total_encontrado. Vendável exige `active` e estoque > 0. Categoria inexistente: `vazio`. Faixa incoerente: `falha`.

**ver_produto(referencia)**. Nome exato normalizado, senão todos os tokens no nome. Zero: `vazio`. Um: `ok`. Vários: `ambiguo` com até 5 opções. "Takamine" é `ambiguo` com 4; "Takamine GD20" é `ok` com id 95.

**calcular_condicoes(produto_id ou valor, forma, parcelas=1, cidade=None, valor_pedido=None)**. Formas: pix, debito, credito, boleto. Promoção só por is_active=1, nunca por calendário; duas ativas no mesmo produto retornam `ambiguo`. Com promoção: original, percentual, final, sem PIX. Sem promoção: PIX aplica 5%. Crédito, 1 a 12: leitura_tabela exige parcela >= 100 quando parcelas > 1. leitura_faixas exige >= 50 até 3x, >= 80 de 4 a 6, >= 100 de 7 a 12. Ambas sim: `permitido=sim`. Ambas não: `nao`. Divergem: `requer_confirmacao`. Frete: Campo Grande acima de 500 grátis, abaixo taxa do manual, exatamente 500 `requer_confirmacao`; outra cidade `cotacao_necessaria`. Valores de regra vêm do YAML.

**listar_promocoes(termo=None)**. Adicionada na revisão da etapa 3, pela seção 7.3 do manual. Devolve só promoções com is_active=1, com produto, percentual e situação de venda; nunca deduz por calendário. Termo sem promoção ativa: `vazio`, e a resposta diz que aquela promoção não está ativa no sistema.

**consultar_pedido(pedido_id, final_telefone, conversa_id)**. Identificação simulada. Pedido inexistente, final incorreto e limite de 3 tentativas por conversa retornam o mesmo `negado`. `ok` traz status, itens (nome, quantidade), total gravado, forma, rastreio, previsão, previsao_vencida, nota. Nunca nome, telefone, e-mail ou cidade.

**consultar_politica(temas)**. Lista de temas conhecidos. Devolve seções com id, título, versão, hash, texto, condições e ambiguidades ligadas. Tema desconhecido: `vazio`. Função `fato(chave)` serve as respostas rápidas da mesma fonte.

**registrar_encaminhamento(conversa_id, tipo, resumo, chave_idempotencia)**. Tipos: reclamacao, atendente, duvida_politica, sem_dado, falhas. Rejeita resumo com telefone ou e-mail. Mesma chave devolve o mesmo protocolo (`EM-000001`). Estados: registrado, encaminhamento_pendente, atendimento_iniciado; transição só por função própria. Erro de gravação retorna `falha`.

## YAML do manual

Transcrição fiel do PDF, versão 2.1, com seções, temas, `publico` (procedimento interno é false), condições estruturadas e bloco `ambiguidades`: telefone/WhatsApp, e-mail, parcela mínima, exceto abaixo de R$ 50, frete de exatamente R$ 500, região metropolitana sem lista, marco da troca por preferência, 30 x 90 dias, total de 300 instrumentos, lojas parceiras sem lista, feriados sem calendário. Quatro regras separadas com marco inicial e dados necessários: arrependimento (recebimento, compra online), preferência (marco não informado), defeito (compra, 30 dias), garantia legal (recebimento, 90 dias).

## Agente por regras

`Agente.responder(conversa_id, mensagem, origem) -> Resposta(texto, acoes, fatos, estado)`.

Laço até 3 passos: percebe, atualiza estado, `Decisor.decidir(estado, mensagem)` devolve `Acao`, código valida esquema, dados e permissão, executa, interpreta o estado da ferramenta, decide responder, perguntar ou encaminhar. `Decisor` é Protocol; `RegrasDecisor` é o controle da avaliação e o LLM entra depois sem mudar o laço.

Estado persistido: objetivo, dados coletados, dados declarados pelo cliente (marcados como declarados), assuntos pendentes, falhas seguidas, acoes_concluidas. Troca de assunto guarda o anterior e oferece retomar. `mensagens_exibidas` é separada de `execucoes`.

Intenções: saudacao, horario, endereco, contato, pagamento, busca_produto, preco_produto, disponibilidade, status_pedido, devolucao, troca_preferencia, defeito, garantia, frete, reclamacao, pedir_atendente, fora_escopo, desconhecido. "Não quero abrir reclamação" não registra; "quero abrir reclamação" registra. Pedido de atendente com negação não encaminha.

Textos em `agente/respostas.py`, com fatos só de resultados de ferramenta. Persona Lia, assistente virtual, informal mas profissional. Fora de escopo: explica que a loja vende só instrumentos, não cita loja parceira. Chamado só é anunciado depois do `ok`, dizendo "chamado registrado" e protocolo. Prazo de 24 horas úteis só em reclamação. Fora do expediente informa o horário de retorno. Elegibilidade de devolução nunca é afirmada: separa sistema, declarado e o que a equipe confirma.

Trace JSONL em `var/trace.jsonl` por turno, campo `origem` obrigatório (real, eval, demo), ferramentas, estados, ações, latência, tudo sem nome, telefone, e-mail ou final digitado.

O resumo do chamado pode conter o relato livre do cliente, inclusive nome, porque é destinado à equipe. Telefone e e-mail continuam rejeitados no resumo. Trace, estado e execuções seguem sem nome. Decisão do Rodrigo em 31/10/2026, ao aprovar a mudança do teste de trace.

Na mesma conversa, com chamado já registrado, novo pedido de atendente informa o protocolo existente e não abre outro chamado. O teste `test_mesmo_pedido_repetido_nao_duplica_chamado` passou a esperar 1 chamado em vez de 2. Mudança de teste aprovada pelo Rodrigo em 01/11/2026.

Também aprovadas pelo Rodrigo em 01/11/2026 estas alterações de testes existentes: "Eu sou a Lia" para "Sou a Lia" em `test_concisao.py` e `test_llm.py`; nova ordem de consultas em `test_devolucao_do_pedido_4_conversa_completa` e `test_mensagens_exibidas_e_execucoes_sao_tabelas_separadas`, porque a regra é dita antes de pedir o pedido; teste do rodapé em `test_web.py`, que passa a exigir um telefone e um e-mail. Aprovadas também as trocas de texto esperado pela linguagem de cliente em `test_agente.py`, `test_cli_e_utilitarios.py`, `test_defeitos_das_conversas.py`, `test_falhas_dev.py`, `test_regressao_etapa3.py`, `test_compra_demo.py` e no e2e de compra.

Canais de contato: decisão do Rodrigo em 01/11/2026, "vamos somente simular e nada mais, use os dados existentes". O site mostra os contatos do manual, sem ativar canal externo real.

CLI `python -m emporio.cli --origem demo`.

## Concisão e redundância

Complemento aprovado pelo Rodrigo em 31/10/2026, aplicado na etapa 5, quando o modelo entra. Não altera as etapas 1 a 3.

- O estado guarda `ja_informados`: chaves dos fatos e avisos já entregues na conversa, por entidade, atributo e valor.
- Evitar repetições que não acrescentem informação, preservando condições necessárias para interpretar a resposta e decidir o próximo passo. Fato ou aviso reaparece quando muda o produto, a condição ou a ação solicitada, quando o valor mudou ou quando o cliente pergunta de novo. Revisão do Rodrigo em 01/11/2026.
- Saudação no máximo uma vez por conversa.
- Texto livre do modelo: no máximo 2 frases curtas e no máximo 1 pergunta por turno.
- Antes de exibir, o código remove frase repetida ou quase igual dentro do turno e em relação às respostas anteriores, sem nunca remover bloco factual necessário à resposta atual.
- A avaliação mede tamanho da resposta em caracteres e taxa de repetição, com contagens, contra o controle por regras. A taxa conta fatos e avisos reapresentados sem pedido sobre o total de fatos e avisos exibidos.

## Site mínimo e Docker (etapas 6 e 7)

Detalhamento do plano v3 aprovado pelo Rodrigo ("pode seguir com o site e o docker", 01/11/2026). Escopo do núcleo apenas. Compra de demonstração, sentimento, streaming, interrupção e tela do atendente são incrementos e ficam fora desta etapa.

- Stack: FastAPI, Jinja2 e HTMX (versão fixa, servida localmente em `static/`, sem CDN), uvicorn. Sem framework JS e sem build.
- Páginas: início com busca, catálogo por categoria e faixa de preço, página do produto, políticas, rastreio de pedido e o chat da Lia em painel fixo em todas as páginas.
- Toda informação do site vem das mesmas ferramentas do agente (`buscar_produtos`, `ver_produto`, `calcular_condicoes`, `consultar_pedido`, `consultar_politica`, `listar_promocoes`). Nenhuma consulta SQL nas rotas, nenhum preço ou regra calculado no template.
- Situação de venda e promoção exibidas como a ferramenta devolve. Produto descontinuado ou esgotado aparece marcado, sem botão de compra.
- Rastreio usa `consultar_pedido` com número e final do telefone, com o mesmo `negado` unificado e o mesmo limite de tentativas, contado por sessão do navegador.
- Chat: `POST /chat` com `conversa_id` da sessão (cookie assinado, sem PII) chama `Agente.responder(..., origem="real")` e devolve o fragmento HTML. Texto do agente é escapado; quebras de linha viram `<br>`.
- Agente montado por `criar_agente` uma vez por processo. Padrão: `EMPORIO_DECISOR=regras` e modelo local só na redação. Ollama ausente ou com falha: o agente responde só com os blocos das regras e o trace registra a falha.
- `GET /saude` responde estado do banco e do modelo.
- Banco criado na subida se não existir, com `python -m emporio.dados.carga`.
- Docker Compose: serviço `app` (python:3.12-slim, usuário sem root, porta 8000) e serviço `ollama` com volume do modelo. Um serviço de uma vez baixa o modelo padrão. Sem GPU a stack sobe e responde; com GPU, configuração opcional documentada.
- Testes: rotas com `TestClient` (catálogo, produto descontinuado sem compra, rastreio ok e negado, chat devolve protocolo em pedido de atendente, chat sem Ollama responde). Um teste Playwright de ponta a ponta no chat e no rastreio, marcado para rodar à parte.

## Homepage e identidade visual (etapa 6b)

Pedido do Rodrigo em 01/11/2026: homepage com header e footer a partir do manual, carrossel de produtos com valores, estilo próprio decidido pelo Planner, sem copiar lojas do segmento e sem cara de site gerado por IA.

**Imagens.** Nenhuma imagem baixada da internet. Fotos de produto pertencem às marcas e lojas, o repositório é público, e uma foto genérica ao lado de um modelo específico mostraria um produto que não é o vendido, contra a regra de todo fato ter fonte. No lugar: ilustrações próprias em SVG de traço, uma por categoria (violão, guitarra, baixo, ukulele, teclado, bateria e as demais existentes), reaproveitadas no card do produto conforme a categoria.

**Direção visual: balcão de loja de música do Centro de Campo Grande.**
- Cores (tokens CSS): papel `#F4EEE3`, tinta `#1F1A17`, jacarandá `#6B3A23`, ipê `#E3A72F` só em destaque pontual (etiqueta de promoção, foco), pantanal `#2F4A3A` para "disponível", cinza quente `#8A8178` para texto secundário. Sem gradiente, sem roxo, sem vidro fosco, sem sombra difusa grande.
- Tipografia: Zilla Slab (títulos, preços, logotipo) e Public Sans (texto), ambas OFL, servidas localmente em woff2 com o arquivo de licença. Números de preço com algarismos tabulares.
- Forma: bordas de 1px na cor tinta, cantos de 2 a 4px, grade assimétrica, filete horizontal separando seções como em impressão. Preço em "etiqueta" de papel com furo e barbante desenhados em CSS/SVG.
- Proibido (cara de IA): emoji, ícones genéricos em círculo, três cards iguais centralizados com ícone, texto em gradiente, hero gigante com frase de efeito em inglês ou genérica ("eleve seu som"), contadores animados, depoimentos inventados.

**Estrutura da homepage.**
1. Faixa superior: endereço, horário de hoje e "aberta agora" ou "fechada, abre às X", calculados por `expediente` a partir do manual.
2. Header: logotipo tipográfico com pequena marca SVG própria, busca, menu de categorias, links Políticas e Rastrear pedido, botão Falar com a Lia.
3. Vitrine (carrossel): produtos com promoção ativa (`listar_promocoes`) e, para completar até 8, os mais baratos vendáveis de categorias diferentes (`buscar_produtos`). Cada etiqueta mostra preço de tabela, promoção quando houver (original, percentual, final) e condição PIX ou parcelamento vinda de `calcular_condicoes`. Carrossel em CSS scroll-snap, navegável por teclado e sem JS obrigatório; setas são realce progressivo.
4. Categorias com as ilustrações; categoria sem produto vendável aparece como "em breve" sem link quebrado.
5. "Como funciona comprar aqui": pagamento, frete, troca e garantia, com texto curto vindo de `consultar_politica`/`fato()`, incluindo as ressalvas das ambiguidades registradas (ex.: frete de exatamente R$ 500 confirmado pela equipe). Link para Políticas.
6. Chamada para a Lia, com exemplos de perguntas clicáveis que abrem o chat já preenchido.
7. Visite a loja: endereço, horário completo e contatos, sem mapa externo.
8. Footer: navegação, contatos do manual com origem (já existente), formas de pagamento em texto, políticas, e o aviso "Loja fictícia criada para um desafio técnico; dados de demonstração".

**Regras que continuam valendo.** Todo fato vem das ferramentas ou do manual (teste de literais cobre templates e CSS). Texto de marca que não é fato (títulos de seção, chamadas) pode ficar no template. Responsivo de 360px a 1440px sem rolagem horizontal da página. Contraste AA. Foco visível.

**Testes.** Rota `/` com vitrine contendo os 4 produtos em promoção ativa e seus valores (Crafter HT-100: 2.399,00, 18%, 1.967,18), nenhuma promoção inativa, categoria vazia sem link, faixa de expediente aberta e fechada por `EMPORIO_DATA_REFERENCIA`, aviso de loja fictícia no footer. Playwright: carrossel navegável por teclado, captura de tela em 390px e 1280px anexada à entrega.

## PWA (site inteiro e a Lia)

Exigência do Rodrigo em 01/11/2026: o projeto todo é otimizado para PWA, inclusive o chat da Lia.

- `manifest.webmanifest` com nome, nome curto, `start_url` `/`, `display` `standalone`, `theme_color` e `background_color` dos tokens, ícones 192 e 512 em PNG e versão `maskable`, gerados a partir da marca SVG própria (renderizados localmente, por exemplo com Playwright; nada baixado).
- Service worker em `/sw.js` (escopo raiz), versionado por constante. Estratégias:
  - estáticos (CSS, JS, fontes, SVG, ícones): cache-first, pré-cache na instalação;
  - páginas HTML: network-first com página offline própria como fallback;
  - `/chat`, `/rastreio`, `/saude` e qualquer POST: network-only, nunca em cache. Preço, estoque, pedido e resposta da Lia nunca são servidos de cache, porque fato velho é fato errado.
- Offline: página própria no estilo do site, dizendo que preços, pedidos e a Lia precisam de conexão, com endereço e horário do manual (pré-cacheados a partir do HTML gerado pelo servidor na instalação). O chat, sem rede, mostra aviso no painel e mantém o texto digitado para reenviar; não finge resposta.
- Mobile primeiro: a Lia abre em tela cheia abaixo de 768px, com campo de texto fixo acima do teclado (`100dvh`, `env(safe-area-inset-*)`), alvos de toque de no mínimo 44px, `enterkeyhint="send"`, sem zoom automático no foco (fonte de 16px no campo).
- Metas: `viewport` com `viewport-fit=cover`, `theme-color`, `apple-touch-icon`, `apple-mobile-web-app-capable`.
- Instalação exige HTTPS ou localhost; o README diz isso.
- Testes: manifest válido e servido com o tipo correto, `sw.js` servido com `Service-Worker-Allowed` adequado e cabeçalho sem cache, rota offline existe. Playwright: service worker registrado, página offline aparece com a rede cortada, `/chat` sem rede mostra aviso e preserva o texto, layout da Lia em 390px sem rolagem horizontal. Lighthouse não é exigido.

## Site real: revisão do Rodrigo (etapa 6c)

Pedido do Rodrigo em 01/11/2026. Substitui, onde houver conflito, as seções "Homepage e identidade visual", "Incremento 1" e o rodapé. Mantêm-se cores, tipografia, regra de fato com fonte e PWA.

**O site e a Lia parecem uma loja de verdade.** Só o repositório sabe que é teste.
- Nenhum texto ao cliente cita manual, sistema, ferramenta, seção, origem de dado, demonstração, teste, desafio ou loja fictícia. O aviso de loja fictícia sai do site e fica no README.
- Número de pedido passa de `DEMO-0001` a `PED-0001`. Sem pagamento real: a confirmação diz "Pedido registrado. Nenhum valor foi cobrado." e continua sem campo de cartão, CPF ou endereço. Saem os avisos de demonstração e de estoque não baixado.
- Ambiguidade do manual continua nunca resolvida em silêncio, em linguagem de cliente: "Esse caso precisa de confirmação da nossa equipe." A evidência fica em `manual_v2_1.yaml`, nos docs e nos testes. Sistema: "conforme o estoque agora", "total do pedido".
- A Lia continua se identificando como assistente virtual.

**Fale Conosco** (`/fale-conosco`, no menu e no rodapé): WhatsApp com ícone e link `https://wa.me/55DDDNUMERO` para o canal de WhatsApp do manual (seção 7, `contato.whatsapp_secao_7`); telefone com ícone e `tel:` para `contato.telefone_capa`; e-mail com ícone e `mailto:` para `contato.email_capa` (grafia sem acento, válida como endereço). Endereço e horário. Formulário: nome, e-mail, assunto e mensagem, com validação no servidor, campo isca contra spam e link para a privacidade. Grava em tabela nova `mensagens_contato` e devolve protocolo `FC-0001`. Envia por SMTP só com `EMPORIO_SMTP_*` configurado; sem isso, fica gravada. A tela só diz "Mensagem recebida", nunca "e-mail enviado". Rodapé e "Visite a loja" usam os mesmos três links com ícone. Ícones SVG próprios.

**Perguntas frequentes** (`/perguntas-frequentes`, no menu e no rodapé, com bloco das principais na homepage): 8 a 12 perguntas em `<details>`, nativas e acessíveis, com respostas vindas do manual via `fato()`/`consultar_politica`: formas de pagamento, parcelamento, PIX, frete, prazo, troca, devolução, garantia, rastreio e horário. Sem fato literal em template.

**Carrossel** no modelo do Radar (`frontend/src/pages/LandingPage.tsx`, só leitura, adaptar ao nosso estilo em JS puro): cartão central em destaque, vizinhos menores e translúcidos atrás (escala 1, 0,87, 0,74; opacidade 1, 0,55, 0,18; deslocamento lateral), em laço, com transição de 0,45 s, clique no vizinho centraliza, setas, pontos, arrasto ou toque com limite de 40 px, setas do teclado, `aria-live` com o produto em destaque e `prefers-reduced-motion`. Sem JS, cai na grade rolável.

**Lia flutuante:** botão redondo fixo no canto inferior direito, com retrato ilustrado próprio, que abre o painel do chat sobre a página e mantém a conversa ao navegar. Começa fechada em todas as páginas. Abaixo de 768px, abre em tela cheia, como já está. Sem barra fixa. "Falar com a Lia" no header abre o mesmo painel.

**Fotos reais de instrumentos.** Decisão do Rodrigo, que substitui a regra de só ilustrações. Fotos por tipo de instrumento (violão nylon, folk, guitarra, baixo, ukulele, teclado, bateria e o que houver no catálogo), de licença livre verificada na origem: Wikimedia Commons, domínio público, CC0 ou CC BY/BY-SA. Nunca foto de loja ou marca. Sem marca legível que contradiga o produto. WebP local, até 200 KB. Tag "Imagem ilustrativa" no cartão e no produto. Autor, licença e link em `docs/CREDITOS_IMAGENS.md` e em `/creditos`, ligado no rodapé. Fundo uniforme recortado ou enquadramento coerente, para a vitrine não parecer colagem.

**Boas práticas:** título e descrição por página, favicon, Open Graph, página de privacidade a partir do manual (LGPD), trilha de navegação no produto, foco visível, foto com `alt`, `loading="lazy"` e dimensões declaradas.

**Política de privacidade e cookies** (`/privacidade`, no rodapé), escrita para este produto, descrevendo só o que ele faz de verdade, conferido no código: cookie de sessão assinado e por que existe, ausência de cookie de publicidade e de rastreadores de terceiros, armazenamento no navegador do histórico do chat, cache do app instalado (só visual, nunca preço ou pedido), o que o chat e o Fale Conosco guardam, quem responde (assistente virtual e equipe), mensagens processadas por modelo rodando nos servidores da loja, carrinho e pedido por sessão, finalidades e direitos do manual (LGPD) e canal de contato. Sem inventar prazo de retenção, encarregado ou CNPJ que o manual não traga: o que faltar não é citado. Sem banner, porque o único cookie é essencial; um link discreto basta. Linguagem de cliente, e um teste por afirmação verificável (nome do cookie, atributos, ausência de script externo).

**Revisão de disposição e repetição, página por página.** Cada página tem um único propósito e a informação aparece em um só lugar por página:
- Contato completo só em Fale Conosco e, resumido, no rodapé. Um e-mail só em todo o site; nenhuma grafia alternativa em lugar nenhum.
- Faixa superior: só situação da loja (aberta ou fechada). Endereço fica no rodapé e em Visite a loja, sem repetir na mesma tela além desses.
- Homepage: abertura curta, vitrine, categorias, 4 a 5 perguntas frequentes, visite a loja (endereço, horário e link), rodapé. Sai "Como funciona comprar aqui", cujo conteúdo vive em Políticas e Perguntas frequentes. Sai a faixa "Pergunte para a Lia" e o botão do header: a Lia flutuante já está em toda página.
- Rodapé: quatro colunas enxutas, sem repetir horário nem texto da homepage.
- Produto: foto e nome, preço, condições, ação de compra, descrição e especificações, nessa ordem, sem repetir preço.
- Catálogo: filtros à esquerda no desktop e recolhidos no celular, grade de produtos com paginação ou "ver mais" dentro do limite de 5 por consulta da ferramenta, chamada repetida por página.
- Políticas: índice lateral ou no topo, um tema por âncora.
- Rastreio, carrinho e checkout: coluna única e clara, resumo ao lado no desktop.
Teste que conte que o e-mail aparece uma vez por página, e que nenhuma frase longa se repete na mesma página.

**Fechar ao clicar fora.** Todo elemento aberto sobre a página (menu de categorias, painel da Lia no desktop, filtros recolhidos, modais) fecha com clique ou toque fora dele e com a tecla Esc, devolvendo o foco a quem o abriu. Clique dentro não fecha. Abrir um fecha o outro. Teste e2e para cada um.

**Testes:** varredura de termos proibidos ao cliente em todo HTML renderizado, em `chat.js` e em todos os textos de `respostas.py`; links do Fale Conosco; formulário gravando e rejeitando inválido; FAQ com valores iguais aos do manual; carrossel por teclado, clique e toque; chat flutuante abre, conversa e fecha em 390 e 1280 px; toda imagem com crédito. Rejeitos de gabarito por mudança de frase são listados para aprovação.

## Composição "Loja acolhedora" (etapa 6d)

Revisão enviada pelo Rodrigo em 01/11/2026. Prevalece sobre a etapa 6c e as seções anteriores de site onde houver conflito.

**Homepage:** cabeçalho compacto com busca visível, abertura estática com fotografia editorial, título curto ("Seu próximo som começa aqui") e uma ação principal ("Explorar instrumentos"); categorias antes da vitrine; vitrine; 4 perguntas frequentes (pagamento, entrega, acompanhamento, trocas) com link para detalhes; visita à loja; rodapé enxuto. Identidade: fundo claro quente, texto escuro, verde nas ações principais, enquadramento consistente nas fotos, cores verificadas quanto à legibilidade. A etiqueta com barbante fica como detalhe menor.

**Cartão de produto:** foto, nome, preço, condição principal, acesso ao produto, nessa ordem. Promoção com preço original, percentual e final.

**Carrossel:** só para destaques, controlado pelo usuário, sem avanço automático. O Radar é referência de movimento, com cartões legíveis e sem perda de comparação. Controles identificados, teclado e redução de movimento, conforme o tutorial de carrosséis da W3C. O resto dos produtos em grade.

**Repetição:** substitui a regra de uma vez por página. Não repetir blocos completos sem necessidade; repetir ações quando isso facilitar a tarefa. Contatos com uma fonte única, sem variantes contraditórias. Sai o teste que conta e-mails.

**Lia:** botão com retrato e rótulo "Lia · conversar", inicialmente fechado, nunca abre sozinho e não cobre ações de compra. O painel mostra nome, identificação como assistente virtual, fechar visível e sugestões curtas ("Encontrar instrumento", "Consultar pedido", "Trocas e devoluções"), preserva a conversa ao navegar e, no celular, é amplo com campo acima do teclado.

**Fotos:** decisão do Rodrigo em 01/11/2026, por ser protótipo: todo produto tem foto real de instrumento, sem "Foto do produto indisponível". Usa a do modelo exato quando houver licença livre; senão, a do mesmo tipo de instrumento, com variação suficiente para os cartões não parecerem iguais (cor, corpo, nylon ou aço). Como o repositório é público, as fotos continuam de licença livre, com crédito em `/creditos`, e o README diz que elas são representativas do tipo de instrumento.

**Fale Conosco por intenção:** Conversar (WhatsApp, ícone e texto), Ligar, Escrever, Deixar uma mensagem. Formulário com assunto, mensagem e contato para retorno; sem campo inútil; texto preservado em erro; confirma só "Mensagem registrada". Canais operacionais só viram link quando verificados: `EMPORIO_WHATSAPP_URL`, `EMPORIO_TELEFONE_LINK` e `EMPORIO_EMAIL_LINK`. Sem essas variáveis, os contatos aparecem como texto com ícone, porque os números do manual são fictícios e podem pertencer a terceiros.

**FAQ:** ajuda, não segunda página de políticas. Na página completa, agrupada por tema. Condição essencial fica na resposta inicial.

**Compra:** antes de confirmar, o checkout diz com clareza que o pedido não gera cobrança nem entrega. Linguagem de cliente, sem detalhe interno.

**Linguagem ao cliente:** omitir detalhes de implementação (seção do manual, ferramenta, origem do dado) e preservar o necessário para entender o que será realizado. Sem varredura indiscriminada de palavras como "sistema" ou "teste".

**Catálogo:** paginação própria, independente do limite de 5 itens por resposta do chat. `buscar_produtos` ganha `deslocamento` e limite maior para a interface do site; a Lia continua pedindo 5. Regras de preço e disponibilidade são as mesmas.

**Categorias vazias** saem da seleção principal; sem "em breve", porque ausência no catálogo não comprova lançamento. **Frete** sempre com a região explícita ("Em Campo Grande: ...").

**Validação:** encontrar um instrumento, consultar condições, acompanhar pedido, abrir e fechar a Lia, enviar mensagem e entender o alcance da compra, em celular e desktop, inclusive por teclado.

## Persona da Lia

Orientação do Rodrigo em 01/11/2026. Faz parte do núcleo. A persona muda a maneira de dizer e não autoriza prometer o que o sistema não consegue fazer. Sem treino de modelo nem chamada extra de IA.

1. **Definição curta:** `src/emporio/agente/persona.yaml` com nome, identificação como assistente virtual da loja, tom, exemplos e comportamentos a evitar. Entra nas instruções do modelo em todos os turnos em que ele redige. Nenhum fato de loja nesse arquivo.
2. **Templates com a mesma voz:** `respostas.py` escrito na voz da persona, sem passar pelo modelo só para ganhar estilo. Exemplos que orientam a voz:
   - saudação: "Oi! Sou a Lia, assistente virtual da Empório da Música. Como posso te ajudar?";
   - produto indisponível: "Esse modelo está sem estoque no momento. Quer que eu procure opções parecidas?", e essa oferta só existe porque um "sim" executa `buscar_produtos` na mesma categoria;
   - falha na consulta: "Não consegui consultar seu pedido agora. Posso tentar novamente.", só com nova tentativa real;
   - cliente frustrado: "Entendo sua frustração. Vou conferir o que está registrado sobre o seu pedido.", só quando a consulta de fato ocorre no turno.
3. **Revisão de conversas completas:** conferir principalmente as transições entre template e modelo.

**O que o código verifica:** apresentação nos templates, apresentação no máximo uma vez, campos obrigatórios da persona, expressões proibidas em `persona.yaml` (gíria forçada, "sem enrolação", emoji, tratamento formal como "prezado cliente", brincadeira) em todos os textos de `respostas.py`.

**O que exige avaliação humana:** acolhimento, naturalidade e adequação à situação. `eval/REVISAO_TOM.md` registra as conversas lidas e estas perguntas, com sim ou não: ela se identifica corretamente? Evita repetir a apresentação? Mantém clareza? Evita brincadeiras diante de reclamações? Os templates parecem vir da mesma assistente que escreve as respostas do modelo? A leitura do Planner é marcada como preliminar; a avaliação humana é a do Rodrigo.

## Incremento 1: compra de demonstração

Do plano v3 aprovado (incremento 1, aceito pelo Rodrigo: "compra de demonstração sem pagamento real").

- Carrinho por sessão do navegador, guardado no servidor (tabela nova `carrinhos` e `pedidos_demo`; os dados originais e a tabela `pedidos` não mudam).
- Só produto vendável entra no carrinho; quantidade de 1 a 3 por item; estoque não é baixado e a página diz isso.
- Checkout: forma de pagamento, parcelas, cidade. Totais, promoção, PIX, parcela e frete vêm só de `calcular_condicoes`, item a item e no total. Opção com `requer_confirmacao` (parcela mínima ambígua, frete de exatamente R$ 500) aparece marcada "a confirmar com a equipe" e não pode ser finalizada como confirmada; cidade fora de Campo Grande mostra "frete calculado pela equipe".
- Finalizar cria `pedidos_demo` com número `DEMO-0001`, total por item gravado em centavos e aviso fixo "pedido de demonstração, nenhum pagamento é feito". Rastreio e Lia reconhecem `DEMO-` e respondem como demonstração, sem misturar com os pedidos dos dados.
- Nova ferramenta só se necessária para a Lia consultar pedido de demonstração, com o mesmo envelope `Resultado`.
- Botão "Quero comprar" da página do produto passa a adicionar ao carrinho; "Quero comprar com a Lia" continua.
- Testes: carrinho com produto em promoção e PIX (sem somar), parcela com `requer_confirmacao`, frete exato de R$ 500, produto descontinuado recusado, total igual à soma das ferramentas, `DEMO-` no rastreio, nada gravado em `pedidos`. E2E do fluxo completo em 390px.

## Incremento 2: sentimento adapta o tom

Do plano v3 aprovado. Sentimento muda só o tom, nunca fatos, permissões nem ferramentas.

- Detector determinístico por turno: `neutro`, `frustrado`, `irritado`. Sinais: vocabulário de frustração e raiva, ofensa, CAIXA ALTA em boa parte da mensagem, pontuação repetida, "de novo", "ninguém responde", repetição da mesma pergunta, falhas seguidas do agente. Ironia não é tentada.
- Efeitos: `frustrado` acrescenta uma frase curta de reconhecimento antes do bloco (texto em `respostas.py`, variando entre poucas formas e nunca repetida na mesma conversa) e encurta o restante; `irritado` faz o mesmo e oferece atendimento humano com pergunta de sim ou não. Dois turnos seguidos frustrados também oferecem. Oferta recusada não se repete na conversa. Chamado só com "sim" explícito, como hoje.
- Sem frase de empatia em turno neutro, sem desculpa por fato correto, sem prometer prazo fora do manual.
- O estado guarda o sentimento por turno; o trace registra o rótulo, não o texto.
- Testes: rótulos em frases de exemplo (incluindo negações e falsos positivos como "não estou bravo, só quero saber o preço"), reconhecimento sem fatos alterados, oferta de humano com irritação, oferta recusada não volta, nenhuma frase de empatia em neutro, controle no dev sem regressão.

## Revisão final do site (etapa 6e)

Aprovada pelo Rodrigo em 01/11/2026. Prevalece sobre as seções anteriores do site nestes pontos. Ferramentas, regras e textos do agente não mudam.

**Checkout recalcula sozinho.** O manual define PIX com 5% sobre o preço de tabela, sem somar com promoção; débito e boleto à vista; crédito até 12x sem juros. Hoje o total só muda ao clicar em "Atualizar valores". Trocar forma, parcelas ou CEP passa a atualizar resumo, total, `total_visto`, pendências e o estado de "Registrar pedido" sem clique extra, com HTMX e sem recarregar a página, preservando o foco no campo. Sem JavaScript, o botão de atualizar continua funcionando (`noscript`). Respostas fora de ordem não podem sobrescrever a escolha mais recente. O campo de parcelas só aparece com crédito. A conferência de `total_visto` no servidor continua.

**Localizador de CEP em todo o país.** Decisão do Rodrigo em 01/11/2026: o site atende o Brasil inteiro, o que substitui a ideia de usar só a faixa de Campo Grande. O campo "Cidade da entrega" vira "CEP de entrega", com 8 dígitos, com ou sem hífen. Ao informar o CEP, o site mostra o endereço localizado (logradouro quando houver, bairro, cidade/UF) e recalcula o frete. Ao lado do campo há o link "Não sei meu CEP", para a busca dos Correios (https://buscacepinter.correios.com.br/app/endereco/index.php), em nova aba.

A consulta é feita pelo servidor no ViaCEP (`https://viacep.com.br/ws/{cep}/json/`), com a biblioteca padrão, limite de 3 segundos e memória em processo. O navegador não fala com terceiros, e nenhuma dependência nova é criada. Resultados:
- Campo Grande com UF MS: cidade base do manual, com a regra atual de frete. A UF é obrigatória, porque existe Campo Grande/RN;
- outra cidade: `cotacao_necessaria`, com "Frete calculado pela equipe", passando `Cidade/UF` a `calcular_condicoes`. Os dados não têm peso nem dimensões, então o site não inventa valor;
- CEP inexistente (`{"erro": "true"}`): pendência "CEP não encontrado", impede finalizar;
- CEP vazio ou com formato inválido: pendência com mensagem clara, impede finalizar, sem consulta externa;
- serviço fora do ar, lento ou com resposta inválida: nunca derruba o checkout. Faixa 79000-000 a 79129-999 vale como Campo Grande/MS; fora dela, "Não localizamos o endereço agora" com frete calculado pela equipe, sem bloquear a compra. A falha fica registrada em log;
- CEP da loja no manual (79202-333): não existe no ViaCEP e é tratado como Campo Grande/MS, sem consulta.

`calcular_condicoes` não muda; quem traduz CEP em cidade é o site. O pedido grava só a cidade derivada (`Recife/PE`), sem o CEP. O aviso do checkout passa a dizer que não se deve informar cartão nem CPF e que o CEP serve só para localizar a entrega e calcular o frete. A página de Privacidade passa a dizer que o CEP é consultado pelo servidor no ViaCEP, que não fica guardado e que o site continua sem carregar scripts de terceiros; a frase "não pede endereço" é ajustada. O README declara o serviço, a contingência e que o frete fora de Campo Grande depende da equipe. `EMPORIO_CEP_EXTERNO=0` desliga a consulta e usa só a contingência. Testes nunca acessam a rede.

**Endereço só no rodapé.** Referência observada: Teclacenter, KaBuM! e Thomann concentram contato e endereço no rodapé e em área própria de atendimento. O endereço sai do corpo da home e da página Fale Conosco. A página offline mantém o endereço, porque não tem rodapé.

**Faixa "Fale conosco".** Modelo enviado pelo Rodrigo em 01/11/2026: um card branco de cantos arredondados, logo acima do rodapé, com três blocos lado a lado separados por divisórias verticais, cada um com ícone de traço fino à esquerda. Usa as cores e fontes da Empório, sem copiar a marca da referência:
1. ícone de envelope e botão contornado "Fale conosco", para `/fale-conosco`;
2. ícone de telefone, número em destaque e horário de atendimento em uma linha curta, com os dados do manual;
3. ícone de pacote, a frase "Já fez seu pedido e quer saber onde ele está?" e botão contornado "Rastrear pedido", para `/rastreio`.

**"Para começar" em carrossel.** Decisão do Rodrigo, para compactar a home. A grade da seção "Para começar" vira carrossel, com o mesmo componente, os mesmos controles e o mesmo comportamento da vitrine de destaques, reaproveitando `vitrine.js` e o CSS existentes. Os dois carrosséis funcionam de forma independente, sem autoplay, com rótulos acessíveis próprios, e sem rolagem horizontal da página em 390 px. Cada um mantém seus produtos e o link "Ver todos os instrumentos".

**Canais e contato: decisão final do Rodrigo em 01/11/2026.** Prevalece sobre o que estiver diferente nesta seção.
- O botão "Fale conosco" da faixa abre `/fale-conosco`.
- Em `/fale-conosco`, WhatsApp e Telefone têm ícone e link ativo por padrão, gerado dos dados do manual: `https://wa.me/55DDDNUMERO`, em nova aba, e `tel:`. Decisão do Rodrigo, que prevalece sobre a anterior de deixar sem link. `EMPORIO_WHATSAPP_URL` e `EMPORIO_TELEFONE_LINK` substituem o padrão. O README avisa que os números são os do manual da loja fictícia.
- O bloco de e-mail tem o link específico "Enviar e-mail", com `mailto:`.
- O telefone da faixa tem link `tel:`, com o ícone do WhatsApp ao lado, com o mesmo link da página.
- A faixa mostra o endereço resumido (rua, número e cidade/UF). O endereço completo, com CEP, fica em `/fale-conosco`. É uma repetição útil e permitida.
- O rodapé segue sem link "Fale conosco" e sem dados de contato.

**Privacidade: decisão final.** Texto em linguagem simples, descrevendo o funcionamento real. Sai o jargão técnico. Informa que o cookie nasce na primeira visita e que o site não tem prazo automático de exclusão: os dados ficam até o cliente pedir a exclusão. Não declara prazo de retenção nem base legal específica sem fundamentação. Informa que "Enviar e-mail" abre o aplicativo de e-mail do cliente.

**Frete: decisão final.** Decisão do Rodrigo, seguindo a prática de mercado: em Campo Grande, frete grátis **a partir de** R$ 500,00, inclusive, e taxa de R$ 35,00 de R$ 499,99 para baixo, no site e na Lia. O manual diz "acima de" e "abaixo de" e não define o valor exato: essa é uma decisão da loja para resolver a ambiguidade `frete_exatamente_500`, e o texto original do manual fica intacto. Os textos ao cliente passam a dizer "a partir de R$ 500,00". O CEP é obrigatório para simular a entrega, não para navegar ou conversar. Fórmula ou tabela de frete estimado só entra depois de aprovada pelo Rodrigo.

A faixa fica em `base.html`, em todas as páginas com rodapé, exceto `/fale-conosco`. No celular os blocos empilham, com divisórias horizontais. Ela não pode ficar coberta pelo botão da Lia.

A seção "Visite a loja" sai da home, porque a faixa a substitui. O rodapé deixa de repetir canais: a coluna "Atendimento" sai, assim como "Todos os canais", e ficam nome, endereço, "Comprar" e "Informações". O rótulo "Falar com a loja" deixa de existir.

**Rodapé sem dados de contato.** Decisão do Rodrigo, que prevalece sobre "Endereço só no rodapé" e sobre os itens acima que mantêm o endereço no rodapé. Dado de contato fica em um lugar só. O rodapé mostra nome da loja, as colunas de links "Comprar" e "Informações" e nenhum endereço, telefone, e-mail ou WhatsApp. O endereço aparece apenas em `/fale-conosco`, no card ao lado do formulário, que passa a se chamar "Onde estamos e horários", e na página offline. O telefone aparece na faixa e em `/fale-conosco`, nunca nas duas ao mesmo tempo, porque a faixa não aparece nessa página.

**Fale conosco sai do cabeçalho.** Decisão do Rodrigo. O link deixa o menu do cabeçalho, no computador e no celular. O acesso passa a ser pela faixa e por um link "Fale conosco" na coluna "Informações" do rodapé.

**Página `/fale-conosco` refeita.** A versão atual foi reprovada pelo Rodrigo. Ela empilha blocos soltos, deixa metade da tela vazia e repete "Deixar uma mensagem". Novo desenho, na mesma linguagem visual da faixa:
- título "Fale conosco" e uma frase curta;
- card branco com três blocos e divisórias, igual ao da faixa: WhatsApp, Telefone e E-mail, cada um com ícone, rótulo claro e o dado do manual. Os rótulos "Conversar", "Ligar" e "Escrever" e o quarto card "Deixar uma mensagem" saem desta página;
- abaixo, duas colunas alinhadas: à esquerda, card branco com o formulário "Envie uma mensagem"; à direita, card menor "Horário de atendimento" com as linhas do manual e a orientação de rastreio, com botão para `/rastreio`, sem endereço;
- as colunas têm a mesma altura e nada fica vazio à direita. Campos e botão seguem a largura do card;
- no celular, a ordem é canais, formulário e horário, sem rolagem horizontal, e o botão da Lia não cobre os canais nem o botão de envio ao final da rolagem;
- a confirmação com protocolo continua funcionando na mesma página.

**Sugestões da Lia não enviam sozinhas.** Clicar numa sugestão, ou em "Quero comprar com a Lia", abre o painel, preenche o campo e põe o foco nele. A mensagem só sai quando o cliente envia, com Enter ou com o botão Enviar, e o texto pode ser editado antes.

**Cache do PWA.** A versão do cache passa a ser um hash do conteúdo dos estáticos, calculado pelo servidor, em vez de um número manual. Mudou um arquivo, muda a versão. Assim um navegador que já visitou o site não mistura HTML novo com CSS antigo.

**Testes.** Aprovada a alteração de testes que preenchem cidade no checkout, do rótulo "Falar com a loja" e do teste que espera envio automático ao clicar na sugestão. Nenhum teste é apagado ou enfraquecido: cada um passa a cobrir o comportamento novo.

## Revisão da Lia (etapa 7)

Aprovada pelo Rodrigo em 01/11/2026, depois de 36 falas reais com cerca de metade das respostas ruins, apesar do dev em 62/62. Fatos continuam escritos por código, e o modelo nunca escreve preço, prazo ou protocolo.

**Etapa 1: correções por regras.**
1. Identidade: "quem é você", "é robô ou pessoa", "qual seu nome" e "o que você faz" recebem resposta da persona, dizendo que é assistente virtual.
2. Encerramento: agradecimento e despedida recebem despedida curta, nunca oferta de chamado. Não contam como falha de entendimento e zeram o contador de falhas.
3. Contexto: depois de uma lista, "qual o mais barato" usa essa lista; depois de um pedido consultado, "quando chega" usa esse pedido; "tem em estoque" e "quanto fica no pix" usam o produto em foco ou o primeiro da lista quando estiver claro.
4. Catálogo: categoria sem marca lista produtos ("quanto custa uma gitarra", "violao barato", "tem teclado"), com tolerância a erro de digitação comum ("gitarra", "ukelele"), inclusive quando há "barato" ou "mais em conta". Um pedido genérico de preço nunca pede marca e modelo se a categoria foi identificada.
5. Reembolso: "em quanto tempo recebo o dinheiro" responde com o prazo do manual.
6. Frete: cidade fora da base informa que o frete é calculado pela equipe, sem pedir valor do pedido. O valor só é pedido para Campo Grande.
7. Duas perguntas na mesma mensagem: responde as duas quando forem intenções conhecidas.
8. Resposta proporcional: "aceitam boleto" e "vocês parcelam" respondem só o tema perguntado, sem listar todas as regras. "e em 12x" sem produto pede o produto em uma frase. Mantém a informação da ambiguidade da parcela mínima quando o assunto for parcela.
9. Pedido: forma de pagamento nunca aparece crua (`debit`, `credit`), e a frase de status fica natural.
10. Recusa: pedido de prompt ou de instruções internas recebe recusa própria, sem falar de desconto.
11. Redação: o validador rejeita frase que comece em minúscula e frase genérica de oferta. Respostas de recusa e de escopo não recebem redação.
12. "sim" sem pergunta pendente recebe resposta natural, sem "não entendi".

**Etapa 2: modelo como reserva de intenção.** Só depois da etapa 1. Quando a percepção por regras não achar intenção e houver modelo, ele escolhe um rótulo de uma lista fechada de intenções sem efeito colateral, ou "nenhuma". Código valida o rótulo, e as regras seguem com slots, ferramentas e respostas. A lista exclui chamado, e o modelo nunca autoriza identificação de cliente. Falha, tempo esgotado ou rótulo inválido voltam ao fluxo atual, sem mentir. Telemetria: `reserva_tentada`, `reserva_aceita`, `reserva_nenhuma`, `reserva_falha`. `EMPORIO_RESERVA=0` desliga. A decisão de manter ligada segue `eval/PREREGISTRO_RESERVA.md`.

**Avaliação.** Os achados viram `eval/casos_conversas.jsonl`, usado para ajuste. `eval/casos_frescos.jsonl` e o holdout não são lidos por quem implementa nem usados para ajuste.

## Frete estimado e auditoria (etapa 8)

Aprovada pelo Rodrigo em 01/11/2026 (decisões 1 a 12, todas na opção A). Prevalece sobre as seções anteriores nestes pontos, inclusive sobre "o site não inventa valor".

**Limite do frete grátis.** Em Campo Grande/MS, grátis a partir de R$ 500,00 em produtos, considerando promoções e antes do desconto do PIX. Abaixo disso, R$ 35,00. A forma de pagamento nunca muda o frete. Vale no site e na Lia. A Lia compara cidade e UF quando a UF for informada: Campo Grande/RN não recebe a regra da base. "Em Campo Grande" é só a cidade, com nota em `/politicas` explicando que as demais cidades seguem o frete estimado.

**Frete estimado (simulação).** Hipótese do protótipo, não tarifa de transportadora. Função única `estimar_frete` em `src/emporio/ferramentas/`, usada pelo site e pela Lia, determinística, com envelope `Resultado`. Tabelas em YAML próprio, separado do manual (`src/emporio/politicas/frete_simulado.yaml`), com a indicação de que são hipóteses. A consulta de CEP passa a morar em `ferramentas/`, porque o agente não importa `web/`.

- Por caixa: peso taxado = maior entre peso real e C × L × A ÷ 6.000, arredondado para cima por kg.
- PAC = base da zona + por kg × (peso taxado − 1), mais adicional.
- SEDEX = (base da zona + por kg × (peso taxado − 1)) × 1,6, mais adicional.
- Adicional de R$ 11,19 quando um lado passa de 100 cm.
- Cada unidade é uma caixa, e o pedido soma as caixas.
- Zonas com origem em MS: MS fora de Campo Grande, base R$ 21,00 e R$ 1,80 por kg; SP, PR, MT, GO, DF, MG, R$ 26,00 e R$ 2,50; RJ, ES, SC, RS, R$ 29,00 e R$ 2,90; BA, SE, AL, PE, PB, RN, CE, PI, MA, TO, R$ 33,00 e R$ 3,20; PA, AP, AM, RR, AC, RO, R$ 36,00 e R$ 3,60.
- Caixas estimadas (C × L × A em cm, peso real): ukulele soprano ou concert 65 × 26 × 12, 1,5 kg; ukulele tenor ou barítono 80 × 30 × 13, 2 kg; violão 110 × 45 × 16, 5 kg; guitarra 112 × 42 × 14, 6,5 kg; baixo elétrico 128 × 42 × 14, 7,5 kg; teclado 61 teclas 110 × 42 × 20, 12 kg.
- Grande porte do manual (baterias acústicas, pianos digitais, teclados de 88 teclas ou stage e contrabaixos acústicos): cotação individual, sem valor. Baixos elétricos seguem a fórmula.
- Produto sem caixa definida: cotação individual, nunca valor inventado.
- Exemplos obrigatórios em teste: Dourados, violão, 14 kg, PAC R$ 55,59 e SEDEX R$ 82,23; São Paulo, guitarra, 11 kg, R$ 62,19 e R$ 92,79; Recife, teclado 61, 16 kg, R$ 92,19 e R$ 140,79; Manaus, ukulele tenor, 6 kg, R$ 54,00 e R$ 86,40.
- Prazos só do manual: PAC 5 a 12 dias úteis, SEDEX 2 a 5. Jadlog fica como modalidade, sem preço.

**Site.** Fora de Campo Grande, o resumo mostra "Frete estimado (simulação)" com o PAC, que entra no total e nas parcelas, e o SEDEX como informação. O total passa a "Total estimado". Pedido grava o frete estimado, e a confirmação mantém os mesmos rótulos. Cotação individual ou serviço de CEP fora do ar sem cidade localizada: "Total dos produtos" no checkout e na confirmação, sem valor inventado.

**Lia.** Aceita CEP na mensagem. Com produto e CEP, informa PAC e SEDEX com o rótulo de simulação, usando `estimar_frete`, e pede o que faltar. Só com cidade e valor, sem produto, segue dizendo que depende de cotação e explica que produto e CEP permitem a estimativa. Nunca promete tarifa nem prazo de transportadora.

**Resumo do checkout.** Uma linha só: "Frete: Grátis", "Frete: R$ 35,00", "Frete estimado (simulação): R$ X", "Frete: Informe o CEP". A região fica apenas em "Entrega em:". Pendência só em erro. O texto sobre o CEP fica só uma vez. `carrinho.html` passa a dizer "do CEP".

**Rodapé compacto.** Pedido do Rodrigo, seguindo o modelo enviado: uma faixa baixa, com o nome da loja à esquerda e os links em linha única à direita (Catálogo, Perguntas frequentes, Políticas, Rastrear pedido, Privacidade e cookies, Créditos das imagens), sem as colunas e sem os títulos "Comprar" e "Informações". Sem espaço vazio abaixo dos links. Altura de até 96 px em 1280 px. No celular, os links quebram em poucas linhas, com alvos de toque adequados e sem rolagem horizontal. Segue sem dados de contato.

**Endereço e horário: decisão final do Rodrigo.** Prevalece sobre o que estiver diferente nas seções anteriores, inclusive sobre a altura do rodapé compacto e o endereço na faixa.
- O rodapé ganha a parte "Onde estamos", com o endereço completo, e "Horário de funcionamento", com os dados do manual. Telefone, e-mail e WhatsApp seguem fora do rodapé. Ele continua compacto: até 160 px em 1280 px, com nome e endereço, horário e links, sem espaço vazio.
- O endereço sai da faixa e dos cards de `/fale-conosco`. O bloco de telefone da faixa e os cards de WhatsApp e Telefone mostram o horário de atendimento, que é o mesmo da loja.
- O card à direita em `/fale-conosco` passa a "Horário de atendimento", informando que WhatsApp e ligações seguem o horário da loja, e mantém o bloco de rastreio.
- A página offline mantém o endereço, porque não tem rodapé.

**Lia: ajustes da conversa real do Rodrigo em 01/11/2026.**
- Uma pergunta por resposta: se a resposta já termina com pergunta, o convite para retomar o assunto anterior fica para o próximo turno em que não houver outra pergunta.
- Sem convite para retomar quando o assunto anterior não recebeu nenhum dado do cliente, como pedir o pedido e mudar de assunto logo em seguida.
- Depois de informar preço de um produto, a resposta oferece um próximo passo curto, com pergunta de sim ou não sobre parcelamento. "Sim" mostra as parcelas do produto em foco.

**Lia direciona e leva ao carrinho.** Pedido do Rodrigo. Hoje "quero comprar o Yamaha C40" só informa o preço.

- `Resposta` ganha uma lista `links`, gerada só por código a partir do resultado das ferramentas, com lista fechada de rotas internas. O modelo nunca escreve nem escolhe link. O texto da resposta não muda por causa disso, e o terminal mostra o endereço como texto. Máximo de 2 por resposta.
- Destinos: produto, `/produto/{id}`; lista de produtos, `/catalogo` com a categoria; pedido, `/rastreio`; política, `/politicas`; dúvida geral, `/perguntas-frequentes`; contato, `/fale-conosco`.
- Compra: com intenção de comprar e produto identificado e disponível, a Lia informa o preço e mostra o botão "Adicionar ao carrinho", que faz POST na rota existente e leva a `/carrinho` com o produto selecionado. A Lia não coloca nada no carrinho sozinha e nunca diz que adicionou antes do clique.
- Sem produto: pergunta qual, ou lista a categoria. Com modelos parecidos, a escolha numerada continua a compra. Produto indisponível, ou com promoção em conferência: sem botão de carrinho, só o link do produto.
- O botão "Quero comprar com a Lia" da página do produto segue o mesmo fluxo, preenchendo o campo sem enviar.
- A conversa salva no navegador mantém os links funcionando depois de mudar de página.

**Lia aquece o lead.** Objetivo pedido pelo Rodrigo: além de responder, a Lia conduz o interesse até a compra, como vendedora consultiva e sem pressão. Implementado por regras, com fatos vindos só das ferramentas.

- Qualificação: em busca ampla sem filtro ("quero uma guitarra"), mostra a lista e faz uma pergunta curta sobre nível, uso ou orçamento. A resposta do cliente refina a busca. No máximo uma pergunta por resposta e uma rodada de qualificação por assunto.
- Recomendação: depois de saber a faixa ou o nível, destaca uma opção com motivo verificável no dado: cabe no orçamento, está em promoção, é a mais barata, ou categoria indicada no próprio catálogo. Nunca "mais vendido", "melhor" ou opinião sem dado.
- Valor: em produto de interesse, cita a condição real que ajuda, uma por vez: promoção ativa, PIX, parcelas sem juros que atendam à parcela mínima, ou frete grátis em Campo Grande quando se aplicar.
- Objeção: "tá caro" oferece opção mais barata da categoria, promoção ativa ou parcelamento, sem desconto inventado. "Vou pensar" responde com respeito, envia o link do produto e não insiste.
- Próximo passo: resposta sobre produto termina com um passo claro, ligado aos links e ao botão de carrinho.
- Limites: sem urgência ou escassez falsa ("últimas unidades", "só hoje"), sem pedir telefone ou e-mail para vender, sem abrir chamado sem consentimento. Cliente frustrado ou irritado não recebe oferta. Recusa, escopo, reclamação, pedido e devolução não recebem oferta. Uma oferta recusada não se repete no assunto.
- Trace registra a etapa (`interesse`, `qualificado`, `pronto`), sem texto do cliente.

**Auditoria: corrigir.**
1. POST sem cookie válido não emite cookie novo, e as ações POST conferem `Origin`.
2. Falhas de rastreio contam por pedido e por IP, com janela de tempo, no site e na Lia.
3. Páginas próprias para 404, 405, 422 e 500, em português.
4. Bloqueio do rastreio com mensagem própria, indicando quando libera e oferecendo atendimento, sem revelar se o pedido existe.
5. Fale Conosco redireciona após gravar, sem duplicar ao recarregar.
6. Entradas numéricas aceitam só `[0-9]` com limite de tamanho, sem erro 500.
7. Filtro de preço entende `2.000` e `1.000,00`, e recusa negativo com texto próprio.
8. Políticas mostram tabelas reais e não publicam instrução interna à equipe. Se isso exigir alterar o texto do manual, pare e relate.
9. Aviso "Imagem ilustrativa" nas fotos do produto.
10. Sai "ponto em aberto" das Perguntas frequentes.
11. Filtro lista só categorias com produto.
12. Busca sem resultado repete o termo e oferece caminhos, com tratamento de termo sem letras.
13. Carrinho mostra subtotal por item e total de produtos.
14. Abertura da home sem "condição de pagamento à vista".
15. Perguntas frequentes orientam também o pedido feito no site.
16. Lia: validador barra `null`, recusas não passam pela redação, frases do modelo não repetem nem contradizem o bloco factual, "e em 12x" logo após uma lista ambígua pede o produto em uma frase, e "entrega em Recife" não repete a informação.
17. Português: "Adicionar ao carrinho", "Finalizar pedido" e "Conversar com a Lia"; horários em "Seg. a sex., das 9h às 18h"; um só rótulo de horário; site em "nós" e Lia em "eu"; ajustes de regência; "do Empório da Música" no texto escrito pelo site, com o texto do manual intacto.
18. "Para começar" passa a "Menores preços por categoria".

**Não corrigir, e declarar como limitação no README:** marca divergente em sete produtos (os CSV ficam intactos), cabeçalhos de segurança, redirecionamento pelo cabeçalho Host, `/saude` com o nome do modelo, segredo e cookie seguro na publicação, e os demais achados baixos.

## Identidade "Palco e madeira" (etapa 9)

Escolha do Rodrigo em 01/11/2026 (opção A), depois de comparar a home com Constelação, Teclacenter, Mercadão da Música, 4 Music e Fender. Prevalece sobre a identidade "balcão" e a composição "Loja acolhedora" no visual; conteúdo, regras e fluxos não mudam.

- Paleta em tokens no `:root`: palco (quase preto com tom de madeira) para topo, abertura e rodapé; creme para áreas de leitura; amarelo-ipê como única cor de destaque (botões principais, preço em destaque, foco); verde só para "disponível". Todo par de texto passa AA, verificado pelo teste de contraste existente, que deve ser atualizado para os novos tokens.
- **Só design, mesma arquitetura.** Decisão do Rodrigo: mantêm-se páginas, seções, ordem, carrosséis, menus, componentes, rotas, textos e comportamento. Nada de seção ou componente novo; muda só a camada visual (CSS, tokens, tamanhos, pesos, fundos e tratamento das imagens existentes). Mudança mínima de marcação só quando o CSS sozinho não alcança o visual, sem alterar conteúdo nem seletores usados pelos testes.
- Topo escuro com logotipo maior; o menu de categorias segue como está, restilizado.
- Abertura no mesmo bloco atual, restilizada: fundo palco, foto maior e de ponta a ponta dentro do bloco, título grande em branco, botão ipê.
- Tipografia: títulos mais pesados, preço com mais peso; manter fontes locais.
- Cards e carrosséis: mesma estrutura, foto protagonista, sem bolinha decorativa.
- Lia, faixa de contato, rodapé, checkout e demais páginas seguem a nova paleta.
- Sem degradê roxo, vidro, emojis ou ícones em excesso; sem cookie banner.
- Aceite: capturas em 1280 e 390 px da home, catálogo, produto, checkout e /fale-conosco em `docs/capturas`; sem rolagem horizontal; contraste AA; e2e verdes.

## Testes obrigatórios

Conversa longa falha se um fato ou aviso reaparecer sem pedido, ou se a saudação surgir duas vezes. Teste separado confirma que, ao perguntar de novo, o cliente recebe o fato.

Cinco estados de cada ferramenta, cálculos com valor esperado (Crafter HT-100 por PIX: 2399,00, 18%, 1967,18; Takamine GD20 sem promoção; Shelby SN-100 em 6x `requer_confirmacao`), idempotência, negado unificado, trace sem PII, varredura de literais de loja em `.py`, teste que altera o YAML e muda a resposta, e conversa completa de devolução do pedido 4: pergunta pedido, pergunta canal, data e estado, propõe registro, confirma protocolo.
