---
name: parse_kabum
description: Regras de extração de preços, títulos, disponibilidade e cupons do KaBuM!.
---

# Skill: parse_kabum

Extrai informações de ofertas do KaBuM! a partir do HTML ou do JSON-LD das páginas de produto e busca.

## Estrutura de Seletores
- **Título**: `h1`, `span.nameCard`
- **Preço Atual (À vista)**: `h4.finalPrice`, `span.priceCard`
- **Preço Original (De)**: `span.oldPrice`, `span.oldPriceCard`
- **Disponibilidade**: verificar texto de indisponibilidade ou botão de compra ativo
