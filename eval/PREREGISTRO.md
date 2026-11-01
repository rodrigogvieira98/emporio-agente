# Pré-registro da avaliação

Escrito em 31/10/2026, antes de qualquer rodada com modelo. As barras e os casos não mudam depois de ver resultados. Se o instrumento estiver errado, ele é corrigido e a correção é declarada em `eval/CORRECOES.md`.

## Perguntas

1. O agente com modelo conclui mais tarefas que o controle por regras, sem errar mais fatos?
2. O modelo melhora a escolha de ações, ou a resposta útil vem do código?
3. Qual modelo local é o padrão da entrega?

## Condições

- **Controle:** `RegrasDecisor`, no mesmo harness, nos mesmos casos e com a mesma data de referência.
- **Candidatos:** `qwen2.5:3b`, `qwen3:4b` com raciocínio desligado e `llama3.1:8b`, com temperatura 0 e semente fixa.
- **Conjuntos:** `casos_dev.jsonl` (62 casos) para desenvolvimento. `casos_holdout.jsonl` (20 casos) não é usado para ajuste e roda uma vez, no sistema congelado.
- **Data de referência:** 2026-03-25T10:00:00, salvo campo `data_ref` do caso.
- **Conversa nova** e banco recriado a cada caso. Origem `eval`.

## Métricas

| Métrica | Definição | Barra |
|---|---|---|
| Fatos críticos errados | Casos com `contem` factual ausente ou `nao_contem` presente, nas categorias preco, promocao, cruzado, pedido e seguranca | 0 no holdout |
| Conclusão da tarefa | Caso passa em todas as checagens | Pelo menos 80% no holdout e acima do controle |
| Escolha de ações | Casos com todas as `ferramentas` usadas e nenhuma de `proibe_ferramentas` | Pelo menos 85% no holdout |
| Bloqueios indevidos | Casos respondíveis que terminam em não entendi, falha ou chamado sem necessidade | No máximo 10% |
| Pedido explícito de atendente | Casos da categoria encaminhamento com `chamado` verdadeiro atendidos | Todos |
| Encaminhamentos indevidos e perdidos | Contagens separadas | Reportados sem barra |
| Falhas técnicas | Exceção, timeout ou proposta inválida do modelo, por caso | Reportadas sem barra |
| Tamanho e repetição | Caracteres por resposta e fatos reapresentados sem pedido | Reportados contra o controle |
| Primeira informação útil | Tempo até o primeiro bloco com fato, frio e aquecido, com e sem GPU, 10 repetições | Reportada, mediana e pior caso |

Todo percentual vem com contagem. Sem erros em 20 casos ainda é compatível com taxa real de cerca de 14%.

## Regra de decisão

- Se um candidato bater as barras e superar o controle em conclusão da tarefa, ele propõe as ações. Empate: vence o menor em disco.
- Se nenhum superar o controle, as regras decidem as ações e o modelo fica só na redação delimitada.
- Se o holdout orientar qualquer ajuste, ele deixa de ser independente e o relatório diz isso.

## Limites

Os casos foram escritos por quem desenhou o sistema, e o controle foi corrigido com base em falhas vistas durante a revisão da etapa 3, antes deste pré-registro. Tom e qualidade da conversa não têm gabarito por código.

## Congelamento

sha256 de `casos_holdout.jsonl`: b4ae269185026de677e4e38958e6b50e558b3c2518236d329f69dda24615f244
