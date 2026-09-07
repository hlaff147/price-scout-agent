# Documento de Arquitetura — PromoRadar

## 1. Visão Geral

O **PromoRadar** adota uma arquitetura híbrida moderna que combina **Arquitetura Hexagonal (Ports & Adapters)** com o **Google Agent Development Kit (ADK 2.8+)**. 

O sistema é estruturado em três macro-camadas:
1. **Core (Domínio Puro):** Regras de negócio, modelos de dados Pydantic e interfaces abstratas (Ports) completamente livres de frameworks externos.
2. **Camada de Agentes (Google ADK):** Agentes determinísticos (`BaseAgent`) orquestrados sequencialmente em um pipeline (`SequentialAgent`), gerenciando estado compartilhado da sessão com rastreabilidade total.
3. **Adapters (Infraestrutura):** Implementações concretas para scraping de marketplaces, cliente HTTP com backoff, persistência em SQLite, envio de alertas via Telegram e geração de relatórios visuais em HTML.

```mermaid
graph TD
    subgraph "1. Core (Domínio Puro & Contratos)"
        PORTS["Ports (Interfaces Abstratas)<br/>IScraper, IAnalyst, INotifier, IRepository, IHttpClient"]
        MODELS["Modelos Pydantic<br/>Product, Source, PriceRecord, Alert, DealAnalysis, ScrapedData"]
    end

    subgraph "2. Orquestração (Google ADK 2.8+)"
        RUNNER["AdkMonitoringRunner<br/>(Runner + InMemorySessionService)"]
        COORD["SequentialAgent (Coordinator)"]
        SA["AdkScraperAgent<br/>(BaseAgent)"]
        AA["AdkAnalystAgent<br/>(BaseAgent)"]
        NA["AdkNotifierAgent<br/>(BaseAgent)"]
        RA["AdkReportAgent<br/>(BaseAgent)"]

        RUNNER --> COORD
        COORD --> SA --> AA --> NA --> RA
    end

    subgraph "3. Adapters (Infraestrutura Concreta)"
        SCRAPERS["ScraperSubagent<br/>(Amazon, Mercado Livre, Shopee, Google Shopping)"]
        HTTP["HttpClient (httpx)<br/>(Rate Limit, Backoff, User-Agents)"]
        REPO["Repository (SQLite WAL)<br/>(CRUD, Histórico, Anti-Spam)"]
        NOTIF["NotifierSubagent<br/>(Telegram Bot API / Console)"]
        REPORT["ReportGenerator<br/>(Jinja2 + Chart.js)"]
    end

    SA -->|consome| PORTS
    AA -->|consome| PORTS
    NA -->|consome| PORTS
    
    SCRAPERS -.->|implements| PORTS
    REPO -.->|implements| PORTS
    NOTIF -.->|implements| PORTS
    HTTP -.->|implements| PORTS
    RA --> REPORT
```

---

## 2. Camadas da Arquitetura Hexagonal

| Camada | Módulo / Pacote | Responsabilidade |
|---|---|---|
| **Core (Domínio & Ports)** | `src/core/ports/`, `src/data/models.py` | Define as interfaces abstratas (`IScraper`, `IAnalyst`, `INotifier`, `IRepository`, `IHttpClient`) e os schemas de dados. Zero acoplamento com redes, bancos ou frameworks. |
| **Agentes ADK** | `src/agents/` | Agentes orientados a eventos (`google.adk.agents.BaseAgent`). Orquestram a execução dos casos de uso, recebem o estado da sessão e propagam dados via `EventActions(state_delta={...})`. |
| **Adapters de Coleta** | `src/subagents/scraper_agent/`, `src/skills/` | Implementa `IScraper`. Contém os parsers de HTML específicos por marketplace e estratégias de extração. |
| **Adapters de Análise** | `src/subagents/price_analyst_agent/` | Implementa `IAnalyst`. Avalia desconto real contra histórico de 60 dias e detecta maquiagem de preços ("metade do dobro"). |
| **Adapters de Alerta** | `src/subagents/notifier_agent/`, `src/tools/notification_tools.py` | Implementa `INotifier`. Dispara mensagens formatadas no Telegram com controle de anti-spam (supressão em < 6h). |
| **Adapters de Persistência** | `src/data/repository.py`, `src/data/database.py` | Implementa `IRepository`. Persiste cotações e alertas em SQLite no modo WAL (Write-Ahead Logging). |
| **Adapters de Relatório** | `src/reporting/report_generator.py` | Renderiza relatórios HTML visuais e responsivos com gráficos comparativos e históricos via Chart.js. |
| **Execução & CLI** | `scripts/run_cycle.py`, `scripts/schedule_daemon.py` | Ponto de entrada para execução sob demanda ou em segundo plano via `APScheduler`. |

