---
name: celulares
description: >-
  Busca preços ao vivo dos 15 smartphones de 512 GB com melhor custo x benefício na faixa
  de R$ 3.000 (Motorola Edge 50 Ultra, Xiaomi 14T, Galaxy S25+, Galaxy S24 FE, Realme GT 6,
  Edge 60 Pro, Realme 14 Pro+, POCO X8 Pro, POCO X8 Pro Max, POCO F6, Edge 50 Neo, POCO X7 Pro,
  Redmi Note 15 Pro 5G, Galaxy A57 e Jovi V70), incrementa o histórico temporal no SQLite e no
  log de ciclos, recompila o dashboard interativo Chart.js (reports/celulares_512gb_black_friday.html)
  com Índice de Benefício (0-100) e retorno por R$ 1.000 gastos, e apresenta análise comparativa
  de ofertas Black Friday. Use esta skill quando o usuário invocar /celulares ou pedir para
  buscar/atualizar preços e relatórios dos celulares 512 GB.
---

# Skill `/celulares` — Busca Incremental e Dashboard Black Friday (Smartphones 512 GB)

Executa uma rodada completa de coleta de preços dos 15 smartphones de 512 GB (`src/config/smartphones_512.yaml`), grava os novos pontos na série histórica do SQLite (`data/promoradar.db`) e no log de ciclos (`data/smartphones_512_cycles.jsonl`), atualiza os gráficos evolutivos e de Custo × Benefício no painel `Chart.js` (`reports/celulares_512gb_black_friday.html`) e entrega um comparativo executivo por perfil de uso.

## Passo a Passo de Execução

1. **Disparar a coleta ao vivo e atualização incremental do dashboard**:
   Execute o motor de rastreamento:
   ```bash
   /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_smartphones_512.py --no-open
   ```
   - **Nota sobre Sandbox**: Tente primeiro no modo padrão (`BypassSandbox: false`). Caso os logs iniciais indiquem bloqueio de rede do sandbox (`403 Forbidden`), cancele imediatamente a tarefa em background (`manage_task` com `kill`) antes que ela finalize um ciclo vazio e reexecute o mesmo comando com `BypassSandbox: true` mantendo o `toolSummary` idêntico.
   - Se o usuário passar um filtro junto ao comando (ex.: `/celulares xiaomi-14t-512`), ainda assim prefira rodar todos os 15 aparelhos para manter a linha do tempo completa no gráfico e destaque o modelo pedido na análise final.

2. **Enriquecimento resiliente via Busca Web (para modelos sem retorno HTTP direto)**:
   - Confira na saída do Passo 1 a linha `Sem cotação HTTP direta (...)`.
   - Para modelos prioritários sem cotação recente, consulte ofertas reais à vista/PIX da **variante de 512 GB** em varejistas brasileiros (`amazon`, `kabum`, `mercadolivre`, `magalu`, `shopee`) usando `search_web`.
   - **Atenção**: Nunca registre preços de versões de `256 GB`, `128 GB`, aparelhos usados/vitrine ou acessórios (capas/películas). Grave **apenas** preços confirmados de **512 GB** novos com URL válida:
     ```bash
     /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_smartphones_512.py --no-open --record-price <product_id> <marketplace> <preco_numerico> "<url_da_oferta>" --title "<titulo_do_anuncio_com_512GB>"
     ```

3. **Validação e Análise Executiva Comparativa**:
   - Leia [celulares_512gb_summary.md](../../reports/celulares_512gb_summary.md) e confira os alertas emitidos no log da execução.
   - Responda em português (`pt-BR`) apresentando:
     1. **Resumo do Ciclo**: número da rodada, total de cotações acumuladas no SQLite, quantidade de aparelhos abaixo do teto de `` `R$ 3.000` `` e abaixo do alvo de Black Friday (`27/11/2026`).
     2. **Principais Oportunidades e Oscilações**: variações relevantes frente à referência da pesquisa e à rodada anterior.
     3. **Tabela Consolidada dos 15 Smartphones 512 GB**: ordenada por Custo-Benefício (`Pts/R$ 1.000`) ou menor preço atual, destacando `🎯 ABAIXO DO ALVO`, barramento `UFS 4.0` vs `UFS 2.2`, RAM física (`12 GB` / `16 GB` vs `8 GB`) e piso histórico (sempre formatando valores monetários entre crases, como `` `R$ 2.369,00` ``).
     4. **Síntese por Perfil de Prioridade**:
        - *Melhor Escolha Geral & Fotografia Avançada*: `Motorola Edge 50 Ultra` vs `Xiaomi 14T`
        - *Longevidade de Software (7 anos) & Ecossistema*: `Samsung Galaxy S25+` vs `Galaxy S24 FE`
        - *Jogos Pesados & Bateria Extrema (6.000–7.000 mAh)*: `POCO X7 Pro`, `POCO X8 Pro / Max`, `Realme GT 6`
        - *Ergonomia Compacta (171 g) & Economia (< R$ 2.500)*: `Motorola Edge 50 Neo`, `Redmi Note 15 Pro 5G`, `Galaxy A57`
     5. **Links Clicáveis**: [celulares_512gb_black_friday.html](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/celulares_512gb_black_friday.html) e [celulares_512gb_summary.md](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/celulares_512gb_summary.md).
