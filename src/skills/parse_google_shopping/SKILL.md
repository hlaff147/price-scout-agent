---
name: parse_google_shopping
description: Extrai ofertas do carrossel de Sponsored Products e do Google Shopping (udm=28), consolidando múltiplas lojas (Amazon, Mercado Livre, Inovivo, etc.) em uma única fonte.
---

# Skill: parse_google_shopping

O Google Shopping atua como um meta-agregador de ofertas de e-commerce.
Esta skill é responsável por:
1. Extrair os cards de produtos patrocinados (Product Listing Ads - PLA) da SERP e do Google Shopping.
2. Capturar o preço promocional atual, preço original (quando houver tag SALE/riscado) e a loja de origem (ex: Amazon.com.br, Mercado Livre, Inovivo).
3. Aplicar filtro estrito de palavras-chave (`matches_keywords`) para descartar produtos sugeridos no mesmo carrossel que sejam de outras marcas ou modelos (ex: Galaxy Buds3 ou capinhas).
4. Selecionar o item mais vantajoso com link direto de compra.
