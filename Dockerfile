# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install .

# ==========================================
# Stage 2: Runtime
# ==========================================
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TZ=America/Sao_Paulo

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Cria usuário não-root para execução segura
RUN useradd -m -u 1000 -s /bin/bash appuser

# Copia dependências pré-instaladas do builder
COPY --from=builder /install /usr/local

# Copia o código da aplicação
COPY --chown=appuser:appuser . /app

# Configura diretórios de dados persistentes e relatórios
RUN mkdir -p /app/data /app/reports && \
    chown -R appuser:appuser /app/data /app/reports

USER appuser

# Verificação periódica de integridade
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python docker/healthcheck.py || exit 1

# Volumes montados para persistência
VOLUME ["/app/data", "/app/reports"]

# Execução contínua padrão
CMD ["python", "scripts/schedule_daemon.py"]
