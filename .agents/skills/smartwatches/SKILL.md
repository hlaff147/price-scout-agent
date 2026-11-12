---
name: smartwatches
description: >-
  Busca preços ao vivo dos 11 smartwatches com melhor custo x benefício na faixa de R$ 800
  a R$ 1.200 (com destaque para o HUAWEI WATCH GT Runner 2, Amazfit Balance 2, Amazfit Balance 1,
  Samsung Galaxy Watch 7 40mm e 44mm, Galaxy Watch 8 LTE, HUAWEI WATCH Fit 5 Pro, HUAWEI WATCH GT 6,
  Garmin Forerunner 55, Amazfit Active 3 Premium e Amazfit Cheetah Square), incrementa o histórico
  temporal no SQLite e no log de ciclos, recompila o dashboard interativo Chart.js
  (reports/smartwatches_black_friday.html) com Índice de Benefício Vestível (0-100) e retorno por
  R$ 1.000 gastos, e apresenta análise comparativa de ofertas Black Friday. Use esta skill quando o
  usuário invocar /smartwatches ou /smartwatch ou pedir para buscar/atualizar preços e relatórios dos smartwatches.
---

# Skill `/smartwatches` — Busca Incremental e Dashboard Black Friday (Smartwatches R$ 800 a R$ 1.200)

Executa uma rodada completa de coleta de preços dos 11 smartwatches (`src/config/smartwatches_800_1200.yaml`), grava os novos pontos na série histórica do SQLite (`data/promoradar.db`) e no log de ciclos (`data/smartwatches_cycles.jsonl`), atualiza os gráficos evolutivos e de Custo × Benefício no painel `Chart.js` (`reports/smartwatches_black_friday.html`) e entrega um comparativo executivo por perfil esportivo e tecnológico, mantendo **foco absoluto no HUAWEI WATCH GT Runner 2** (maratona, titanio, GPS flutuante 3D e HRV).

## Passo a Passo de Execução

1. **Disparar a coleta ao vivo e atualização incremental do dashboard**:
   Execute o motor de rastreamento:
   ```bash
   /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_smartwatches.py --no-open
   ```
   - **Nota sobre Sandbox**: Tente primeiro no modo padrão (`BypassSandbox: false`). Caso os logs indiquem bloqueio de rede do sandbox (`403 Forbidden`), cancele a tarefa em background (`manage_task` com `kill`) e reexecute o mesmo comando com `BypassSandbox: true` mantendo o `toolSummary` idêntico.
   - Mesmo que o usuário filtre por um relógio específico (ex: `/smartwatches huawei-gt-runner-2`), prefira monitorar o conjunto completo para atualizar as curvas comparativas de preço e custo-benefício.

2. **Enriquecimento resiliente via Busca Web (para modelos sem retorno HTTP direto)**:
   - Confira na saída do Passo 1 a lista `Sem cotação HTTP direta (...)`.
   - Para modelos prioritários sem cotação recente (em especial o **HUAWEI WATCH GT Runner 2**), consulte ofertas reais à vista/PIX em varejistas brasileiros (`amazon`, `kabum`, `mercadolivre`, `magalu`, `shopee`, `aliexpress_br`) usando `search_web`.
   - **Atenção**: Nunca registre preços de acessórios falsos-positivos (pulseiras avulsas, películas, capas protetoras, docks ou cabos carregadores) ou modelos de entrada fora do escopo. Grave apenas preços confirmados do relógio inteligente completo novo com URL válida:
     ```bash
     /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_smartwatches.py --no-open --record-price <product_id> <marketplace> <preco_numerico> "<url_da_oferta>" --title "<titulo_do_anuncio>"
     ```

3. **Validação e Análise Executiva Comparativa**:
   - Leia [smartwatches_summary.md](../../reports/smartwatches_summary.md) e confira os alertas emitidos no log da execução.
   - Responda em português (`pt-BR`) apresentando:
     1. **Resumo do Ciclo**: número da rodada, total de cotações acumuladas no SQLite, relógios na faixa de `` `R$ 800` `` a `` `R$ 1.200` `` e oportunidades abaixo do alvo de Black Friday (`27/11/2026`).
     2. **Destaque Especial HUAWEI WATCH GT Runner 2**: status de preço atual, proximidade do piso histórico promocional (`` `R$ 999,00` `` a `` `R$ 1.276,00` ``), arquitetura do sensor TruSense/HRV, antena 3D flutuante e peso ultraleve (34,5 g).
     3. **Tabela Consolidada dos 11 Smartwatches**: ordenada por Custo-Benefício (`Pts/R$ 1.000`) ou menor preço atual, destacando `🎯 ABAIXO DO ALVO`, GNSS (Banda Dupla L1+L5 vs L1 simples), Autonomia de Bateria em dias, SO (HarmonyOS vs Zepp OS vs Wear OS) e preço atual formatado entre crases (ex: `` `R$ 1.099,00` ``).
     4. **Síntese por Perfil de Prioridade**:
        - *Maratona, Asfalto & Máxima Precisão Cardíaca*: `HUAWEI WATCH GT Runner 2` (L1+L5 3D, 34,5 g, titânio, 14 dias)
        - *Híbrido Premium Completo (Bioimpedância, ECG & Bateria 14d)*: `Amazfit Balance 2` vs `Amazfit Balance 1`
        - *Wear OS, Mini-Smartphone & Pagamento por Aproximação Universal*: `Samsung Galaxy Watch 7 (40mm / 44mm)` vs `Galaxy Watch 8 LTE`
        - *Plataforma Tradicional de Corrida (Garmin Coach & Botões Físicos)*: `Garmin Forerunner 55`
        - *Piso do Orçamento com GPS L1+L5 Integrado (< R$ 850)*: `Amazfit Cheetah Square` vs `Amazfit Active 3 Premium`
     5. **Widget Interativo Inline**: renderizar `<agent-embed src="file://<ArtifactDir>/grafico_precos_smartwatches.html"></agent-embed>`.
     6. **Links Clicáveis**: [smartwatches_black_friday.html](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/smartwatches_black_friday.html) e [smartwatches_summary.md](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/smartwatches_summary.md).
