---
name: monitores
description: >-
  Busca preços ao vivo dos 13 monitores ergonômicos de 27 polegadas com ajuste de altura,
  incrementa o histórico temporal no SQLite e no log de ciclos, recompila o dashboard
  interativo Chart.js (reports/monitores_27_black_friday.html) e apresenta análise
  comparativa de ofertas Black Friday. Use esta skill quando o usuário invocar /monitores
  ou pedir para atualizar a busca, os gráficos e a análise de preços dos monitores.
---

# Skill `/monitores` — Busca Incremental e Dashboard Black Friday (27" Ergonômicos)

Executa uma nova rodada completa de coleta de preços dos 13 monitores de 27" com ajuste de altura (`src/config/monitors_27.yaml`), grava os novos pontos na série histórica do SQLite (`data/promoradar.db`) e no log de ciclos (`data/monitors_27_cycles.jsonl`), atualiza os gráficos evolutivos do painel único `Chart.js` (`reports/monitores_27_black_friday.html`) e entrega um comparativo executivo da rodada.

## Passo a Passo de Execução

1. **Disparar a coleta ao vivo e atualização incremental do dashboard**:
   Execute o motor de rastreamento:
   ```bash
   /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_monitors_27.py --no-open
   ```
   - **Nota sobre Sandbox**: Tente primeiro no modo padrão (`BypassSandbox: false`). Caso os logs iniciais indiquem bloqueio de rede do sandbox (`403 Forbidden`), cancele imediatamente a tarefa em background (`manage_task` com `kill`) antes que ela finalize um ciclo vazio e reexecute o mesmo comando com `BypassSandbox: true` mantendo o `toolSummary` idêntico.
   - Se o usuário passar um filtro junto ao comando (ex.: `/monitores aoc-q27g4f`), ainda assim prefira rodar os 13 monitores para manter a linha do tempo completa no gráfico e destaque o modelo pedido na análise final.

2. **Enriquecimento resiliente via Busca Web (opcional para modelos sem retorno HTTP direto)**:
   - Confira na saída do Passo 1 a linha `Sem cotação HTTP direta (...)`.
   - Para modelos prioritários sem cotação recente, consulte ofertas reais à vista/PIX em lojas brasileiras (`amazon`, `kabum`, `mercadolivre`, `pichau`, `terabyte`, `magalu`, `dell`) usando `search_web`.
   - Grave **apenas** preços atuais confirmados com URL válida de varejista brasileiro (nunca estime valores nem registre suportes, cabos ou peças):
     ```bash
     /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_monitors_27.py --no-open --record-price <product_id> <marketplace> <preco_numerico> "<url_da_oferta>" --title "<titulo_do_anuncio>"
     ```

3. **Validação e Análise Executiva Comparativa**:
   - Leia [monitors_27_history_summary.md](../../reports/monitors_27_history_summary.md) e confira os alertas emitidos no log da execução.
   - Responda em português (`pt-BR`) apresentando:
     1. **Resumo do Ciclo**: número da rodada, total de cotações acumuladas no SQLite, quantidade de pontos na linha do tempo do gráfico e contagem regressiva para a Black Friday (`27/11/2026`).
     2. **Principais Quedas e Oscilações**: variações relevantes frente à rodada imediatamente anterior.
     3. **Tabela Consolidada dos 13 Monitores**: ordenada pelo menor preço atual, destacando `🎯 ABAIXO DO ALVO` e mínimas históricas (sempre formatando valores monetários entre crases, como `` `R$ 1.061,10` ``).
     4. **Veredito por Perfil de Uso**: melhores opções atuais em *QHD Gamer Custo-Benefício*, *QHD + USB-C*, *eSports 240Hz+* e *Home Office Corporativo*.
     5. **Links Clicáveis**: [monitores_27_black_friday.html](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/monitores_27_black_friday.html) e [monitors_27_history_summary.md](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/monitors_27_history_summary.md).
