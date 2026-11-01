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
