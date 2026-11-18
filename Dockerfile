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

ARG INSTALL_PLAYWRIGHT_BROWSERS=true

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TZ=America/Sao_Paulo

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copia dependências Python pré-instaladas
COPY --from=builder /install /usr/local

# Instala binário e dependências de sistema do Chromium headless para fallback JS
RUN if [ "$INSTALL_PLAYWRIGHT_BROWSERS" = "true" ]; then \
        mkdir -p /ms-playwright && \
        playwright install --with-deps chromium && \
        chmod -R 755 /ms-playwright && \
        rm -rf /var/lib/apt/lists/*; \
    fi

# Cria usuário não-root para execução segura
RUN useradd -m -u 1000 -s /bin/bash appuser

COPY --chown=appuser:appuser . /app

RUN mkdir -p /app/data /app/reports && \
    chown -R appuser:appuser /app/data /app/reports

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python docker/healthcheck.py || exit 1

VOLUME ["/app/data", "/app/reports"]

CMD ["python", "scripts/schedule_daemon.py"]
