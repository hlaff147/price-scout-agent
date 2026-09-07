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
| Notificações | Bot do Telegram (`python-telegram-bot`) | E-mail (SMTP), Discord Webhook |
| Logging | `loguru` | `structlog` |
| Testes | `pytest` + `pytest-mock` | — |
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
└── ativo (bool)

Source
├── id
├── product_id (FK)
├── marketplace          # "amazon", "mercadolivre", "kabum"...
├── url_produto
└── metodo_coleta        # "scraping_html" | "browser" | "api"

PriceRecord
├── id
├── source_id (FK)
├── preco
├── preco_original       # para calcular desconto real
├── moeda
├── disponivel (bool)
├── cupom (nullable)
└── coletado_em (timestamp)

Alert
├── id
├── product_id (FK)
├── price_record_id (FK)
├── motivo               # "abaixo_do_alvo" | "minimo_historico" | "cupom_novo"
├── enviado_em
└── canal                # "telegram" | "email"
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

## 10. Deploy e Infraestrutura

- **MVP local:** execução via cron no próprio computador/Raspberry Pi.
- **Produção leve:** container Docker + `systemd timer` em VPS barata, ou
  GitHub Actions com execução agendada (`schedule:` no workflow).
- Banco SQLite versionado em disco persistente (volume Docker) — migrar para
  Postgres gerenciado se o projeto crescer para múltiplos usuários.

## 11. Estrutura de Pastas do Repositório

```
promo-radar/
├── src/
│   ├── orchestrator/        # agente orquestrador principal
│   ├── subagents/           # um módulo por subagente
│   │   ├── scraper_agent/
│   │   ├── price_analyst_agent/
│   │   └── notifier_agent/
│   ├── skills/              # SKILL.md + lógica de parsing por marketplace
│   │   ├── parse_amazon/
│   │   ├── parse_mercadolivre/
│   │   └── normalize_product/
│   ├── mcp_servers/         # servidores MCP customizados (se necessário)
│   ├── tools/               # funções utilitárias chamadas por agentes
│   ├── data/                # models pydantic + acesso a banco
│   └── config/              # produtos monitorados, thresholds
├── tests/
├── scripts/                 # scripts de agendamento/execução manual
├── docs/
│   ├── NEGOCIAL.md
│   ├── TECNICO.md
│   └── ARQUITETURA.md
├── .env.example
├── pyproject.toml
└── README.md
```

## 12. Roadmap Técnico

1. MVP com 1 produto, scraping simples (requests/BS4) em 2-3 sites estáticos.
2. Adicionar Playwright para sites dependentes de JS.
3. Introduzir subagentes paralelos (um por marketplace) via Claude Agent SDK.
4. Adicionar skills reutilizáveis de parsing/normalização.
5. Persistência em Postgres + dashboard simples (opcional, ex.: Streamlit).
6. Empacotar como serviço agendado em nuvem.
