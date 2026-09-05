"""Tests for SQLite database operations and repository."""

from datetime import datetime, timezone

from src.data.database import Database
from src.data.models import Alert, PriceRecord, Product, Source
from src.data.repository import Repository


class TestRepository:
    def test_product_crud_and_sources(self):
        db = Database(":memory:")
        repo = Repository(db)

        product = Product(
            id="p-1",
            nome="Huawei FreeBuds Pro 5",
            keywords=["Huawei", "FreeBuds Pro 5"],
            preco_alvo=850.0,
            preco_maximo=1100.0,
            sources=[
                Source(
                    product_id="p-1",
                    marketplace="mercadolivre",
                    url_produto="https://ml.com/test",
                )
            ],
        )

        # Upsert
        repo.upsert_product(product)

        # Retrieve
        fetched = repo.get_product("p-1")
        assert fetched is not None
        assert fetched.nome == "Huawei FreeBuds Pro 5"
        assert fetched.preco_alvo == 850.0
        assert len(fetched.sources) == 1
        assert fetched.sources[0].marketplace == "mercadolivre"

    def test_price_records_and_history(self):
        db = Database(":memory:")
        repo = Repository(db)

        product = Product(
            id="p-1",
            nome="Test Item",
            keywords=["Test"],
            preco_alvo=100.0,
            preco_maximo=200.0,
        )
        repo.upsert_product(product)
        source = repo.upsert_source(
            Source(product_id="p-1", marketplace="amazon", url_produto="https://amazon.com/item")
        )

        record1 = PriceRecord(
            source_id=source.id,
            preco=150.0,
            coletado_em=datetime.now(timezone.utc),
        )
        record2 = PriceRecord(
            source_id=source.id,
            preco=120.0,
            coletado_em=datetime.now(timezone.utc),
        )

        repo.save_price_record(record1)
        repo.save_price_record(record2)

        min_price = repo.get_historical_min_price("p-1")
        assert min_price == 120.0

        history = repo.get_price_history("p-1")
        assert len(history) == 2

    def test_alert_persistence_and_anti_spam(self):
        db = Database(":memory:")
        repo = Repository(db)

        product = Product(
            id="p-1",
            nome="Test Item",
            keywords=["Test"],
            preco_alvo=100.0,
            preco_maximo=200.0,
        )
        repo.upsert_product(product)
        source = repo.upsert_source(
            Source(product_id="p-1", marketplace="amazon", url_produto="https://amazon.com/item")
        )
        rec = repo.save_price_record(
            PriceRecord(source_id=source.id, preco=90.0, coletado_em=datetime.now(timezone.utc))
        )

        assert repo.has_recent_alert("p-1", hours=6) is False

        alert = Alert(
            product_id="p-1",
            price_record_id=rec.id,
            motivo="abaixo_do_alvo",
            canal="telegram",
        )
        repo.save_alert(alert)

        assert repo.has_recent_alert("p-1", hours=6) is True
