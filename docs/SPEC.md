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

CLI `python -m emporio.cli --origem demo`.

## Concisão e redundância

Complemento aprovado pelo Rodrigo em 31/10/2026, aplicado na etapa 5, quando o modelo entra. Não altera as etapas 1 a 3.

- O estado guarda `ja_informados`: chaves dos fatos e avisos já entregues na conversa, por entidade, atributo e valor.
- Fato ou aviso já entregue não reaparece sem pedido do cliente. Exceções: o valor mudou, ou o cliente perguntou de novo.
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

## Testes obrigatórios

Conversa longa falha se um fato ou aviso reaparecer sem pedido, ou se a saudação surgir duas vezes. Teste separado confirma que, ao perguntar de novo, o cliente recebe o fato.

Cinco estados de cada ferramenta, cálculos com valor esperado (Crafter HT-100 por PIX: 2399,00, 18%, 1967,18; Takamine GD20 sem promoção; Shelby SN-100 em 6x `requer_confirmacao`), idempotência, negado unificado, trace sem PII, varredura de literais de loja em `.py`, teste que altera o YAML e muda a resposta, e conversa completa de devolução do pedido 4: pergunta pedido, pergunta canal, data e estado, propõe registro, confirma protocolo.
