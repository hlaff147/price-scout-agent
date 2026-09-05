---
name: parse_amazon
description: Regras de extração de preços, títulos, disponibilidade e cupons da Amazon Brasil.
---

# Skill: parse_amazon

Extrai informações de ofertas da Amazon a partir do HTML de páginas de produto ou listagens de busca.

## Estrutura de Seletores
- **Título**: `span#productTitle`, `h2.a-size-mini span`, `h2 a span`
- **Preço Atual**: `span.a-price .a-offscreen`, `span#priceblock_ourprice`, `span#priceblock_dealprice`
- **Preço Original (Lista/De)**: `span.basisPrice .a-offscreen`, `span.a-text-price .a-offscreen`
- **Cupons**: `span.promoPriceBlockMessage`, `label[for*="coupon"]`
- **Disponibilidade**: `div#availability span` ("Em estoque", "Não disponível")
