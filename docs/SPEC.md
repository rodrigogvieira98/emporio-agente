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

CLI `python -m emporio.cli --origem demo`.

## Concisão e redundância

Complemento aprovado pelo Rodrigo em 31/10/2026, aplicado na etapa 5, quando o modelo entra. Não altera as etapas 1 a 3.

- O estado guarda `ja_informados`: chaves dos fatos e avisos já entregues na conversa, por entidade, atributo e valor.
- Fato ou aviso já entregue não reaparece sem pedido do cliente. Exceções: o valor mudou, ou o cliente perguntou de novo.
- Saudação no máximo uma vez por conversa.
- Texto livre do modelo: no máximo 2 frases curtas e no máximo 1 pergunta por turno.
- Antes de exibir, o código remove frase repetida ou quase igual dentro do turno e em relação às respostas anteriores, sem nunca remover bloco factual necessário à resposta atual.
- A avaliação mede tamanho da resposta em caracteres e taxa de repetição, com contagens, contra o controle por regras. A taxa conta fatos e avisos reapresentados sem pedido sobre o total de fatos e avisos exibidos.

## Testes obrigatórios

Conversa longa falha se um fato ou aviso reaparecer sem pedido, ou se a saudação surgir duas vezes. Teste separado confirma que, ao perguntar de novo, o cliente recebe o fato.

Cinco estados de cada ferramenta, cálculos com valor esperado (Crafter HT-100 por PIX: 2399,00, 18%, 1967,18; Takamine GD20 sem promoção; Shelby SN-100 em 6x `requer_confirmacao`), idempotência, negado unificado, trace sem PII, varredura de literais de loja em `.py`, teste que altera o YAML e muda a resposta, e conversa completa de devolução do pedido 4: pergunta pedido, pergunta canal, data e estado, propõe registro, confirma protocolo.
