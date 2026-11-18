"""Repository pattern for SQLite persistence with canonical UTC timestamps and N+1 prevention."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from loguru import logger

from src.core.models import (
    Alert,
    Coupon,
    PriceRecord,
    PriorityLevel,
    Product,
    SelectorOverride,
    Source,
)
from src.core.ports.coupon_port import ICouponRepositoryPort
from src.core.ports.product_management_port import IProductManagementPort
from src.core.ports.repository_port import IRepository
from src.core.ports.selector_port import ISelectorRepositoryPort
from src.data.database import Database, default_db


def utc_now_iso() -> str:
    """Retorna o timestamp atual em formato ISO-8601 UTC canônico uniforme."""
    return datetime.now(timezone.utc).isoformat()


def ensure_utc_iso(dt: datetime | None) -> str | None:
    """Normaliza um datetime para ISO-8601 UTC explícito."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def parse_utc_datetime(raw: str | None) -> datetime | None:
    """Converte string ISO/SQLite em datetime timezone-aware UTC."""
    if not raw:
        return None
    normalized = raw.replace(" ", "T") if " " in raw and "T" not in raw else raw
    dt = datetime.fromisoformat(normalized)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def calculate_next_run(product: Product, from_time: datetime | None = None) -> datetime:
    """Calcula o timestamp do próximo ciclo com base na prioridade ou intervalo customizado."""
    base_time = from_time or datetime.now(timezone.utc)
    if product.intervalo_customizado_min and product.intervalo_customizado_min > 0:
        return base_time + timedelta(minutes=product.intervalo_customizado_min)
    if product.prioridade == PriorityLevel.HIGH:
        return base_time + timedelta(hours=1)
    if product.prioridade == PriorityLevel.LOW:
        return base_time + timedelta(hours=12)
    return base_time + timedelta(hours=4)


