# Documento Técnico — PromoRadar

## 1. Visão Geral Técnica

Sistema em Python que orquestra um agente de IA (via **Claude Agent SDK** ou
equivalente) capaz de acionar **subagentes**, **skills** e **MCP servers**
para: (1) buscar/raspar preços de um produto em múltiplas fontes, (2)
normalizar e comparar com histórico, e (3) notificar quando houver uma
promoção real.

## 2. Stack Tecnológica

| Camada | Tecnologia sugerida | Alternativa |
|---|---|---|
| Linguagem | Python 3.12+ | — |
| Orquestração de agente | Google ADK (`google-adk` 2.8+) | Claude Agent SDK, LangGraph |
| Automação de navegador (sites com JS) | Playwright | Selenium |
| Scraping simples (HTML estático) | `requests` + `BeautifulSoup4` | `httpx` + `selectolax` |
| Parsing estruturado / schemas | `pydantic` | `dataclasses` |
| Banco de dados | SQLite (MVP) | PostgreSQL (produção/escala) |
| Agendamento | `APScheduler` ou cron do SO | GitHub Actions (workflow agendado) |
| Notificações | Bot do Telegram (`python-telegram-bot` / HTTP) | E-mail (SMTP), Discord Webhook |
| Relatórios Visuais | `jinja2` + Chart.js | Streamlit, Dash |
| Logging | `loguru` | `structlog` |
| Testes | `pytest` + `pytest-mock` + `pytest-asyncio` | — |
| Lint/format | `ruff` + `black` | — |
| Empacotamento/deploy | Docker | `systemd` timer em VPS |

## 3. Modelo de Dados

```
Product
├── id
├── nome                # "Huawei FreeBuds Pro 5"
├── keywords[]          # termos de busca alternativos
├── preco_alvo          # preço que o usuário considera bom
├── preco_maximo        # teto aceitável
├── prioridade          # "high" (1h) | "medium" (4h) | "low" (12h)
├── intervalo_customizado_min # opcional
├── ultimo_ciclo_em     # timestamp
├── proximo_ciclo_em    # timestamp
└── ativo (bool)

Source
├── id
├── product_id (FK)
├── marketplace          # "amazon", "mercadolivre", "kabum", "shopee"...
├── url_produto
├── metodo_coleta        # "scraping_html" | "browser" | "api"
├── ativo (bool)
└── motivo_desativacao (nullable)

PriceRecord
├── id
├── source_id (FK)
├── preco
├── preco_original       # para calcular desconto real
├── moeda
├── disponivel (bool)
├── cupom (nullable)
└── coletado_em (timestamp)

Coupon
├── id
├── marketplace
├── product_id (FK nullable)
├── codigo               # "TECH10", "MELI15"
├── descricao
├── desconto_percentual
├── desconto_fixo
├── preco_minimo
├── valido_ate
├── primeira_vez_visto
├── ultimo_visto
└── ativo (bool)

SelectorOverride
├── id
├── marketplace
├── target_field         # "container", "titulo", "preco"
├── original_selector
├── healed_selector
├── confidence_score
├── status               # "active", "pending_review", "rolled_back"
├── sucessos_consecutivos
└── falhas_consecutivas

Alert
├── id
├── product_id (FK)
├── price_record_id (FK)
├── motivo               # "abaixo_do_alvo" | "minimo_historico" | "desconto_real" | "cupom_promocional"
├── enviado_em
└── canal                # "telegram" | "console"
```

## 4. Estratégia de Web Scraping

- **Prioridade de coleta:** API oficial > scraping HTML estático > automação
  de navegador (Playwright), do método mais barato/estável para o mais caro.
- **Respeito a `robots.txt`** e termos de uso de cada fonte antes de habilitar
  o scraper daquele marketplace.
- **Rate limiting** por fonte (ex.: 1 requisição a cada N segundos) e
  `backoff` exponencial em erros 429/503.
- **Rotação de User-Agent** e headers realistas para reduzir bloqueios triviais.
- **Parser isolado por marketplace** (um módulo/skill por site), para que a
  quebra de um parser não afete os demais.
- **Deduplicação de variantes:** normalizar nome do produto (cor, edição,
  versão global/nacional) antes de comparar preços entre fontes.
- **Detecção de "falso desconto":** comparar preço "de/por" anunciado com o
  histórico coletado, não confiar apenas no rótulo do site.

## 5. Agendamento (Scheduler)

- MVP: `APScheduler` rodando em processo local ou cron do SO, ciclo a cada
  1–4 horas (ajustável por produto, produtos mais concorridos podem ter ciclo
  mais curto).
- Produção: workflow agendado em GitHub Actions ou VPS com `systemd timer`,
  evitando depender do computador local estar ligado.

## 6. Notificações

- Canal inicial: bot do Telegram (simples de configurar, push imediato).
- Mensagem deve conter: produto, preço encontrado, preço original, desconto
  %, fonte/link direto, e se é mínimo histórico.
- Extensível para e-mail/Discord via interface comum de "notifier".

## 7. Observabilidade e Logging

- Log estruturado por ciclo de execução (produto, fontes consultadas, tempo
  de resposta, erros).
- Alerta para o próprio usuário quando um scraper falha N vezes seguidas
  (sinal de que o site mudou o layout).
- Métricas simples: nº de ciclos executados, nº de preços coletados, nº de
  alertas disparados.

## 8. Testes

- **Testes unitários** dos parsers, usando HTML salvo localmente (fixtures)
  para não depender da rede nem de mudanças no site real.
- **Testes de integração** do fluxo orquestrador → subagente → persistência,
  com mocks de rede.
- **Testes de regressão de parser:** rodar periodicamente contra o site real
  em ambiente controlado para detectar quebra de layout cedo.

## 9. Segurança e Compliance