---

## 3. Orquestração via Google ADK

O pipeline do PromoRadar utiliza o **Google ADK** de forma determinística (agentes não-LLM, custo zero de tokens e latência em milissegundos), deixando a arquitetura pronta para futura injeção de agentes com LLM (ex.: self-healing scrapers):

1. **`AdkMonitoringRunner`**: Inicializa a sessão com `InMemorySessionService`, configura o estado inicial (`product`, `sources`, `dry_run`, `generate_report`) e inicia o streaming do `Runner`.
2. **`AdkScraperAgent`**:
   - Lê fontes ativas da sessão.
   - Dispara scraping concorrente com `asyncio.gather(..., return_exceptions=True)`.
   - Classifica resultados entre cotações coletadas, "sem resultado" e erros de rede.
   - Emite evento com `EventActions(state_delta={"scraped_pairs": ...})`.
3. **`AdkAnalystAgent`**:
   - Congela a linha de base histórica pré-ciclo (`prev_min`, `prev_avg`).
   - Avalia ofertas sem contaminação entre fontes do mesmo ciclo.
   - Emite evento com `EventActions(state_delta={"analyses": ..., "deals_found": ...})`.
4. **`AdkNotifierAgent`**:
   - Processa as ofertas detectadas e aplica a política anti-spam.
   - Dispara alertas no Telegram ou exibe no Console.
   - Emite evento com `EventActions(state_delta={"notifications_sent": ...})`.
5. **`AdkReportAgent`**:
   - Constrói o resumo do ciclo e compila o relatório HTML interativo com Chart.js.
   - Emite evento com `EventActions(state_delta={"report_path": ...})`.

---

## 4. Fluxo de Execução (Ciclo Completo)

```mermaid
sequenceDiagram
    autonumber
    participant CLI as CLI / Scheduler
    participant Runner as AdkMonitoringRunner
    participant ADK as SequentialAgent (Pipeline)
    participant Scraper as AdkScraperAgent
    participant Analyst as AdkAnalystAgent
    participant DB as SQLite Repository
    participant Notif as AdkNotifierAgent
    participant TG as Telegram Bot API
    participant Report as AdkReportAgent

    CLI->>Runner: run_cycle(product_id)
    Runner->>Runner: cria sessão isolada no SessionService
    Runner->>ADK: runner.run_async(new_message="start")
    
    rect rgb(240, 248, 255)
        Note over ADK,Scraper: Fase 1: Coleta Concorrente
        ADK->>Scraper: _run_async_impl(ctx)
        Scraper->>Scraper: asyncio.gather(fontes ativas)
        Scraper-->>ADK: yield Event(state_delta={scraped_pairs})
    end

    rect rgb(255, 250, 240)
        Note over ADK,Analyst: Fase 2: Análise Histórica Estável
        ADK->>Analyst: _run_async_impl(ctx)
        Analyst->>DB: busca linha de base pré-ciclo (prev_min, prev_avg)
        Analyst->>DB: persiste novos PriceRecords
        Analyst->>Analyst: detecta ofertas e falso desconto
        Analyst-->>ADK: yield Event(state_delta={analyses, deals_found})
    end

    rect rgb(240, 255, 240)
        Note over ADK,Notif: Fase 3: Notificação Anti-Spam
        ADK->>Notif: _run_async_impl(ctx)
        opt Oferta válida e sem spam (<6h)
            Notif->>TG: envia mensagem formatada (HTML)
            Notif->>DB: registra Alert enviado
        end
        Notif-->>ADK: yield Event(state_delta={notifications_sent})
    end

    rect rgb(255, 245, 245)
        Note over ADK,Report: Fase 4: Relatório Visual
        ADK->>Report: _run_async_impl(ctx)
        Report->>Report: renderiza Jinja2 + Chart.js
        Report-->>ADK: yield Event(state_delta={report_path})
    end

    ADK-->>Runner: turn_complete
    Runner->>Runner: recupera estado final consolidado
    Runner-->>CLI: resumo do ciclo + link do relatório
```

