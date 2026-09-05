---
name: parse_mercadolivre
description: Regras de extração de preços, títulos, disponibilidade e cupons do Mercado Livre.
---

# Skill: parse_mercadolivre

Extrai informações de ofertas do Mercado Livre a partir do HTML de páginas de produto ou listagens de busca.

## Estrutura de Seletores
- **Título**: `h1.ui-pdp-title`, `h2.ui-search-item__title`, `h2.poly-component__title`
- **Preço Atual**: `span.andes-money-amount.ui-pdp-price__part--medium`, `.andes-money-amount__fraction`
- **Preço Original**: `s.andes-money-amount--previous`, `.ui-pdp-price__original-value`
- **Cupons**: `span.ui-pdp-promotions-pill-label`, `.andes-badge`
- **Disponibilidade**: presença de botão de compra / ausência de texto "Não disponível"
