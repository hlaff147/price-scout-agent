"""Database connection, lazy default proxy, and reversible schema migrations using SQLite."""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger

from src.config.settings import settings

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    keywords TEXT NOT NULL,  -- JSON list
    preco_alvo REAL NOT NULL,
    preco_maximo REAL NOT NULL,
    prioridade TEXT NOT NULL DEFAULT 'medium',
    prioridade_manual INTEGER NOT NULL DEFAULT 0,
    intervalo_customizado_min INTEGER,
    ultimo_ciclo_em TIMESTAMP,
    proximo_ciclo_em TIMESTAMP,
    ativo INTEGER NOT NULL DEFAULT 1,
    ativo_manual INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    url_produto TEXT NOT NULL,
    metodo_coleta TEXT NOT NULL DEFAULT 'scraping_html',
    ativo INTEGER NOT NULL DEFAULT 1,
    motivo_desativacao TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(product_id, marketplace)
);

CREATE TABLE IF NOT EXISTS price_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    preco REAL NOT NULL,
    preco_original REAL,
    moeda TEXT NOT NULL DEFAULT 'BRL',
    disponivel INTEGER NOT NULL DEFAULT 1,
    cupom TEXT,
    titulo_coletado TEXT,
    url_encontrada TEXT,
    coletado_em TIMESTAMP NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_price_records_source_date
ON price_records(source_id, coletado_em DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    price_record_id INTEGER,
    motivo TEXT NOT NULL,
    detalhes TEXT,
    enviado_em TIMESTAMP NOT NULL,
    canal TEXT NOT NULL DEFAULT 'telegram',
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (price_record_id) REFERENCES price_records(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_product_date
ON alerts(product_id, enviado_em DESC);

CREATE TABLE IF NOT EXISTS selector_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    target_field TEXT NOT NULL,
    original_selector TEXT NOT NULL,
    healed_selector TEXT NOT NULL,
    confidence_score REAL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'active',
    sucessos_consecutivos INTEGER NOT NULL DEFAULT 0,
    falhas_consecutivas INTEGER NOT NULL DEFAULT 0,
    criado_em TIMESTAMP NOT NULL,
    UNIQUE(marketplace, target_field)
);

CREATE TABLE IF NOT EXISTS healing_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    tentado_em TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_healing_attempts_mkt_date
ON healing_attempts(marketplace, tentado_em DESC);

CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    product_id TEXT,
    codigo TEXT NOT NULL,
    descricao TEXT,
    desconto_percentual REAL,
    desconto_fixo REAL,
    preco_minimo REAL,
    valido_ate TIMESTAMP,
    primeira_vez_visto TIMESTAMP NOT NULL,
    ultimo_visto TIMESTAMP NOT NULL,
    ativo INTEGER DEFAULT 1,
    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL,
    UNIQUE (marketplace, codigo)
);

