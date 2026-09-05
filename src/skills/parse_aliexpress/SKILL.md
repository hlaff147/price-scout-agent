---
name: parse_aliexpress
description: Regras de extração de preços, títulos, cupons e disponibilidade no AliExpress.
---

# Skill: parse_aliexpress

Extrai ofertas de produtos e listagens de busca no AliExpress (em reais BRL).

## Estrutura de Seletores
- **Título**: `h1[data-pl="product-title"]`, `h1.product-title-text`, `div.multi--title--`
- **Preço Atual**: `span.product-price-value`, `div.product-price-current`, `div.multi--price-sale--`
- **Preço Original (Riscado)**: `span.product-price-del`, `div.product-price-original`, `div.multi--price-original--`
- **Disponibilidade**: verificar texto de estoque e status do botão de compra
