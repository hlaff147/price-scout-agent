---
name: suportes
description: >-
  Busca preços ao vivo dos 10 melhores suportes articulados para 1 e 2 monitores
  (ELG F80N/F80W, North Bayou NB F80, Zinnia Nimbo 110 V2, ELG FH80N, Coibeu DN01,
  ELG F160N, North Bayou NB F160, ELG FH160N, Zinnia Nimbo 210 e Vinik SM310C),
  com foco em instalação sem furos em mesa de 5 cm (50 mm), incrementa o histórico
  no SQLite e recompila o dashboard Chart.js (reports/suportes_monitor_black_friday.html).
  Use esta skill quando o usuário invocar /suportes ou pedir para buscar/atualizar
  preços e relatórios dos suportes/braços articulados de monitor.
---

# Skill `/suportes` — Busca Incremental e Dashboard Black Friday (Suportes Articulados 1 e 2 Monitores — Mesa 5 cm Sem Furos)

Executa uma rodada completa de coleta de preços dos 10 suportes articulados (`src/config/monitor_arms.yaml`), grava os novos pontos na série histórica do SQLite (`data/promoradar.db`) e no log de ciclos (`data/monitor_arms_cycles.jsonl`), atualiza os gráficos de Custo × Benefício e compatibilidade de morsa no painel `Chart.js` (`reports/suportes_monitor_black_friday.html`) e entrega um comparativo executivo focado em **instalação sem furos em mesa de 5 cm (50 mm)**.

## Passo a Passo de Execução

1. **Disparar a coleta ao vivo e atualização incremental do dashboard**:
   Execute o motor de rastreamento:
   ```bash
   /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_monitor_arms.py --no-open
   ```
   - **Nota sobre Sandbox**: Tente primeiro no modo padrão (`BypassSandbox: false`). Caso os logs iniciais indiquem bloqueio de rede do sandbox (`403 Forbidden`), cancele a tarefa em background (`manage_task` com `kill`) e reexecute o mesmo comando com `BypassSandbox: true` mantendo o `toolSummary` idêntico.
   - Mesmo que o usuário filtre por um modelo específico (ex.: `/suportes elg-f80n`), prefira rodar todos os 10 modelos para manter o comparativo completo.

2. **Enriquecimento resiliente via Busca Web (opcional para modelos sem retorno HTTP direto)**:
   - Confira na saída do Passo 1 a linha `Sem cotação HTTP direta (...)`.
   - Para modelos prioritários sem cotação recente, consulte ofertas reais à vista/PIX em varejistas brasileiros (`amazon`, `kabum`, `mercadolivre`, `magalu`, `pichau`) usando `search_web` e grave com:
     ```bash
     /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/.venv/bin/python /Users/humbertolimadealcantarafonsecafilho/price-scout-agent/scripts/track_monitor_arms.py --no-open --record-price <product_id> <marketplace> <preco_numerico> "<url_da_oferta>" --title "<titulo_do_anuncio>"
     ```

3. **Validação e Análise Executiva Comparativa**:
   - Leia [monitor_arms_summary.md](../../reports/monitor_arms_summary.md) e confira os alertas emitidos no log da execução.
   - Responda em português (`pt-BR`) apresentando:
     1. **Resumo do Ciclo**: número da rodada, total de cotações acumuladas no SQLite, suportes com morsa 5 cm confirmada e ofertas abaixo do alvo Black Friday (`27/11/2026`).
     2. **Compatibilidade Mesa de 5 cm (50 mm) Sem Furos**: folga da morsa (ELG 70–75 mm = 20–25 mm de folga; North Bayou 90–95 mm = 40–45 mm de folga; modelos econômicos a confirmar) e alerta sobre profundidade livre sob a borda e rigidez do tampo.
     3. **Tabela Consolidada (1 e 2 Monitores)**: ordenada por Custo-Benefício (`Pts/R$ 100`) ou menor preço atual, destacando `🎯 Abaixo do Alvo`, mecanismo, carga e preço atual formatado entre crases (ex: `` `R$ 155,00` ``).
     4. **Veredito por Cenário**: *Melhor Geral 1 Tela* (`ELG F80N` / `NB F80`), *Telas Pesadas* (`ELG FH80N` / `FH160N`), *Melhor Duplo* (`ELG F160N` / `NB F160` vs 2 braços individuais) e *Econômico* (`Zinnia Nimbo 110/210`, `Coibeu DN01`).
     5. **Links Clicáveis**: [suportes_monitor_black_friday.html](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/suportes_monitor_black_friday.html) e [monitor_arms_summary.md](file:///Users/humbertolimadealcantarafonsecafilho/price-scout-agent/reports/monitor_arms_summary.md).
