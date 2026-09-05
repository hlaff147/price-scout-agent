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

1. Múltiplos produtos com prioridades diferentes.
2. Dashboard web com histórico de preços (gráfico).
3. Deduplicação inteligente de variantes (cor/versão) via LLM.
4. Alertas por cupom/código de desconto, não só preço.
5. Suporte a mais canais de notificação (WhatsApp, e-mail, Discord).
6. Modelo preditivo simples de "melhor momento para comprar".

## 8. Métricas de Sucesso (KPIs)

- **Tempo economizado:** redução do tempo manual gasto pesquisando promoções.
- **Taxa de captura:** % de promoções reais que o agente identificou vs. as
  que você encontrou depois manualmente (idealmente 0 promoções perdidas).
- **Taxa de falso positivo:** alertas disparados que não eram realmente boas
  ofertas.
- **Latência do alerta:** tempo entre a promoção aparecer no site e a
  notificação chegar.

## 9. Riscos e Restrições

- **Legal/ToS:** scraping pode violar termos de uso de alguns sites; mitigar
  priorizando APIs oficiais quando existirem e respeitando `robots.txt` e
  limites de requisição.
- **Fragilidade de scraping:** mudanças de layout no site quebram o parser.
  Mitigar com testes automatizados e alertas de falha do próprio agente.
- **Custo de LLM:** uso de agentes com LLM tem custo por chamada; mitigar
  usando modelos menores/baratos para tarefas simples (ex.: parsing) e
  reservando modelos maiores só para decisão/orquestração.
- **Bloqueio por anti-bot:** IP/rate limit block. Mitigar com backoff,
  user-agents variados e, se necessário, proxies.

## 10. Estimativa de Custos (ordem de grandeza)

- Hospedagem: gratuito (execução local/cron) a ~US$5-10/mês (VPS pequena).
- API de LLM: baixo, dado uso pessoal com poucos produtos e execuções
  espaçadas (algumas dezenas de chamadas/dia).
- Proxies (opcional, se houver bloqueio): variável, pode começar sem.

## 11. Critérios de Aceite do MVP

- [ ] Consigo cadastrar um produto (nome + faixa de preço) via config simples.
- [ ] O agente varre pelo menos 3 fontes automaticamente em um ciclo agendado.
- [ ] Recebo notificação no Telegram quando o preço encontrado é vantajoso.
- [ ] Existe histórico de preço persistido (consigo consultar depois).
- [ ] Falhas de scraping em uma fonte não derrubam o ciclo inteiro (isolamento
      de falhas por subagente).
