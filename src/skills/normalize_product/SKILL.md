---
name: normalize_product
description: Padroniza preços, títulos e variantes de produtos coletados em múltiplos marketplaces.
---

# Skill: normalize_product

Esta skill é responsável por:
1. Converter strings monetárias brasileiras (ex: `R$ 1.299,90` ou `R$850`) em `float` padronizado.
2. Normalizar textos, removendo acentuações, espaços duplicados e ruídos de caracteres.
3. Validar se o produto coletado confere com as palavras-chave cadastradas para evitar falsos positivos de acessórios (como capas ou pontas de fone).
