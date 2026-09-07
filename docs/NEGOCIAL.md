# Documento de Negócio — PromoRadar

## 1. Contexto

Acompanhar promoções de um produto específico manualmente exige entrar em vários
sites (Amazon, Mercado Livre, Magazine Luiza, KaBuM, AliExpress, Shopee, etc.)
diversas vezes por dia, comparar preços, e ainda assim é fácil perder uma
promoção relâmpago ou um cupom que só dura algumas horas.

O gatilho deste projeto foi a busca recorrente por promoções do **Huawei
FreeBuds Pro 5**, mas o problema é genérico: qualquer produto de interesse
(eletrônico, eletrodoméstico, etc.) sofre do mesmo desgaste de monitoramento
manual.

## 2. Problema

- Tempo gasto diariamente revisitando sites para checar preço.
- Dificuldade de saber se um "desconto" anunciado é real (muitos e-commerces
  inflam o preço "de" para simular desconto).
- Promoções de curta duração (relâmpago, cupom, flash sale) são perdidas por
  falta de monitoramento contínuo.
- Preço varia por variante do produto (cor, região, versão global vs
  nacional), gerando comparações incorretas se não houver normalização.

## 3. Objetivo do Projeto

Criar um agente autônomo que, dado um produto de interesse, monitore
continuamente múltiplas fontes na web, identifique quando o preço está
realmente em condição de compra vantajosa (com base em histórico, não apenas
no rótulo "promoção") e notifique o usuário automaticamente.

## 4. Proposta de Valor

| Antes | Depois |
|---|---|
| Busca manual em vários sites, várias vezes ao dia | Monitoramento contínuo e automático |
| Sem noção de histórico de preço | Alerta baseado em preço mínimo histórico real |
| Perde promoções relâmpago | Checagem frequente (ex.: a cada 1-4h) |
| Um produto por vez, de cabeça | Lista de produtos configurável e escalável |

## 5. Público-alvo / Personas

- **MVP:** uso pessoal (você), monitorando 1 a N produtos específicos.
- **Evolução:** amigos/família com acesso a um bot de Telegram compartilhado.
- **Visão de longo prazo (opcional):** produto para entusiastas de tecnologia
  que quiseram monitorar produtos de nicho não cobertos por agregadores
  genéricos (Buscapé, Zoom, PromoBit).

## 6. Escopo do MVP

- Cadastro de 1 produto (ex.: "Huawei FreeBuds Pro 5") com nome, palavras-chave
  e faixa de preço aceitável.
- Monitoramento em 3–5 marketplaces via scraping/busca.
- Registro de histórico de preço por fonte.
- Notificação via Telegram quando o preço cair abaixo do limite definido ou
  atingir uma mínima histórica.
- Execução agendada (ex.: de hora em hora) local ou em nuvem.

## 7. Escopo Futuro (Roadmap)

1. [x] Múltiplos produtos com prioridades diferentes (High=1h, Medium=4h, Low=12h) e rate limiter por domínio.
2. [x] Suporte a Playwright para renderização de SPAs e marketplaces JS-pesados com pool de browsers.
3. [x] Deduplicação inteligente de variantes (cor/versão/capacidade/região) e Bot Conversacional no Telegram.
4. [x] Subagente Self-Healing com Gemini 1.5 Flash e validação rigorosa em sandbox.
5. [x] Alertas por cupom/código de desconto com cálculo de preço efetivo e listagem via bot (`/coupons`).
6. [x] Empacotamento Full Docker (multi-stage) e suporte a deploy 24/7 em VPS com SQLite WAL.
7. [x] Relatório visual pós-ciclo em HTML com gráficos interativos Chart.js.
8. [ ] Suporte a mais canais de notificação (WhatsApp, Discord).
9. [ ] Modelo preditivo simples de "melhor momento para comprar".

## 8. Métricas de Sucesso (KPIs)

- **Tempo economizado:** redução do tempo manual gasto pesquisando promoções.
- **Taxa de captura:** % de promoções reais que o agente identificou vs. as
  que você encontrou depois manualmente (idealmente 0 promoções perdidas).