class Repository(
    IRepository,
    IProductManagementPort,
    ISelectorRepositoryPort,
    ICouponRepositoryPort,
):
    """Repositório unificado de produtos, fontes, séries de preços, alertas, seletores e cupons."""

    def __init__(self, db: Database | None = None):
        self.db = db or default_db

    # ------------------ Produtos ------------------ #

    def _row_to_product(self, row: sqlite3.Row, sources: list[Source]) -> Product:
        row_keys = set(row.keys())
        p_raw = row["prioridade"] if "prioridade" in row_keys and row["prioridade"] else "medium"
        try:
            priority = PriorityLevel(p_raw)
        except ValueError:
            priority = PriorityLevel.MEDIUM

        ultimo_ciclo = (
            parse_utc_datetime(row["ultimo_ciclo_em"])
            if "ultimo_ciclo_em" in row_keys and row["ultimo_ciclo_em"]
            else None
        )
        proximo_ciclo = (
            parse_utc_datetime(row["proximo_ciclo_em"])
            if "proximo_ciclo_em" in row_keys and row["proximo_ciclo_em"]
            else None
        )
        intervalo_custom = (
            row["intervalo_customizado_min"]
            if "intervalo_customizado_min" in row_keys
            else None
        )

        return Product(
            id=row["id"],
            nome=row["nome"],
            keywords=json.loads(row["keywords"]),
            preco_alvo=row["preco_alvo"],
            preco_maximo=row["preco_maximo"],
            prioridade=priority,
            intervalo_customizado_min=intervalo_custom,
            ultimo_ciclo_em=ultimo_ciclo,
            proximo_ciclo_em=proximo_ciclo,
            ativo=bool(row["ativo"]),
            sources=sources,
        )

    def _load_sources_grouped(
        self, conn: sqlite3.Connection, product_ids: list[str]
    ) -> dict[str, list[Source]]:
        """Carrega fontes em lote em uma única query (elimina N+1 em listagens)."""
        grouped: dict[str, list[Source]] = defaultdict(list)
        if not product_ids:
            return grouped

        placeholders = ",".join("?" for _ in product_ids)
        rows = conn.execute(
            f"""
            SELECT id, product_id, marketplace, url_produto, metodo_coleta, ativo, motivo_desativacao
            FROM sources
            WHERE product_id IN ({placeholders})
            ORDER BY id ASC
            """,
            product_ids,
        ).fetchall()

        for r in rows:
            grouped[r["product_id"]].append(
                Source(
                    id=r["id"],
                    product_id=r["product_id"],
                    marketplace=r["marketplace"],
                    url_produto=r["url_produto"],
                    metodo_coleta=r["metodo_coleta"],
                    ativo=bool(r["ativo"]),
                    motivo_desativacao=r["motivo_desativacao"],
                )
            )
        return grouped

    def upsert_product(self, product: Product) -> Product:
        """Insere ou atualiza explicitamente um produto (ex.: comando administrativo `/add` ou testes)."""
        return self._upsert_product_internal(product, preserve_runtime_overrides=False)

    def sync_catalog_product(self, product: Product) -> Product:
        """Sincroniza metadados de catálogo YAML sem sobrescrever `/pause`, `/resume` ou `/priority`."""
        return self._upsert_product_internal(product, preserve_runtime_overrides=True)

    def _upsert_product_internal(
        self, product: Product, *, preserve_runtime_overrides: bool
    ) -> Product:
        prio_str = (
            product.prioridade.value
            if isinstance(product.prioridade, PriorityLevel)
            else str(product.prioridade)
        )
        with self.db.get_connection() as conn:
            if preserve_runtime_overrides:
                conn.execute(
                    """
                    INSERT INTO products (
                        id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                        prioridade_manual, intervalo_customizado_min, ultimo_ciclo_em,
                        proximo_ciclo_em, ativo, ativo_manual
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, NULL)
                    ON CONFLICT(id) DO UPDATE SET
                        nome=excluded.nome,
                        keywords=excluded.keywords,
                        preco_alvo=excluded.preco_alvo,
                        preco_maximo=excluded.preco_maximo,
                        prioridade=CASE
                            WHEN products.prioridade_manual = 1 THEN products.prioridade
                            ELSE excluded.prioridade
                        END,
                        intervalo_customizado_min=excluded.intervalo_customizado_min,
                        ultimo_ciclo_em=COALESCE(excluded.ultimo_ciclo_em, products.ultimo_ciclo_em),
                        proximo_ciclo_em=COALESCE(excluded.proximo_ciclo_em, products.proximo_ciclo_em),
                        ativo=CASE
                            WHEN products.ativo_manual IS NOT NULL THEN products.ativo_manual
                            ELSE excluded.ativo
                        END;
                    """,
                    (
                        product.id,
                        product.nome,
                        json.dumps(product.keywords, ensure_ascii=False),
                        product.preco_alvo,
                        product.preco_maximo,
                        prio_str,
                        product.intervalo_customizado_min,
                        ensure_utc_iso(product.ultimo_ciclo_em),
                        ensure_utc_iso(product.proximo_ciclo_em),
                        1 if product.ativo else 0,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO products (
                        id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                        prioridade_manual, intervalo_customizado_min, ultimo_ciclo_em,
                        proximo_ciclo_em, ativo, ativo_manual
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, NULL)
                    ON CONFLICT(id) DO UPDATE SET
                        nome=excluded.nome,
                        keywords=excluded.keywords,
                        preco_alvo=excluded.preco_alvo,
                        preco_maximo=excluded.preco_maximo,
                        prioridade=excluded.prioridade,
                        prioridade_manual=0,
                        intervalo_customizado_min=excluded.intervalo_customizado_min,
                        ultimo_ciclo_em=COALESCE(excluded.ultimo_ciclo_em, products.ultimo_ciclo_em),
                        proximo_ciclo_em=COALESCE(excluded.proximo_ciclo_em, products.proximo_ciclo_em),
                        ativo=excluded.ativo,
                        ativo_manual=NULL;
                    """,
                    (
                        product.id,
                        product.nome,
                        json.dumps(product.keywords, ensure_ascii=False),
                        product.preco_alvo,
                        product.preco_maximo,
                        prio_str,
                        product.intervalo_customizado_min,
                        ensure_utc_iso(product.ultimo_ciclo_em),
                        ensure_utc_iso(product.proximo_ciclo_em),
                        1 if product.ativo else 0,
                    ),
                )

            for src in product.sources:
                src.product_id = product.id
                self._upsert_source_with_conn(conn, src)

        return product

    def get_product(self, product_id: str) -> Product | None:
        """Recupera um produto com suas fontes em uma única conexão."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                       intervalo_customizado_min, ultimo_ciclo_em, proximo_ciclo_em, ativo
                FROM products WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
            if not row:
                return None

            sources_map = self._load_sources_grouped(conn, [product_id])
            return self._row_to_product(row, sources_map.get(product_id, []))

    def list_active_products(self) -> list[Product]:
        return self.list_products(active_only=True)

    def list_products(self, active_only: bool = True) -> list[Product]:
        """Lista produtos e suas fontes em exatamente 2 queries (zero N+1)."""
        query = """
            SELECT id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                   intervalo_customizado_min, ultimo_ciclo_em, proximo_ciclo_em, ativo
            FROM products
        """
        if active_only:
            query += " WHERE ativo = 1"

        with self.db.get_connection() as conn:
            rows = conn.execute(query).fetchall()
            pids = [r["id"] for r in rows]
            sources_map = self._load_sources_grouped(conn, pids)

        return [self._row_to_product(r, sources_map.get(r["id"], [])) for r in rows]

    def get_due_products(self) -> list[Product]:
        """Retorna produtos ativos prontos para execução com carregamento batch de fontes."""
        now_iso = utc_now_iso()
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                       intervalo_customizado_min, ultimo_ciclo_em, proximo_ciclo_em, ativo
                FROM products
                WHERE ativo = 1 AND (proximo_ciclo_em IS NULL OR proximo_ciclo_em <= ?)
                ORDER BY
                    CASE prioridade
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                    END ASC,
                    proximo_ciclo_em ASC NULLS FIRST
                """,
                (now_iso,),
            ).fetchall()
            pids = [r["id"] for r in rows]
            sources_map = self._load_sources_grouped(conn, pids)

        return [self._row_to_product(r, sources_map.get(r["id"], [])) for r in rows]

    def update_product_schedule(
        self, product_id: str, last_run: datetime, next_run: datetime
    ) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """
                UPDATE products
                SET ultimo_ciclo_em = ?, proximo_ciclo_em = ?
                WHERE id = ?
                """,
                (ensure_utc_iso(last_run), ensure_utc_iso(next_run), product_id),
            )

    def set_product_priority(self, product_id: str, priority: PriorityLevel) -> bool:
        """Altera a prioridade de um produto marcando override manual contra sobrescrita YAML."""
        prio_val = priority.value if isinstance(priority, PriorityLevel) else str(priority)
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE products SET prioridade = ?, prioridade_manual = 1 WHERE id = ?",
                (prio_val, product_id),
            )
            return cursor.rowcount > 0

    def set_product_active(self, product_id: str, active: bool) -> bool:
        """Ativa ou pausa um produto marcando override manual contra sobrescrita YAML."""
        flag = 1 if active else 0
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE products SET ativo = ?, ativo_manual = ? WHERE id = ?",
                (flag, flag, product_id),
            )
            return cursor.rowcount > 0

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
        with self.db.get_connection() as conn:
            return self._upsert_source_with_conn(conn, source)

    def get_sources_for_product(self, product_id: str) -> list[Source]:
        with self.db.get_connection() as conn:
            return self._load_sources_grouped(conn, [product_id]).get(product_id, [])

    def get_active_sources_for_product(self, product_id: str) -> list[Source]:
        return [s for s in self.get_sources_for_product(product_id) if s.ativo]

    # ------------------ Registros de Preço ------------------ #

    def save_price_record(self, record: PriceRecord) -> PriceRecord:
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
                    ensure_utc_iso(record.coletado_em) or utc_now_iso(),
                ),
            )
            record.id = cursor.lastrowid
        logger.debug(f"Preço registrado: R${record.preco:.2f} (source_id={record.source_id})")
        return record

    def get_price_history(self, product_id: str, days: int = 90) -> list[PriceRecord]:
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
                coletado_em=parse_utc_datetime(r["coletado_em"]) or datetime.now(timezone.utc),
            )
            for r in rows
        ]

    def get_historical_min_price(self, product_id: str) -> float | None:
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

    def get_historical_min_prices_map(self, product_ids: list[str]) -> dict[str, float | None]:
        """Consulta mínimas históricas em lote em uma única query (evita N+1 no `/list`)."""
        result: dict[str, float | None] = {pid: None for pid in product_ids}
        if not product_ids:
            return result
        placeholders = ",".join("?" for _ in product_ids)
        with self.db.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT s.product_id, MIN(pr.preco) as min_preco
                FROM price_records pr
                JOIN sources s ON s.id = pr.source_id
                WHERE s.product_id IN ({placeholders}) AND pr.disponivel = 1
                GROUP BY s.product_id
                """,
                product_ids,
            ).fetchall()
        for r in rows:
            if r["min_preco"] is not None:
                result[r["product_id"]] = float(r["min_preco"])
        return result

    def get_historical_average_price(self, product_id: str, days: int = 60) -> float | None:
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

    def get_price_history_by_source(self, source_id: int, days: int = 90) -> list[PriceRecord]:
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
                coletado_em=parse_utc_datetime(r["coletado_em"]) or datetime.now(timezone.utc),
            )
            for r in rows
        ]

    # ------------------ Alertas ------------------ #

    def save_alert(self, alert: Alert) -> Alert:
        with self.db.get_connection() as conn:
            valid_record_id = alert.price_record_id
            if valid_record_id is not None:
                exists = conn.execute(
                    "SELECT 1 FROM price_records WHERE id = ?",
                    (valid_record_id,),
                ).fetchone()
                if not exists:
                    valid_record_id = None

            cursor = conn.execute(
                """
                INSERT INTO alerts (product_id, price_record_id, motivo, detalhes, enviado_em, canal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.product_id,
                    valid_record_id,
                    alert.motivo,
                    alert.detalhes,
                    ensure_utc_iso(alert.enviado_em) or utc_now_iso(),
                    alert.canal,
                ),
            )
            alert.id = cursor.lastrowid
            alert.price_record_id = valid_record_id
        return alert

    def has_recent_alert(self, product_id: str, hours: int = 12) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM alerts WHERE product_id = ? AND enviado_em >= ?",
                (product_id, cutoff),
            ).fetchone()
            return bool(row and row["count"] > 0)

    def get_recent_alerts(self, product_id: str, limit: int = 10) -> list[Alert]:
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
                enviado_em=parse_utc_datetime(r["enviado_em"]) or datetime.now(timezone.utc),
                canal=r["canal"],
            )
            for r in rows
        ]

    # ------------------ Seletores e Self-Healing ------------------ #

    def get_active_overrides(self, marketplace: str) -> dict[str, str]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT target_field, healed_selector
                FROM selector_overrides
                WHERE marketplace = ? AND status = 'active'
                """,
                (marketplace.lower(),),
            ).fetchall()
        return {r["target_field"]: r["healed_selector"] for r in rows}

    def save_override(self, override: SelectorOverride) -> SelectorOverride:
        now_iso = ensure_utc_iso(override.criado_em) or utc_now_iso()
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO selector_overrides (
                    marketplace, target_field, original_selector, healed_selector,
                    confidence_score, status, sucessos_consecutivos, falhas_consecutivas, criado_em
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(marketplace, target_field) DO UPDATE SET
                    original_selector=excluded.original_selector,
                    healed_selector=excluded.healed_selector,
                    confidence_score=excluded.confidence_score,
                    status=excluded.status,
                    sucessos_consecutivos=0,
                    falhas_consecutivas=0,
                    criado_em=excluded.criado_em;
                """,
                (
                    override.marketplace.lower(),
                    override.target_field,
                    override.original_selector,
                    override.healed_selector,
                    override.confidence_score,
                    override.status,
                    override.sucessos_consecutivos,
                    override.falhas_consecutivas,
                    now_iso,
                ),
            )
            if not override.id:
                override.id = cursor.lastrowid
        logger.info(
            f"Seletor '{override.target_field}' reparado para [{override.marketplace.upper()}]: "
            f"'{override.healed_selector}' (status={override.status})"
        )
        return override

    def record_override_outcome(
        self, marketplace: str, *, success: bool, max_consecutive_failures: int = 3
    ) -> None:
        """Atualiza contadores de saúde e aplica auto-rollback após falhas consecutivas."""
        mkt = marketplace.lower()
        with self.db.get_connection() as conn:
            if success:
                conn.execute(
                    """
                    UPDATE selector_overrides
                    SET sucessos_consecutivos = sucessos_consecutivos + 1,
                        falhas_consecutivas = 0
                    WHERE marketplace = ? AND status = 'active'
                    """,
                    (mkt,),
                )
            else:
                conn.execute(
                    """
                    UPDATE selector_overrides
                    SET falhas_consecutivas = falhas_consecutivas + 1,
                        sucessos_consecutivos = 0,
                        status = CASE
                            WHEN falhas_consecutivas + 1 >= ? THEN 'rolled_back'
                            ELSE status
                        END
                    WHERE marketplace = ? AND status = 'active'
                    """,
                    (max_consecutive_failures, mkt),
                )

    def record_healing_attempt(self, marketplace: str) -> None:
        """Registra tentativa de reparo com timestamp ISO-8601 UTC canônico."""
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO healing_attempts (marketplace, tentado_em) VALUES (?, ?)",
                (marketplace.lower(), utc_now_iso()),
            )

    def has_exceeded_healing_attempts(
        self, marketplace: str, max_attempts: int = 2, hours: int = 24
    ) -> bool:
        """Verifica se o limite de tentativas de reparo foi atingido (Circuit Breaker preciso em qualquer janela)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM healing_attempts WHERE marketplace = ? AND tentado_em >= ?",
                (marketplace.lower(), cutoff),
            ).fetchone()
            return bool(row and row["count"] >= max_attempts)

    # ------------------ Cupons e Promoções ------------------ #

    def save_coupon(self, coupon: Coupon) -> Coupon:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO coupons (
                    marketplace, product_id, codigo, descricao,
                    desconto_percentual, desconto_fixo, preco_minimo,
                    valido_ate, primeira_vez_visto, ultimo_visto, ativo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(marketplace, codigo) DO UPDATE SET
                    product_id=COALESCE(excluded.product_id, coupons.product_id),
                    descricao=COALESCE(excluded.descricao, coupons.descricao),
                    desconto_percentual=COALESCE(excluded.desconto_percentual, coupons.desconto_percentual),
                    desconto_fixo=COALESCE(excluded.desconto_fixo, coupons.desconto_fixo),
                    preco_minimo=COALESCE(excluded.preco_minimo, coupons.preco_minimo),
                    valido_ate=COALESCE(excluded.valido_ate, coupons.valido_ate),
                    ultimo_visto=excluded.ultimo_visto,
                    ativo=excluded.ativo;
                """,
                (
                    coupon.marketplace.lower(),
                    coupon.product_id,
                    coupon.codigo.strip().upper(),
                    coupon.descricao,
                    coupon.desconto_percentual,
                    coupon.desconto_fixo,
                    coupon.preco_minimo,
                    ensure_utc_iso(coupon.valido_ate),
                    ensure_utc_iso(coupon.primeira_vez_visto) or utc_now_iso(),
                    ensure_utc_iso(coupon.ultimo_visto) or utc_now_iso(),
                    1 if coupon.ativo else 0,
                ),
            )
            if not coupon.id:
                coupon.id = cursor.lastrowid
        logger.info(f"Cupom '{coupon.codigo}' registrado para [{coupon.marketplace.upper()}]")
        return coupon

    def get_coupon(self, marketplace: str, codigo: str) -> Coupon | None:
        with self.db.get_connection() as conn:
            r = conn.execute(
                "SELECT * FROM coupons WHERE marketplace = ? AND codigo = ?",
                (marketplace.lower(), codigo.strip().upper()),
            ).fetchone()
            if not r:
                return None
            return Coupon(
                id=r["id"],
                marketplace=r["marketplace"],
                product_id=r["product_id"],
                codigo=r["codigo"],
                descricao=r["descricao"],
                desconto_percentual=r["desconto_percentual"],
                desconto_fixo=r["desconto_fixo"],
                preco_minimo=r["preco_minimo"],
                valido_ate=parse_utc_datetime(r["valido_ate"]),
                primeira_vez_visto=parse_utc_datetime(r["primeira_vez_visto"]) or datetime.now(timezone.utc),
                ultimo_visto=parse_utc_datetime(r["ultimo_visto"]) or datetime.now(timezone.utc),
                ativo=bool(r["ativo"]),
            )

    def list_active_coupons(self, marketplace: str | None = None) -> list[Coupon]:
        query = "SELECT * FROM coupons WHERE ativo = 1"
        params: list[str] = []
        if marketplace:
            query += " AND marketplace = ?"
            params.append(marketplace.lower())
        query += " ORDER BY ultimo_visto DESC"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            Coupon(
                id=r["id"],
                marketplace=r["marketplace"],
                product_id=r["product_id"],
                codigo=r["codigo"],
                descricao=r["descricao"],
                desconto_percentual=r["desconto_percentual"],
                desconto_fixo=r["desconto_fixo"],
                preco_minimo=r["preco_minimo"],
                valido_ate=parse_utc_datetime(r["valido_ate"]),
                primeira_vez_visto=parse_utc_datetime(r["primeira_vez_visto"]) or datetime.now(timezone.utc),
                ultimo_visto=parse_utc_datetime(r["ultimo_visto"]) or datetime.now(timezone.utc),
                ativo=bool(r["ativo"]),
            )
            for r in rows
        ]

    def is_coupon_recent(self, marketplace: str, codigo: str, hours: int = 24) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM coupons
                WHERE marketplace = ? AND codigo = ? AND ultimo_visto >= ?
                """,
                (marketplace.lower(), codigo.strip().upper(), cutoff),
            ).fetchone()
            return bool(row and row["count"] > 0)