- Segredos (token do Telegram, chave de API do modelo) em variáveis de
  ambiente / `.env`, nunca versionados.
- Verificar explicitamente `robots.txt` e ToS de cada marketplace antes de
  adicionar um novo scraper; priorizar fontes com API pública quando
  disponível (ex.: Mercado Livre possui API oficial de busca).
- Sem coleta de dados pessoais de terceiros — apenas dados públicos de preço.

## 10. Deploy e Infraestrutura (Full Docker em VPS)

O **PromoRadar** opera em modo **Full Docker** via **Docker Compose** para VPS (Hetzner, DigitalOcean, Lightsail):
- **Dockerfile multi-stage** (`python:3.12-slim`) com separação de build e runtime.
- **Segurança:** Execução estrita sob usuário não-root (`appuser:1000`).
- **Persistência garantida via volumes:**
  - `./data:/app/data`: preserva o banco de dados SQLite (`promoradar.db`, `wal`, `shm`).
  - `./reports:/app/reports`: preserva os relatórios HTML interativos gerados.
- **Resiliência:** Política `restart: unless-stopped`, rotação de logs (`max-size: 10m`, `max-file: 3`) e `HEALTHCHECK` periódico do SQLite.
- **Comandos operacionais rápidos (`Makefile`):**
  - `make docker-build`: compila a imagem do container.
  - `make docker-up`: inicia o daemon contínuo em background.
  - `make docker-down`: encerra a execução dos serviços.
  - `make docker-logs`: acompanha os logs em tempo real.
  - `make docker-cycle`: dispara um ciclo avulso sob demanda via container CLI.
  - `make docker-dry-run`: executa um ciclo de teste sem disparar alertas reais.

## 11. Estrutura de Pastas do Repositório

```
promo-radar/
├── src/
│   ├── core/                # Núcleo da Arquitetura Hexagonal
│   │   └── ports/           # Interfaces abstratas (IScraper, IAnalyst, INotifier, IRepository, IProductManagementPort, ISelectorRepositoryPort, ICouponRepositoryPort, IHttpClient)
│   ├── agents/              # Agentes Google ADK (BaseAgent, SequentialAgent, AdkMonitoringRunner)
│   ├── adapters/            # Driving Adapters
│   │   └── telegram_bot/    # Bot conversacional interativo (/list, /add, /priority, /pause, /resume, /coupons, /check, /status)
│   ├── orchestrator/        # Orquestrador procedural (mantido para compatibilidade --legacy)
│   ├── subagents/           # Adaptadores de scraping, análise, cura e notificação
│   │   ├── scraper_agent/   # ScraperSubagent (composite), HttpScraperSubagent, PlaywrightScraperSubagent, extractor
│   │   ├── price_analyst_agent/ # PriceAnalystSubagent (análise com histórico, cupons e variantes)
│   │   ├── healing_agent/   # GeminiHealerSubagent (self-healing de CSS com validação sandbox)
│   │   ├── matcher/         # HybridProductMatcher (deduplicação semântica de variantes)
│   │   └── notifier_agent/  # NotifierSubagent (despacho Telegram/Console para deals e cupons)
│   ├── skills/              # SKILL.md + lógica de parsing e formatação
│   │   ├── parse_amazon/
│   │   ├── parse_mercadolivre/
│   │   ├── parse_shopee/
│   │   ├── parse_google_shopping/
│   │   ├── parse_aliexpress/
│   │   ├── parse_kabum/
│   │   ├── parse_coupon/    # Parser e normalizador de cupons promocionais
│   │   ├── normalize_product/
│   │   ├── detect_fake_discount/
│   │   └── format_alert/
│   ├── tools/               # BrowserPool (Playwright), DomainRateLimiter, HttpClient, TelegramTools
│   ├── reporting/           # Gerador de relatórios HTML visuais (Jinja2 + Chart.js)
│   ├── data/                # Models Pydantic + SQLite WAL com migrations automáticas
│   └── config/              # Produtos monitorados (YAML) e settings (.env)
├── tests/                   # 88 testes automatizados (100% de sucesso)
│   ├── test_ports.py
│   ├── test_priority_and_rate_limiter.py
│   ├── test_playwright_scraper.py
│   ├── test_matcher_and_telegram_bot.py
│   ├── test_self_healing.py
│   ├── test_coupons.py
│   ├── test_parsers.py
│   ├── test_analyst.py
│   ├── test_repository.py
│   └── test_orchestrator.py
├── scripts/                 # CLI (run_cycle.py) e daemon agendado (schedule_daemon.py)
├── docker/                  # Healthcheck para container
├── Dockerfile               # Multi-stage build com Chromium e appuser não-root
├── docker-compose.yml       # Orquestração de volume persistente e restart contínuo
├── Makefile                 # Comandos operacionais locais e Docker
├── docs/                    # Documentação técnica, negocial e arquitetural (ADRs)
└── README.md
```

## 12. Roadmap Técnico

1. [x] MVP com monitoramento concorrente, isolamento de falhas e histórico persistido.
2. [x] Relatórios visuais pós-ciclo em HTML com gráficos Chart.js interativos.
3. [x] Arquitetura Hexagonal (Ports & Adapters) e orquestração via Google ADK (`google-adk` 2.8+).
4. [x] Automação via browser (Playwright) com pool de instâncias e bloqueio de mídia para SPAs.
5. [x] Subagente inteligente Self-Healing (Gemini 1.5 Flash) com sandbox e circuit breaker.
6. [x] Deduplicação semântica de variantes e Bot conversacional no Telegram (Driving Adapter).
7. [x] Alertas especializados por cupom, código promocional e cálculo de preço efetivo.
8. [x] Empacotamento Docker multi-stage e deploy contínuo em VPS com persistência SQLite WAL.

