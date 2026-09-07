"""Database connection and table management using SQLite."""

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
    intervalo_customizado_min INTEGER,
    ultimo_ciclo_em TIMESTAMP,
    proximo_ciclo_em TIMESTAMP,
    ativo INTEGER NOT NULL DEFAULT 1,
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
    price_record_id INTEGER NOT NULL,
    motivo TEXT NOT NULL,
    detalhes TEXT,
    enviado_em TIMESTAMP NOT NULL,
    canal TEXT NOT NULL DEFAULT 'telegram',
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (price_record_id) REFERENCES price_records(id) ON DELETE CASCADE
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
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(marketplace, target_field)
);

CREATE TABLE IF NOT EXISTS healing_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    tentado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
    primeira_vez_visto TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultimo_visto TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ativo INTEGER DEFAULT 1,
    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL,
    UNIQUE (marketplace, codigo)
);

CREATE INDEX IF NOT EXISTS idx_coupons_mkt_code ON coupons(marketplace, codigo);
"""


class Database:
    """Gerenciador de conexão SQLite do PromoRadar."""

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
        """Fornece uma conexão segura com rollback em caso de erro."""
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

    def init_db(self) -> None:
        """Cria as tabelas e índices se ainda não existirem."""
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=30.0) as setup_conn:
                setup_conn.execute("PRAGMA journal_mode = WAL;")
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            # Migrações para tabela sources
            src_cols = [col[1] for col in conn.execute("PRAGMA table_info(sources)").fetchall()]
            if "ativo" not in src_cols:
                conn.execute("ALTER TABLE sources ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1;")
            if "motivo_desativacao" not in src_cols:
                conn.execute("ALTER TABLE sources ADD COLUMN motivo_desativacao TEXT;")
            
            # Migrações para tabela products
            prod_cols = [col[1] for col in conn.execute("PRAGMA table_info(products)").fetchall()]
            if "prioridade" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN prioridade TEXT NOT NULL DEFAULT 'medium';")
            if "intervalo_customizado_min" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN intervalo_customizado_min INTEGER;")
            if "ultimo_ciclo_em" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN ultimo_ciclo_em TIMESTAMP;")
            if "proximo_ciclo_em" not in prod_cols:
                conn.execute("ALTER TABLE products ADD COLUMN proximo_ciclo_em TIMESTAMP;")
        logger.debug(f"Banco de dados inicializado em: {self.db_path}")


# Instância padrão
default_db = Database()
