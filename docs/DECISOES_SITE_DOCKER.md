# Decisões de arquitetura: site e Docker

Cada decisão diz o que foi escolhido, por que, e por que não a alternativa. Complementa o DOC de decisões do projeto (decisões 1 a 22) e a seção "Site mínimo e Docker" de `docs/SPEC.md`.

## Agente no site

| # | Decisão | Por que | Por que não a alternativa |
|---|---|---|---|
| S1 | As regras decidem as ações, e o modelo local só redige o texto curto (`EMPORIO_DECISOR=regras`) | Resultado pré-registrado no dev (62 casos): controle 49/62 com 4/31 fatos críticos errados, `qwen3:4b` 40/62 com 11/31, `qwen2.5:3b` 37/62 com 10/31. A regra escrita antes de medir manda as regras decidirem se nenhum modelo superar o controle | Deixar o modelo decidir as ações conclui menos tarefas e erra mais preço, prazo e protocolo. Usar uma API paga fere a restrição de rodar tudo localmente. `llama3.1:8b` ainda em medição; se superar as barras, a decisão é revista |
| S2 | Sem Ollama, o chat responde só com os blocos das regras e registra a falha no trace | O atendimento não para porque o modelo caiu, e a falha fica visível, não silenciosa | Mostrar erro ao cliente deixa a loja sem atendimento. Esconder a falha impede de saber que o modelo está fora |
| S3 | Um agente por processo, criado na subida | O agente guarda o estado no banco, não na memória; criar um por requisição só repete a carga | Um agente por usuário em memória perde a conversa quando o processo reinicia |

## Site

| # | Decisão | Por que | Por que não a alternativa |
|---|---|---|---|
| S4 | FastAPI | Mesmo Python e mesmos modelos Pydantic das ferramentas, validação de entrada pronta, `TestClient` para testar rotas sem servidor | Flask exige montar validação à parte. Django traz ORM, admin e autenticação que o projeto não usa e duplicaria o acesso ao banco |
| S5 | Páginas no servidor com Jinja2 e HTMX | Uma linguagem só, nenhum passo de build, o fragmento do chat volta pronto do servidor | React ou Vue exigem Node, build e uma API JSON separada para um site de cinco páginas. O prazo não paga essa infraestrutura |
| S6 | HTMX servido localmente em `static/`, com versão fixa | O site funciona offline e na avaliação sem depender de CDN externo | CDN cai, muda ou é bloqueado na rede do avaliador |
| S7 | O site lê tudo pelas mesmas ferramentas do agente, sem SQL nas rotas | Preço, promoção e situação de venda mostrados no site e ditos pela Lia vêm da mesma função, então não divergem | Consultas próprias no site criariam uma segunda regra de preço, e a primeira divergência seria um cliente vendo um valor na página e outro no chat |
| S8 | Produto esgotado ou descontinuado aparece marcado e sem botão de compra | O dado do sistema manda; o site não promete o que não há | Esconder o produto confunde quem chega por busca externa ou pelo chat |
| S9 | Rastreio com número do pedido e final do telefone, com a mesma resposta negada para pedido inexistente, final errado e limite de tentativas | Não revela se um pedido existe e reaproveita a identificação simulada já testada | Login completo está fora do escopo. Mensagens diferentes permitiriam descobrir pedidos por tentativa |
| S10 | Sessão por cookie assinado com um identificador aleatório, sem dado pessoal | Liga a conversa e o limite de tentativas ao navegador sem guardar PII | Guardar a conversa no `localStorage` deixa o estado fora do servidor e permite adulteração. Cookie com dados do cliente expõe PII |
| S11 | Texto do agente sempre escapado | O texto pode repetir o que o cliente digitou | Inserir HTML cru abre injeção de script no próprio chat |

## Docker

| # | Decisão | Por que | Por que não a alternativa |
|---|---|---|---|
| S12 | Docker Compose com dois serviços, `app` e `ollama` | Um comando sobe tudo, igual em qualquer máquina, e cada serviço reinicia sem derrubar o outro | Um contêiner único com app e Ollama mistura ciclos de vida e deixa a imagem enorme. Kubernetes é desproporcional para uma demonstração local |
| S13 | `python:3.12-slim`, usuário sem root | Imagem pequena e com wheels prontas para todas as dependências | `alpine` usa musl e costuma compilar dependências na instalação. Rodar como root amplia o estrago de uma falha |
| S14 | Volume nomeado para os modelos e um serviço de uma vez que baixa o modelo padrão | O modelo de vários GB é baixado uma vez e sobrevive a rebuild. A app sobe sem esperar o download | Embutir o modelo na imagem a deixa com vários GB e refaz o download a cada build |
| S15 | Sem GPU por padrão, GPU por arquivo de override | Funciona em qualquer máquina do avaliador; quem tem GPU ganha velocidade com um parâmetro | Exigir GPU impede a demonstração na maioria dos notebooks |
| S16 | Banco SQLite criado na subida a partir dos CSV | Os dados originais ficam imutáveis e o banco sempre corresponde a eles | Versionar o banco no repositório duplica a fonte e deixa a carga sem teste |
| S17 | Healthcheck em `/saude`, informando banco e modelo | O Compose e o avaliador veem se a app está pronta e se o modelo responde | Sem ele, a falha do modelo só aparece quando alguém conversa |

## Testes

| # | Decisão | Por que | Por que não a alternativa |
|---|---|---|---|
| S18 | Rotas testadas com `TestClient` e um teste Playwright de ponta a ponta, rodado à parte | `TestClient` é rápido e roda sempre; o Playwright confirma o que o cliente vê clicando, onde os defeitos caros costumam escapar | Só testes de API deixam passar defeitos de tela. Só Playwright torna a suíte lenta e dependente de navegador instalado. Selenium exige driver separado e é mais instável |
