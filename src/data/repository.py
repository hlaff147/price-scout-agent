"""Repository pattern for database operations in PromoRadar."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from loguru import logger

from src.core.ports.repository_port import IRepository
from src.data.database import Database, default_db
from src.data.models import Alert, PriceRecord, Product, Source


class Repository(IRepository):
    """Repositório de acesso aos dados de produtos, fontes, preços e alertas."""

    def __init__(self, db: Database | None = None):
        self.db = db or default_db

    # ------------------ Produtos ------------------ #

    def upsert_product(self, product: Product) -> Product:
        """Insere ou atualiza um produto."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO products (id, nome, keywords, preco_alvo, preco_maximo, ativo)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nome=excluded.nome,
                    keywords=excluded.keywords,
                    preco_alvo=excluded.preco_alvo,
                    preco_maximo=excluded.preco_maximo,
                    ativo=excluded.ativo;
                """,
                (
                    product.id,
                    product.nome,
                    json.dumps(product.keywords, ensure_ascii=False),
                    product.preco_alvo,
                    product.preco_maximo,
                    1 if product.ativo else 0,
                ),
            )
            # Salvar ou atualizar fontes associadas
            for src in product.sources:
                src.product_id = product.id
                self._upsert_source_with_conn(conn, src)

        return product

    def get_product(self, product_id: str) -> Product | None:
        """Recupera um produto com suas fontes associadas."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT id, nome, keywords, preco_alvo, preco_maximo, ativo FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
            if not row:
                return None

            sources = self.get_sources_for_product(product_id)
            return Product(
                id=row["id"],
                nome=row["nome"],
                keywords=json.loads(row["keywords"]),
                preco_alvo=row["preco_alvo"],
                preco_maximo=row["preco_maximo"],
                ativo=bool(row["ativo"]),
                sources=sources,
            )

    def list_active_products(self) -> list[Product]:
        """Lista todos os produtos ativos."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, nome, keywords, preco_alvo, preco_maximo, ativo FROM products WHERE ativo = 1"
            ).fetchall()

        products = []
        for r in rows:
            sources = self.get_sources_for_product(r["id"])
            products.append(
                Product(
                    id=r["id"],
                    nome=r["nome"],
                    keywords=json.loads(r["keywords"]),
                    preco_alvo=r["preco_alvo"],
                    preco_maximo=r["preco_maximo"],
                    ativo=bool(r["ativo"]),
                    sources=sources,
                )
            )
        return products

    # ------------------ Fontes ------------------ #

    def _upsert_source_with_conn(self, conn: sqlite3.Connection, source: Source) -> Source:
        conn.execute(
            """
            INSERT INTO sources (product_id, marketplace, url_produto, metodo_coleta, ativo, motivo_desativacao)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id, marketplace) DO UPDATE SET
                url_produto=excluded.url_produto,
                metodo_coleta=excluded.metodo_coleta,
                ativo=excluded.ativo,
                motivo_desativacao=excluded.motivo_desativacao;
            """,
            (
                source.product_id,
                source.marketplace,
                source.url_produto,
                source.metodo_coleta,
                1 if source.ativo else 0,
                source.motivo_desativacao,
            ),
        )
        if not source.id:
            row = conn.execute(
                "SELECT id FROM sources WHERE product_id = ? AND marketplace = ?",
                (source.product_id, source.marketplace),
            ).fetchone()
            if row:
                source.id = row["id"]
        return source

    def upsert_source(self, source: Source) -> Source:
        """Insere ou atualiza uma fonte de coleta para um produto."""
        with self.db.get_connection() as conn:
            return self._upsert_source_with_conn(conn, source)

    def get_sources_for_product(self, product_id: str) -> list[Source]:
        """Retorna todas as fontes cadastradas para um produto (ativas e inativas)."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, product_id, marketplace, url_produto, metodo_coleta, ativo, motivo_desativacao "
                "FROM sources WHERE product_id = ?",
                (product_id,),
            ).fetchall()

        return [
            Source(
                id=r["id"],
                product_id=r["product_id"],
                marketplace=r["marketplace"],
                url_produto=r["url_produto"],
                metodo_coleta=r["metodo_coleta"],
                ativo=bool(r["ativo"]),
                motivo_desativacao=r["motivo_desativacao"],
            )
            for r in rows
        ]

    def get_active_sources_for_product(self, product_id: str) -> list[Source]:
        """Retorna apenas as fontes ativas para um determinado produto."""
        all_sources = self.get_sources_for_product(product_id)
        return [s for s in all_sources if s.ativo]

    # ------------------ Registros de Preço ------------------ #

    def save_price_record(self, record: PriceRecord) -> PriceRecord:
        """Persiste um novo registro de preço coletado."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO price_records 
                (source_id, preco, preco_original, moeda, disponivel, cupom, titulo_coletado, url_encontrada, coletado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.source_id,
                    record.preco,
                    record.preco_original,
                    record.moeda,
                    1 if record.disponivel else 0,
                    record.cupom,
                    record.titulo_coletado,
                    record.url_encontrada,
                    record.coletado_em.isoformat(),
                ),
            )
            record.id = cursor.lastrowid
        logger.debug(f"Preço registrado: R${record.preco:.2f} (source_id={record.source_id})")
        return record

    def get_price_history(self, product_id: str, days: int = 90) -> list[PriceRecord]:
        """Retorna histórico de preços de todas as fontes de um produto nos últimos N dias."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT pr.id, pr.source_id, pr.preco, pr.preco_original, pr.moeda,
                       pr.disponivel, pr.cupom, pr.titulo_coletado, pr.url_encontrada, pr.coletado_em
                FROM price_records pr
                JOIN sources s ON s.id = pr.source_id
                WHERE s.product_id = ? AND pr.coletado_em >= ? AND pr.disponivel = 1
                ORDER BY pr.coletado_em DESC
                """,
                (product_id, cutoff),
            ).fetchall()

        records = []
        for r in rows:
            records.append(
                PriceRecord(
                    id=r["id"],
                    source_id=r["source_id"],
                    preco=r["preco"],
                    preco_original=r["preco_original"],
                    moeda=r["moeda"],
                    disponivel=bool(r["disponivel"]),
                    cupom=r["cupom"],
                    titulo_coletado=r["titulo_coletado"],
                    url_encontrada=r["url_encontrada"],
                    coletado_em=datetime.fromisoformat(r["coletado_em"]),
                )
            )
        return records

    def get_historical_min_price(self, product_id: str) -> float | None:
        """Retorna o menor preço histórico já registrado para o produto em qualquer fonte."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT MIN(pr.preco) as min_preco
                FROM price_records pr
                JOIN sources s ON s.id = pr.source_id
                WHERE s.product_id = ? AND pr.disponivel = 1
                """,
                (product_id,),
            ).fetchone()
            if row and row["min_preco"] is not None:
                return float(row["min_preco"])
            return None

    def get_historical_average_price(self, product_id: str, days: int = 60) -> float | None:
        """Retorna a média de preços nos últimos N dias."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT AVG(pr.preco) as avg_preco
                FROM price_records pr
                JOIN sources s ON s.id = pr.source_id
                WHERE s.product_id = ? AND pr.coletado_em >= ? AND pr.disponivel = 1
                """,
                (product_id, cutoff),
            ).fetchone()
            if row and row["avg_preco"] is not None:
                return float(row["avg_preco"])
            return None

    # ------------------ Alertas ------------------ #

    def save_alert(self, alert: Alert) -> Alert:
        """Registra um alerta enviado."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO alerts (product_id, price_record_id, motivo, detalhes, enviado_em, canal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.product_id,
                    alert.price_record_id,
                    alert.motivo,
                    alert.detalhes,
                    alert.enviado_em.isoformat(),
                    alert.canal,
                ),
            )
            alert.id = cursor.lastrowid
        return alert

    def has_recent_alert(self, product_id: str, hours: int = 12) -> bool:
        """Verifica se já foi enviado um alerta para o produto nas últimas N horas (anti-spam)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM alerts WHERE product_id = ? AND enviado_em >= ?",
                (product_id, cutoff),
            ).fetchone()
            return bool(row and row["count"] > 0)

    def get_price_history_by_source(self, source_id: int, days: int = 90) -> list[PriceRecord]:
        """Retorna histórico de preços de uma fonte específica nos últimos N dias."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, source_id, preco, preco_original, moeda,
                       disponivel, cupom, titulo_coletado, url_encontrada, coletado_em
                FROM price_records
                WHERE source_id = ? AND coletado_em >= ? AND disponivel = 1
                ORDER BY coletado_em ASC
                """,
                (source_id, cutoff),
            ).fetchall()

        return [
            PriceRecord(
                id=r["id"],
                source_id=r["source_id"],
                preco=r["preco"],
                preco_original=r["preco_original"],
                moeda=r["moeda"],
                disponivel=bool(r["disponivel"]),
                cupom=r["cupom"],
                titulo_coletado=r["titulo_coletado"],
                url_encontrada=r["url_encontrada"],
                coletado_em=datetime.fromisoformat(r["coletado_em"]),
            )
            for r in rows
        ]

    def get_recent_alerts(self, product_id: str, limit: int = 10) -> list[Alert]:
        """Retorna os últimos N alertas de um produto."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, product_id, price_record_id, motivo, detalhes, enviado_em, canal
                FROM alerts
                WHERE product_id = ?
                ORDER BY enviado_em DESC
                LIMIT ?
                """,
                (product_id, limit),
            ).fetchall()

        return [
            Alert(
                id=r["id"],
                product_id=r["product_id"],
                price_record_id=r["price_record_id"],
                motivo=r["motivo"],
                detalhes=r["detalhes"],
                enviado_em=datetime.fromisoformat(r["enviado_em"]),
                canal=r["canal"],
            )
            for r in rows
        ]

