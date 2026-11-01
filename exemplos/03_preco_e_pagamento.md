# Preço, nome ambíguo, promoção e parcelamento

Gerada por `exemplos/gerar_conversas.py`. Data de referência 2026-03-25T10:00:00, decisor `regras`, modelo de redação: qwen2.5:3b.

**Cliente:** Quanto custa um Takamine?

**Lia:** Achei mais de um modelo parecido:  
1) Takamine GD20 Dreadnought Natural  
2) Takamine GC5CE Elétrico Nylon Natural  
3) Takamine GN51CE Elétrico Aço Natural  
4) Takamine GC1CE Elétrico Nylon Natural  
Qual deles? Pode responder com o número.

<sub>Ferramentas: ver_produto</sub>

**Cliente:** Quanto custa o Takamine GD20?

**Lia:** Takamine GD20 Dreadnought Natural: preço de tabela R$ 2.199,00. No PIX (5% de desconto) fica R$ 2.089,05.

<sub>Ferramentas: ver_produto, calcular_condicoes</sub>

**Cliente:** E o Crafter HT-100 no pix?

**Lia:** Crafter HT-100 Folk Aço Natural: preço de tabela R$ 2.399,00, promoção de 18% e preço final R$ 1.967,18. O desconto do PIX não soma com promoção.

<sub>Ferramentas: ver_produto, calcular_condicoes</sub>

**Cliente:** Parcela o Shelby SN-100 em 6x?

**Lia:** Shelby SN-100 Folk Aço Preto: preço de tabela R$ 549,00. No crédito em 6x, cada parcela fica em R$ 91,50. O manual tem duas leituras para a parcela mínima (R$ 100,00 na tabela e R$ 80,00 na faixa de 6x), então a equipe precisa confirmar. Quer que eu registre a dúvida para eles? Responda sim ou não.

<sub>Ferramentas: ver_produto, calcular_condicoes</sub>
