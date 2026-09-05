---
name: detect_fake_discount
description: Heurística para detectar preços "de" inflados artificialmente e calcular o desconto real com base em dados históricos.
---

# Skill: detect_fake_discount

Muitos e-commerces inflam o preço "original" (riscado) para exibir porcentagens chamativas de desconto (ex: "50% OFF").
Esta skill:
1. Compara o preço original anunciado com a média histórica e com o preço máximo definido pelo usuário.
2. Calcula o **desconto real** em relação à média de preços observada no histórico do PromoRadar, e não em relação ao rótulo anunciado pela loja.
3. Classifica se o anúncio apresenta indícios de "falsa promoção" (`fake discount`).
