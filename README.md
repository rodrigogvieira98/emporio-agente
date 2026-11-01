# Agente da Empório da Música

Lia, assistente virtual da Empório da Música (loja fictícia de instrumentos em Campo Grande/MS). Ela responde sobre catálogo, preços, condições de pagamento, status de pedidos e políticas da loja, registra reclamações e encaminha para a equipe. Junto vem um site da loja (catálogo, produto, políticas, rastreio) com a Lia em todas as páginas, instalável como PWA.

Aviso do repositório: a loja é fictícia e os pedidos não são reais. Nenhum valor é cobrado e nada é entregue. O site não diz isso ao cliente, por decisão de produto. Os canais de contato (WhatsApp `wa.me`, `tel:` e `mailto:`) têm link padrão gerado dos números e do e-mail do manual da loja fictícia, que não são contatos reais; `EMPORIO_WHATSAPP_URL`, `EMPORIO_TELEFONE_LINK` e `EMPORIO_EMAIL_LINK` substituem os padrões; o Fale Conosco só envia e-mail com `EMPORIO_SMTP_HOST` e `EMPORIO_SMTP_PARA` configurados. Fotos: ver `docs/CREDITOS_IMAGENS.md` (regeneram com `python -m emporio.web.gerar_fotos PASTA`, com Pillow de `requirements-e2e.txt`).

## Executar com Docker

```
docker compose up -d --build
```

Site em http://localhost:8000 e estado em http://localhost:8000/saude. O modelo padrão `qwen2.5:3b` é baixado na primeira subida (cerca de 2 GB); enquanto isso, a Lia já responde só com as regras. Troque o modelo com `EMPORIO_MODELO`.
Com GPU NVIDIA: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`.
Parar: `docker compose down`.

## Executar sem Docker

Requer Python 3.11 ou superior.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set PYTHONPATH=src
.venv\Scripts\python -m emporio.dados.carga
.venv\Scripts\python -m uvicorn emporio.web.app:app --port 8000
```

No Linux ou macOS, use `.venv/bin/` e `export PYTHONPATH=src`.
Modelo local (opcional): instale o [Ollama](https://ollama.com), rode `ollama pull qwen2.5:3b` e defina `EMPORIO_MODELO=qwen2.5:3b` antes de subir. Sem modelo, a Lia funciona só com as regras.
Conversa pelo terminal: `.venv\Scripts\python -m emporio.cli --origem demo`.
O PWA só pode ser instalado em `localhost` ou em HTTPS.
`EMPORIO_DATA_REFERENCIA=2026-03-25T10:00:00` fixa a data e a hora da loja, útil porque os pedidos dos dados são de 2025 e 2026.

## Testes e avaliação

```
python -m pytest
pip install -r requirements-e2e.txt && playwright install chromium
python -m pytest -m e2e
python eval/rodar.py --conjunto dev --rotulo meu_teste
```

## Decisões técnicas

- **Abordagem: agente com ferramentas determinísticas (function calling), sem RAG.** Catálogo, preços e pedidos são dados estruturados, consultados exatamente no SQLite. O manual da loja virou um YAML versionado com regras estruturadas e ambiguidades registradas. A cada turno, o agente percebe a intenção, decide uma ação, o código valida e executa a ferramenta e interpreta o resultado (até 3 passos). Busca por semelhança traria o produto parecido em vez do certo.
- **Modelo: `qwen2.5:3b` local via Ollama, só para redigir até 2 frases curtas.** Medimos três modelos locais decidindo as ações contra um controle só com regras, com critérios escritos antes de medir (`eval/PREREGISTRO.md`). Nenhum superou o controle, então as regras decidem e o modelo só redige; preço, prazo e protocolo são sempre escritos pelo código. Local e gratuito, roda sem GPU.
- **Prompt:** curto e com contrato de saída. A redação é validada por código antes de aparecer (sem números, sem produto fora do resultado, sem promessa de ação não executada, sem repetir o que o bloco factual já diz).
- **Interface:** site FastAPI com Jinja2 e HTMX, sem build de front-end, PWA e terminal. O site lê as mesmas ferramentas da Lia, então página e chat nunca divergem.
- **Persistência:** SQLite guarda estado da conversa, mensagens, chamados e tentativas de identificação. Um trace JSONL por turno registra ferramentas, estados e latência, sem dado pessoal.
- **Tratamento de dados:** os CSV originais ficam intactos. Inconsistências (totais divergentes, PIX sem desconto, parcelas abaixo do mínimo, e-mail duplicado) são mostradas como gravadas e cobertas por teste, nunca corrigidas em silêncio.

## Resultados medidos (62 casos de desenvolvimento)

| Configuração | Tarefas concluídas | Fatos críticos errados |
|---|---|---|
| Regras decidem (entregue) | 50/62 | 4/31 |
| `qwen3:4b` decide | 40/62 | 11/31 |
| `qwen2.5:3b` decide | 39/62 | 10/31 |
| `llama3.1:8b` decide | 38/62 | 10/31 |

Os modelos foram medidos sobre o controle de 49/62; o controle melhorou depois com correções vindas de conversas reais. Um conjunto separado de 20 casos (`eval/casos_holdout.jsonl`) roda uma única vez no sistema congelado.

## Exemplos de conversa

Cinco conversas reais em [`exemplos/`](exemplos), geradas pelo próprio agente com `python exemplos/gerar_conversas.py`: catálogo com filtro de preço, informações da loja e pergunta fora do escopo, preço com nome ambíguo e promoção, devolução com consulta ao pedido e às políticas, e reclamação com atendimento humano.

## Limitações e próximos passos

- Identificação do cliente é simulada (número do pedido e final do telefone). Com mais tempo: login real.
- A percepção da intenção é por regras e vocabulário; formulações muito diferentes das previstas podem não ser entendidas. Com mais tempo: medir um classificador maior só para intenção, mantendo as ferramentas.
- O manual tem ambiguidades (parcela mínima, frete de exatamente R$ 500, prazo da troca por preferência, 30 x 90 dias). A Lia mostra as duas leituras e encaminha para a equipe em vez de decidir.
- Sem compra real nem pagamento.
- O frete estimado fora de Campo Grande (PAC e SEDEX) é uma hipótese de simulação: as tabelas, caixas e pesos são suposições do protótipo e os valores não foram conferidos nos Correios, então não são tarifa nem prazo de transportadora.
- Resposta com o modelo em CPU leva dezenas de segundos na primeira chamada; a redação livre vem desligada por padrão (`EMPORIO_REDACAO=1` liga). Com modelo e decisor de regras, o modelo também serve de reserva de intenção quando as regras não entendem a mensagem (lista fechada, sem chamado nem consulta de pedido); `EMPORIO_RESERVA=0` desliga.
- PWA testado só em Chromium emulando celular.

## Uso de assistentes de código

Usei o Claude Code com papéis separados. Um modelo mais forte (Claude Opus) explorou os dados, escreveu a especificação e revisou cada entrega. Um modelo mais econômico (Claude Sonnet) implementou cada etapa a partir da especificação aprovada, com permissões de arquivo delimitadas. Eu aprovei cada especificação antes da implementação e cada mudança de teste existente. Os critérios de avaliação foram escritos antes de medir os modelos, e uma entrega foi reprovada e refeita na revisão. As conversas de exemplo foram geradas rodando o agente, e os defeitos que elas mostraram viraram testes antes de serem corrigidos.
