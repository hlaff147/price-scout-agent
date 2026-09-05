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
            columns = [col[1] for col in conn.execute("PRAGMA table_info(sources)").fetchall()]
            if "ativo" not in columns:
                conn.execute("ALTER TABLE sources ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1;")
            if "motivo_desativacao" not in columns:
                conn.execute("ALTER TABLE sources ADD COLUMN motivo_desativacao TEXT;")
        logger.debug(f"Banco de dados inicializado em: {self.db_path}")


# Instância padrão
default_db = Database()