CREATE INDEX IF NOT EXISTS idx_coupons_mkt_code ON coupons(marketplace, codigo);
"""


class Database:
    """Gerenciador de conexão SQLite do PromoRadar com migrações seguras e reversíveis."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = str(db_path) if db_path else str(settings.db_path)
        self._memory_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON;")
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Fornece uma conexão segura com commit/rollback transacional."""
        if self._memory_conn is not None:
            try:
                yield self._memory_conn
                self._memory_conn.commit()
            except Exception:
                self._memory_conn.rollback()
                raise
        else:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _create_safety_backup_if_needed(self) -> None:
        """Cria backup físico pré-migração se o arquivo existir e precisar de migração estrutural."""
        if self.db_path == ":memory:":
            return
        db_file = Path(self.db_path)
        if not db_file.exists() or db_file.stat().st_size == 0:
            return
        bak_file = Path(f"{self.db_path}-pre-migration.bak")
        if not bak_file.exists():
            shutil.copy2(db_file, bak_file)

    def init_db(self) -> None:
        """Cria tabelas, índices e aplica migrações idempotentes preservando 100% dos dados."""
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=30.0) as setup_conn:
                setup_conn.execute("PRAGMA journal_mode = WAL;")

        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

            # Migrações aditivas para sources
            src_cols = {col[1] for col in conn.execute("PRAGMA table_info(sources)").fetchall()}
            if "ativo" not in src_cols:
                conn.execute("ALTER TABLE sources ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1;")
            if "motivo_desativacao" not in src_cols:
                conn.execute("ALTER TABLE sources ADD COLUMN motivo_desativacao TEXT;")

            # Migrações aditivas para products (incluindo proteção de estado manual runtime)
            prod_cols = {col[1] for col in conn.execute("PRAGMA table_info(products)").fetchall()}
            if "prioridade" not in prod_cols:
                conn.execute(
                    "ALTER TABLE products ADD COLUMN prioridade TEXT NOT NULL DEFAULT 'medium';"
                )
            if "prioridade_manual" not in prod_cols:
                conn.execute(
                    "ALTER TABLE products ADD COLUMN prioridade_manual INTEGER NOT NULL DEFAULT 0;"
                )
            if "intervalo_customizado_min" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN intervalo_customizado_min INTEGER;")
            if "ultimo_ciclo_em" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN ultimo_ciclo_em TIMESTAMP;")
            if "proximo_ciclo_em" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN proximo_ciclo_em TIMESTAMP;")
            if "ativo_manual" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN ativo_manual INTEGER;")

            # Migração estrutural de alerts: torna price_record_id anulável (ON DELETE SET NULL)
            # e repara eventuais FKs órfãs legadas sem perder nenhum registro histórico de alerta.
            alert_info = conn.execute("PRAGMA table_info(alerts)").fetchall()
            pr_col = next((c for c in alert_info if c[1] == "price_record_id"), None)
            has_orphan_alert = conn.execute(
                """
                SELECT 1 FROM alerts
                WHERE price_record_id IS NOT NULL
                  AND price_record_id NOT IN (SELECT id FROM price_records)
                LIMIT 1
                """
            ).fetchone()

            if (pr_col and pr_col[3] == 1) or has_orphan_alert:
                self._create_safety_backup_if_needed()
                conn.execute("PRAGMA foreign_keys = OFF;")
                try:
                    conn.executescript(
                        """
                        CREATE TABLE alerts_v2 (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            product_id TEXT NOT NULL,
                            price_record_id INTEGER,
                            motivo TEXT NOT NULL,
                            detalhes TEXT,
                            enviado_em TIMESTAMP NOT NULL,
                            canal TEXT NOT NULL DEFAULT 'telegram',
                            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                            FOREIGN KEY (price_record_id) REFERENCES price_records(id) ON DELETE SET NULL
                        );

                        INSERT INTO alerts_v2 (id, product_id, price_record_id, motivo, detalhes, enviado_em, canal)
                        SELECT
                            a.id,
                            a.product_id,
                            CASE
                                WHEN a.price_record_id IN (SELECT id FROM price_records) THEN a.price_record_id
                                ELSE NULL
                            END,
                            a.motivo,
                            a.detalhes,
                            a.enviado_em,
                            a.canal
                        FROM alerts a
                        WHERE a.product_id IN (SELECT id FROM products);

                        DROP TABLE alerts;
                        ALTER TABLE alerts_v2 RENAME TO alerts;
                        CREATE INDEX IF NOT EXISTS idx_alerts_product_date
                        ON alerts(product_id, enviado_em DESC);
                        """
                    )
                finally:
                    conn.execute("PRAGMA foreign_keys = ON;")

            # Normalização canônica de timestamps legados ('YYYY-MM-DD HH:MM:SS' -> ISO-8601 UTC)
            conn.execute(
                """
                UPDATE healing_attempts
                SET tentado_em = REPLACE(tentado_em, ' ', 'T') || '+00:00'
                WHERE tentado_em LIKE '____-__-__ __:__:__'
                """
            )
            conn.execute(
                """
                UPDATE selector_overrides
                SET criado_em = REPLACE(criado_em, ' ', 'T') || '+00:00'
                WHERE criado_em LIKE '____-__-__ __:__:__'
                """
            )

        logger.debug(f"Banco de dados inicializado em: {self.db_path}")


class LazyDatabaseProxy:
    """Proxy preguiçoso que evita I/O em disco durante o `import` de módulos."""

    def __init__(self) -> None:
        self._instance: Database | None = None
        self._target_path: str | None = None

    def _resolve(self) -> Database:
        current_path = str(settings.DATABASE_PATH)
        if self._instance is None or self._target_path != current_path:
            self._instance = Database(current_path)
            self._target_path = current_path
        return self._instance

    @property
    def db_path(self) -> str:
        return self._resolve().db_path

    def init_db(self) -> None:
        self._resolve().init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        with self._resolve().get_connection() as conn:
            yield conn


default_db: Database = LazyDatabaseProxy()  # type: ignore[assignment]
