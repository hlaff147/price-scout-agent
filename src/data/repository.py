"""Repository pattern for database operations in PromoRadar."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from loguru import logger

from src.core.ports.coupon_port import ICouponRepositoryPort
from src.core.ports.product_management_port import IProductManagementPort
from src.core.ports.repository_port import IRepository
from src.core.ports.selector_port import ISelectorRepositoryPort
from src.data.database import Database, default_db
from src.data.models import (
    Alert,
    Coupon,
    PriceRecord,
    PriorityLevel,
    Product,
    SelectorOverride,
    Source,
)


def calculate_next_run(product: Product, from_time: datetime | None = None) -> datetime:
    """Calcula o timestamp do próximo ciclo com base na prioridade ou intervalo customizado."""
    base_time = from_time or datetime.now(timezone.utc)
    if product.intervalo_customizado_min and product.intervalo_customizado_min > 0:
        return base_time + timedelta(minutes=product.intervalo_customizado_min)
    if product.prioridade == PriorityLevel.HIGH:
        return base_time + timedelta(hours=1)
    if product.prioridade == PriorityLevel.LOW:
        return base_time + timedelta(hours=12)
    # Padrão MEDIUM
    return base_time + timedelta(hours=4)


class Repository(IRepository, IProductManagementPort, ISelectorRepositoryPort, ICouponRepositoryPort):
    """Repositório de acesso aos dados de produtos, fontes, preços e alertas."""

    def __init__(self, db: Database | None = None):
        self.db = db or default_db

    # ------------------ Produtos ------------------ #

    def _row_to_product(self, row: sqlite3.Row, sources: list[Source]) -> Product:
        """Converte uma linha SQLite em instância tipada de Product."""
        row_keys = set(row.keys())
        p_raw = row["prioridade"] if "prioridade" in row_keys and row["prioridade"] else "medium"
        try:
            priority = PriorityLevel(p_raw)
        except ValueError:
            priority = PriorityLevel.MEDIUM

        ultimo_ciclo = None
        if "ultimo_ciclo_em" in row_keys and row["ultimo_ciclo_em"]:
            ultimo_ciclo = datetime.fromisoformat(row["ultimo_ciclo_em"])

        proximo_ciclo = None
        if "proximo_ciclo_em" in row_keys and row["proximo_ciclo_em"]:
            proximo_ciclo = datetime.fromisoformat(row["proximo_ciclo_em"])

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

    def upsert_product(self, product: Product) -> Product:
        """Insere ou atualiza um produto."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO products (
                    id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                    intervalo_customizado_min, ultimo_ciclo_em, proximo_ciclo_em, ativo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nome=excluded.nome,
                    keywords=excluded.keywords,
                    preco_alvo=excluded.preco_alvo,
                    preco_maximo=excluded.preco_maximo,
                    prioridade=excluded.prioridade,
                    intervalo_customizado_min=excluded.intervalo_customizado_min,
                    ultimo_ciclo_em=COALESCE(excluded.ultimo_ciclo_em, products.ultimo_ciclo_em),
                    proximo_ciclo_em=COALESCE(excluded.proximo_ciclo_em, products.proximo_ciclo_em),
                    ativo=excluded.ativo;
                """,
                (
                    product.id,
                    product.nome,
                    json.dumps(product.keywords, ensure_ascii=False),
                    product.preco_alvo,
                    product.preco_maximo,
                    product.prioridade.value if isinstance(product.prioridade, PriorityLevel) else str(product.prioridade),
                    product.intervalo_customizado_min,
                    product.ultimo_ciclo_em.isoformat() if product.ultimo_ciclo_em else None,
                    product.proximo_ciclo_em.isoformat() if product.proximo_ciclo_em else None,
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
                """
                SELECT id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                       intervalo_customizado_min, ultimo_ciclo_em, proximo_ciclo_em, ativo
                FROM products WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
            if not row:
                return None

            sources = self.get_sources_for_product(product_id)
            return self._row_to_product(row, sources)

    def list_active_products(self) -> list[Product]:
        """Lista todos os produtos ativos."""
        return self.list_products(active_only=True)

    def list_products(self, active_only: bool = True) -> list[Product]:
        """Lista produtos com filtro opcional de ativo."""
        query = (
            """
            SELECT id, nome, keywords, preco_alvo, preco_maximo, prioridade,
                   intervalo_customizado_min, ultimo_ciclo_em, proximo_ciclo_em, ativo
            FROM products
            """
        )
        if active_only:
            query += " WHERE ativo = 1"

        with self.db.get_connection() as conn:
            rows = conn.execute(query).fetchall()

        products = []
        for r in rows:
            sources = self.get_sources_for_product(r["id"])
            products.append(self._row_to_product(r, sources))
        return products

    def get_due_products(self) -> list[Product]:
        """Retorna produtos ativos que estão prontos para execução no ciclo atual."""
        now_iso = datetime.now(timezone.utc).isoformat()
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

        products = []
        for r in rows:
            sources = self.get_sources_for_product(r["id"])
            products.append(self._row_to_product(r, sources))
        return products

    def update_product_schedule(
        self, product_id: str, last_run: datetime, next_run: datetime
    ) -> None:
        """Atualiza os horários de último e próximo ciclo."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                UPDATE products
                SET ultimo_ciclo_em = ?, proximo_ciclo_em = ?
                WHERE id = ?
                """,
                (last_run.isoformat(), next_run.isoformat(), product_id),
            )

    def set_product_priority(self, product_id: str, priority: PriorityLevel) -> bool:
        """Altera a prioridade de um produto."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE products SET prioridade = ? WHERE id = ?",
                (priority.value if isinstance(priority, PriorityLevel) else str(priority), product_id),
            )
            return cursor.rowcount > 0

    def set_product_active(self, product_id: str, active: bool) -> bool:
        """Ativa ou desativa um produto."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE products SET ativo = ? WHERE id = ?",
                (1 if active else 0, product_id),
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

    # ------------------ Seletores e Self-Healing ------------------ #

    def get_active_overrides(self, marketplace: str) -> dict[str, str]:
        """Retorna os seletores ativos para o marketplace (target_field -> selector)."""
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
        """Salva ou atualiza um seletor reparado."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO selector_overrides (
                    marketplace, target_field, original_selector, healed_selector,
                    confidence_score, status, sucessos_consecutivos, falhas_consecutivas
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(marketplace, target_field) DO UPDATE SET
                    original_selector=excluded.original_selector,
                    healed_selector=excluded.healed_selector,
                    confidence_score=excluded.confidence_score,
                    status=excluded.status,
                    sucessos_consecutivos=0,
                    falhas_consecutivas=0,
                    criado_em=CURRENT_TIMESTAMP;
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
                ),
            )
            if not override.id:
                override.id = cursor.lastrowid
        logger.info(
            f"Seletor '{override.target_field}' reparado para [{override.marketplace.upper()}]: "
            f"'{override.healed_selector}' (status={override.status})"
        )
        return override

    def record_healing_attempt(self, marketplace: str) -> None:
        """Registra uma tentativa de reparo para o circuito de segurança."""
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO healing_attempts (marketplace) VALUES (?)",
                (marketplace.lower(),),
            )

    def has_exceeded_healing_attempts(
        self, marketplace: str, max_attempts: int = 2, hours: int = 24
    ) -> bool:
        """Verifica se o limite de tentativas de reparo foi atingido (Circuit Breaker)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM healing_attempts WHERE marketplace = ? AND tentado_em >= ?",
                (marketplace.lower(), cutoff),
            ).fetchone()
            return bool(row and row["count"] >= max_attempts)

    # ------------------ Cupons e Promoções ------------------ #

    def save_coupon(self, coupon: Coupon) -> Coupon:
        """Salva ou atualiza um cupom no banco de dados."""
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
                    coupon.valido_ate.isoformat() if coupon.valido_ate else None,
                    coupon.primeira_vez_visto.isoformat() if coupon.primeira_vez_visto else datetime.now(timezone.utc).isoformat(),
                    coupon.ultimo_visto.isoformat() if coupon.ultimo_visto else datetime.now(timezone.utc).isoformat(),
                    1 if coupon.ativo else 0,
                ),
            )
            if not coupon.id:
                coupon.id = cursor.lastrowid
        logger.info(f"Cupom '{coupon.codigo}' registrado para [{coupon.marketplace.upper()}]")
        return coupon

    def get_coupon(self, marketplace: str, codigo: str) -> Coupon | None:
        """Busca um cupom específico por marketplace e código."""
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
                valido_ate=datetime.fromisoformat(r["valido_ate"]) if r["valido_ate"] else None,
                primeira_vez_visto=datetime.fromisoformat(r["primeira_vez_visto"]) if r["primeira_vez_visto"] else datetime.now(timezone.utc),
                ultimo_visto=datetime.fromisoformat(r["ultimo_visto"]) if r["ultimo_visto"] else datetime.now(timezone.utc),
                ativo=bool(r["ativo"]),
            )

    def list_active_coupons(self, marketplace: str | None = None) -> list[Coupon]:
        """Lista cupons ativos cadastrados, opcionalmente filtrados por marketplace."""
        query = "SELECT * FROM coupons WHERE ativo = 1"
        params: list[str] = []
        if marketplace:
            query += " AND marketplace = ?"
            params.append(marketplace.lower())
        query += " ORDER BY ultimo_visto DESC"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        coupons = []
        for r in rows:
            coupons.append(
                Coupon(
                    id=r["id"],
                    marketplace=r["marketplace"],
                    product_id=r["product_id"],
                    codigo=r["codigo"],
                    descricao=r["descricao"],
                    desconto_percentual=r["desconto_percentual"],
                    desconto_fixo=r["desconto_fixo"],
                    preco_minimo=r["preco_minimo"],
                    valido_ate=datetime.fromisoformat(r["valido_ate"]) if r["valido_ate"] else None,
                    primeira_vez_visto=datetime.fromisoformat(r["primeira_vez_visto"]) if r["primeira_vez_visto"] else datetime.now(timezone.utc),
                    ultimo_visto=datetime.fromisoformat(r["ultimo_visto"]) if r["ultimo_visto"] else datetime.now(timezone.utc),
                    ativo=bool(r["ativo"]),
                )
            )
        return coupons

    def is_coupon_recent(self, marketplace: str, codigo: str, hours: int = 24) -> bool:
        """Verifica se o cupom já foi visto nas últimas N horas."""
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



