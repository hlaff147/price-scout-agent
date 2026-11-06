---
name: monitor-black-friday-tracker
description: >-
  Executa o rastreamento incremental de preços dos 13 monitores ergonômicos de 27 polegadas
  para a Black Friday, persiste o histórico no SQLite do PromoRadar e atualiza o painel
  interativo Chart.js (reports/monitores_27_black_friday.html) e o relatório Markdown.
  Use esta skill quando o usuário pedir para buscar/atualizar preços dos monitores 27",
  gerar gráficos evolutivos de Black Friday ou nas execuções agendadas de 6 em 6 horas.
---

# Monitor Black Friday Tracker (27" Ergonômicos)

Procedimento padronizado para coletar preços atuais dos 13 monitores de 27" com ajuste de altura (`src/config/monitors_27.yaml`), acumular séries históricas no SQLite (`data/promoradar.db`) e recompilar o painel interativo unificado (`reports/monitores_27_black_friday.html`).

## Passo a Passo de Execução

1. **Executar o ciclo automatizado de scraping e atualização do painel**:
   ```bash
   /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_monitors_27.py --no-open
   ```

2. **Enriquecimento resiliente via Busca Web (se houver bloqueio anti-bot em algum monitor)**:
   - Verifique na saída do Passo 1 a linha `Sem cotação HTTP direta (...)`.
   - Para os monitores que ficaram sem cotação HTTP direta na rodada (priorizando os modelos QHD Gamer e destaques), consulte preços reais à vista/PIX no varejo brasileiro (Amazon Brasil, KaBuM!, Mercado Livre, Pichau, Terabyteshop, Magalu ou Dell Oficial) usando a ferramenta `search_web`.
   - Para cada preço real confirmado com URL válida de loja brasileira (descartando suportes, fontes ou monitores recondicionados/defeituosos), grave no banco SQLite executando:
     ```bash
     /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_monitors_27.py --no-open --record-price <product_id> <marketplace> <preco_numerico> "<url_da_oferta>" --title "<titulo_do_anuncio>"
     ```
   - Valores aceitos para `<marketplace>`: `amazon`, `kabum`, `mercadolivre`, `pichau`, `terabyte`, `magalu`, `dell`, `google_shopping`.

3. **Validação e Relatório Executivo**:
   - Leia `/Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/monitors_27_history_summary.md` para conferir o consolidado atualizado da rodada.
   - Apresente um resumo objetivo destacando:
     - Monitores que atingiram ou ficaram abaixo do **Preço Alvo Black Friday** (`🎯 ABAIXO DO ALVO`).
     - Menor preço QHD Gamer (144Hz+) e menor preço geral da rodada.
     - Variações relevantes frente às rodadas anteriores.
     - Links clicáveis para [`monitores_27_black_friday.html`](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/monitores_27_black_friday.html) e [`monitors_27_history_summary.md`](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/monitors_27_history_summary.md).
