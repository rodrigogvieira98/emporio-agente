# Pré-registro: modelo como reserva de intenção

Escrito em 01/11/2026, antes de implementar e antes de qualquer rodada. A barra e `casos_frescos.jsonl` não mudam depois de ver resultados. Correção de instrumento vai para `eval/CORRECOES.md`. Este registro não altera `PREREGISTRO.md` nem o holdout.

## Pergunta

Quando as regras não entendem, um modelo local escolhendo uma intenção de uma lista fechada reduz os "não entendi" sem piorar fatos nem criar chamados indevidos?

## Condições

- **A:** Lia com as correções por regras, sem reserva.
- **B:** A com a reserva ligada, no mesmo commit, mesmo modelo de redação (`qwen2.5:3b`), mesma data de referência e banco recriado a cada caso.
- **Conjuntos:** `casos_dev.jsonl`, `casos_variacoes.jsonl`, `casos_conversas.jsonl` (achados da revisão, usados para ajuste) e `casos_frescos.jsonl` (18 casos). Os frescos não servem para ajuste: quem implementa não os lê, e A roda antes de B.

## Barra

A reserva fica ligada somente se B, comparado a A com `eval/comparar.py`, cumprir todos os itens:

1. fatos críticos errados: nenhum aumento em nenhum conjunto;
2. chamados indevidos: nenhum aumento em nenhum conjunto;
3. casos que terminam em não entendi nos frescos: pelo menos 2 a menos;
4. nenhum caso que passava em A falha em B nos frescos;
5. falhas técnicas sem resposta ao cliente: zero;
6. mediana de tempo por caso nos frescos: até 2 vezes a de A.

Se qualquer item falhar, a reserva fica desligada e a entrega é a condição A, com o resultado relatado.

## O que não cobre

Os frescos foram escritos por quem revisou a Lia e são poucos. Eles não substituem o holdout e não medem conversa real com clientes.

## Adendo de 01/11/2026: condição C

Escrito antes de implementar a condição C e antes de qualquer rodada de `casos_frescos.jsonl`.

- **Condição C:** classificador de lista fechada antes das regras, com as regras como validação e fallback, mesmo commit-base de A e B.
- **Barra:** C substitui A ou B somente se cumprir os itens 1, 2, 4 e 5 da barra em relação a A, tiver conclusão nos frescos estritamente maior que a de A e a de B, e mediana de tempo por caso de até 3 vezes a de A.
- Com redação desligada nas três condições, que passa a ser o padrão da entrega.
- Se C não passar, ela não entra na entrega, e o resultado é relatado.

## Adendo de 01/11/2026, 19h15: redação ligada na entrega

Escrito antes de qualquer rodada de `casos_frescos.jsonl` e do holdout. Por decisão do Rodrigo, a entrega usa redação ligada (`EMPORIO_REDACAO=1`). As condições A e B passam a rodar com redação ligada, que é a configuração entregue, e A também sem redação, como controle. A barra não muda. Relatar também a telemetria `redacao_tentada`, `redacao_exibida` e `redacao_descartada` com denominador.