- **Taxa de falso positivo:** alertas disparados que não eram realmente boas
  ofertas (minimizada pela deduplicação semântica e detector de desconto inflado).
- **Latência do alerta:** tempo entre a promoção aparecer no site e a
  notificação chegar (otimizada pelos ciclos por prioridade: 1h para itens de alta prioridade).

## 9. Riscos e Restrições

- **Legal/ToS:** scraping pode violar termos de uso de alguns sites; mitigar
  priorizando APIs oficiais quando existirem e respeitando `robots.txt` e
  limites de requisição com `DomainRateLimiter`.
- **Fragilidade de scraping:** mudanças de layout no site quebram o parser.
  Mitigado com o subagente `GeminiHealerSubagent` (Self-Healing com Circuit Breaker e validação em sandbox).
- **Custo de LLM:** uso de agentes com LLM tem custo por chamada; mitigado
  com sanitização prévia do DOM (reduzindo tokens em até 85%) e circuit breaker (máx 2 tentativas/dia por loja).
- **Bloqueio por anti-bot:** IP/rate limit block. Mitigado com espaçamento configurável por domínio (1.5s–3.0s),
  user-agents realistas e renderização headless via Playwright.

## 10. Estimativa de Custos (ordem de grandeza)

- Hospedagem: VPS Linux básica (1-2 vCPU, 2GB RAM) a ~US$ 4-6/mês via Docker Compose.
- API de LLM: desprezível (< US$ 0.10/mês no Gemini Flash), acionado apenas em quebras de layout ou variantes complexas.
- Armazenamento: local SQLite em volume Docker persistente (WAL).

## 11. Critérios de Aceite do MVP (Validados ✅)

- [x] Consigo cadastrar um produto (nome + faixa de preço) via config simples (`src/config/products.yaml`) ou Telegram (`/add`).
- [x] O agente varre pelo menos 3 fontes automaticamente em um ciclo agendado (Mercado Livre, Amazon, Shopee, KaBuM, Google Shopping).
- [x] Recebo notificação no Telegram quando o preço encontrado é vantajoso (`NotifierSubagent` / `AdkNotifierAgent`).
- [x] Existe histórico de preço persistido (SQLite WAL consultável por data e fonte).
- [x] Falhas de scraping em uma fonte não derrubam o ciclo inteiro (isolamento com `asyncio.gather(..., return_exceptions=True)`).

## 12. Funcionalidades Estratégicas Entregues (Evolução Contínua ✅)

- **Fase 1: Múltiplos Produtos & Priorização Inteligente:**
  Escalonamento com `HIGH` (1h), `MEDIUM` (4h) e `LOW` (12h), com cálculo atômico de `proximo_ciclo_em` e `DomainRateLimiter` protegendo requisições contra bloqueios por domínio.
- **Fase 2: Suporte a Playwright para SPAs/JS:**
  Pool de navegadores gerenciado (`PlaywrightBrowserPool`) com bloqueio de assets pesados (imagens/fontes) e fallback automático entre requisição HTTP e renderização completa de browser.
- **Fase 3: Deduplicação Semântica & Bot Conversacional no Telegram:**
  Deduplicação de variantes divergentes (exclui acessórios, cores e versões incompatíveis como Global vs Nacional) e interface conversacional completa no Telegram com comandos `/list`, `/add`, `/priority`, `/pause`, `/resume`, `/coupons`, `/check` e `/status`.
- **Fase 4: Subagente Self-Healing com Gemini:**
  Reparo autônomo de seletores CSS quebrados via Gemini 1.5 Flash, com sanitizador de DOM, circuit breaker de segurança (máx 2 tentativas em 24h) e validação obrigatória em sandbox antes da persistência.
- **Fase 5: Alertas Especializados por Cupom e Códigos Promocionais:**
  Detecção inteligente de cupons em texto de anúncios, cálculo de preço efetivo com desconto (percentual ou fixo), armazenamento dedicado na tabela `coupons` e alertas específicos com templates ricos.
- **Fase 6: Full Docker & Deploy Contínuo em VPS:**
  Container multi-stage com Chromium, usuário não-root `appuser`, healthcheck integrado, Docker Compose com volume persistente para SQLite e relatórios de ciclo montados no host.