---

## 5. Skills e ADK Tools

### Skills (Módulos de Domínio & Extração)
Skills funcionam como procedimentos desacoplados reutilizáveis:
- **`parse_<marketplace>`**: Extrai preço, título e disponibilidade usando seletores CSS resilientes.
- **`normalize_product`**: Padroniza caracteres, moedas (`R$ 1.234,56`) e valida relevância por palavras-chave.
- **`detect_fake_discount`**: Heurística de confronto contra histórico real e contra teto máximo do usuário.
- **`format_alert`**: Formata mensagens em HTML para o Telegram e texto estruturado para console.

### ADK Tools (Funções Python Puras)
Localizadas em `src/tools/`:
- **`scraping_tools.py`**: `fetch_page_content(url)`, `parse_marketplace_html(html, marketplace, url)`.
- **`analysis_tools.py`**: `evaluate_fake_discount(...)`, `query_historical_prices(...)` (com injeção de `IRepository`).
- **`notification_tools.py`**: `send_telegram_notification(text, parse_mode)`.

---

## 6. Registro de Decisões de Arquitetura (ADRs)

| ADR | Título | Status | Decisão & Justificativa |
|---|---|---|---|
| **ADR-001** | Adoção do Google Agent Development Kit (ADK) | **Aprovada** | Substituiu o plano inicial de orquestrador puramente procedural e ideias de Claude SDK por `google-adk` (2.8+). Permite pipeline multiagente tipado, suporte nativo a agentes determinísticos (`BaseAgent`), propagação de estado padronizada (`EventActions`) e facilidade de plugar agentes com Gemini no futuro sem alterar o pipeline. |
| **ADR-002** | Refatoração para Arquitetura Hexagonal (Ports & Adapters) | **Aprovada** | Criação de interfaces abstratas (`IScraper`, `IAnalyst`, `INotifier`, `IRepository`, `IHttpClient`) em `src/core/ports/`. Garante que os agentes e a lógica de negócio não conheçam detalhes de rede (httpx), banco (sqlite3) ou Telegram, viabilizando mocks e troca de tecnologia com impacto zero no core. |
| **ADR-003** | Relatórios Visuais HTML pós-ciclo com Chart.js | **Aprovada** | Em vez de depender de um servidor de dashboard pesado (Streamlit) ativo 24/7, o próprio ciclo compila um arquivo HTML estático autocontido com gráficos interativos de histórico e comparação de preços, abrindo automaticamente no navegador. |
| **ADR-004** | Scraping HTTP Direto vs. Servidores MCP no MVP | **Aprovada** | Servidores MCP externos (Playwright, Search) adicionam custo de processo desnecessário para páginas onde requests estáticos com rotação de User-Agents atendem perfeitamente. O MCP permanece reservado para expansão futura. |
| **ADR-005** | Isolamento da Linha de Base no Analista de Preços | **Aprovada** | A consulta de mínima e média histórica (`prev_min`, `prev_avg`) deve ser capturada uma única vez no início do lote do produto, impedindo que a gravação de uma fonte contamine a comparação das fontes subsequentes no mesmo ciclo. |
