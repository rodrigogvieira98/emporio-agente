# Resultados

Detalhe das medições resumidas no [README](../README.md#resultados). Critérios em `eval/PREREGISTRO.md` e `eval/PREREGISTRO_RESERVA.md`; correções de instrumento e gabarito em `eval/CORRECOES.md`; arquivos de cada execução em `eval/resultados/`.

## Comparação de modelos decidindo as ações (dev, 62 casos, `num_ctx` 8192, commit 41b8a9f)

| Configuração | Conclusão | Fatos críticos errados |
|---|---|---|
| Regras decidem (controle) | 49/62 | 4/31 |
| `qwen3:4b` decide | 40/62 | 11/31 |
| `qwen2.5:3b` decide | 39/62 | 10/31 |
| `qwen3:8b` decide | 39/62 | 13/31 |
| `llama3.1:8b` decide | 38/62 | 10/31 |

Um segundo experimento, com o modelo classificando a intenção antes das regras, deu 47/62 e 5/31 contra 62/62 e 0/31 das regras no mesmo commit, de 5 a 9 vezes mais lento. Foi descartado.

## Versão final: holdout 2, execução única (commit fafe24c)

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

## Compreensão de frases novas (QA independente)

| Rodada | Conversas / turnos | Turnos corretos | Críticos | Altos |
|---|---|---|---|---|
| QA 2 | 35 / 163 | 30,1% | 4 | 60 |
| QA 3 | 35 / 174 | 33,9% | 0 | 53 |
| QA 4 | 35 / 181 | 35,4% | 1 | 57 |

Conversas inéditas, simuladas por agentes independentes como caixa-preta; a classificação é de um único avaliador por rodada, então a comparação é aproximada. Três rodadas de correção renderam cerca de 5 pontos: as regras chegaram ao limite para linguagem natural. O QA 4 mediu a versão anterior às correções finais de risco, e não medimos de novo.

## Holdout original, execução única (commit e0f35d6)

| Critério pré-registrado | Barra | Entregue | Só regras |
|---|---|---|---|
| Conclusão | ≥ 80% | 18/20 (90%) | 18/20 |
| Fatos críticos errados | 0 | **1/10, reprovado** | 1/10 |
| Escolha de ações | ≥ 85% | 20/20 | 20/20 |
| Bloqueios indevidos | ≤ 10% | 1/20 | 1/20 |
| Pedido de atendente | todos | 1/1 | 1/1 |

Aquela versão reprovou por omitir a forma do reembolso (h12); além disso, não identificou um produto descontinuado (h06). O prazo foi estendido depois dessa execução, e o conjunto não rodou de novo. As causas foram corrigidas e a versão final foi medida pelo holdout 2. O conjunto de 40 casos é maior e mais difícil, então 90% e 75% não são comparáveis diretamente. A medição congelada de 735bb85 e os frescos (controle 16/18, redação 16/18, reserva 17/18) estão em `eval/resultados`; a reserva não passou na barra pré-registrada e ficou desligada, e os frescos viraram desenvolvimento depois de corrigir o caso f02 (`eval/CORRECOES.md`).

## Versão avaliada e verificação da entrega

- Código avaliado no holdout 2: **fafe24c**. Depois dele, por decisão do Rodrigo em 02/11/2026, mudaram: o banner (bolinhas indicadoras e foto de violão sem pessoa), o rodapé (sem Perguntas frequentes) e o tom de quatro respostas da Lia (acolhimento curto em reclamação irritada; todo chamado informa protocolo, prazo de 24 horas úteis e canais; pergunta sobre um dia responde só aquele dia; resumo de devolução em até 4 linhas). Saiu também a frase "um atendente já tem como falar com você", que não era verdadeira num chat anônimo. Os números do holdout 2 valem para fafe24c, e o holdout não rodou de novo; depois das mudanças, dev 62/62, variações 14/14 e conversas 108/108, com zero fatos críticos e zero chamados indevidos.
- Instalação limpa sem Docker e Docker verificados em f12c19f (01/11/2026, 23h46): 1.500 testes passando, site, modelo `qwen3:4b` e Lia respondendo. A versão final com as mudanças acima passou em 1.515 testes unitários e 210 de navegador (02/11/2026, 01h30).
- Docker, no mesmo commit, com `docker compose up -d --build`: site no ar, modelo `qwen3:4b` carregado e Lia respondendo. O download do zero foi verificado antes, em 38b8370, com cerca de 4 minutos, e nesta rodada o modelo já estava no volume.
