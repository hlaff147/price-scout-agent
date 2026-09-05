---
name: parse_shopee
description: Regras de extração de preços, títulos, cupons e disponibilidade na Shopee Brasil.
---

# Skill: parse_shopee

Extrai ofertas de produtos e listagens de busca na Shopee Brasil.

## Estrutura de Seletores
- **Título**: `div[data-sqe="name"]`, `div.line-clamp-2`, `h1`
- **Preço Atual**: `span.truncate`, `div[class*="text-shopee-primary"]`, `div[class*="price"]`
- **Preço Original (Riscado)**: `div.line-through`, `span.line-through`
- **Cupons / Frete**: `span[class*="voucher"]`, `div[class*="shipping"]`
- **Disponibilidade**: presença de preço e ausência de tag "Esgotado"
