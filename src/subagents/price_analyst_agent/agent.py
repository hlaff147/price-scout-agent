"""Price analyst subagent for deal evaluation and discount verification."""

from loguru import logger

from src.core.ports.analyst_port import IAnalyst
from src.core.ports.repository_port import IRepository
from src.data.models import DealAnalysis, PriceRecord, Product, ScrapedData, Source
from src.data.repository import Repository
from src.skills.detect_fake_discount.detector import DetectFakeDiscountSkill
from src.subagents.base import BaseSubagent


class PriceAnalystSubagent(BaseSubagent, IAnalyst):
    """Subagente responsável por normalizar, persistir e analisar ofertas com base no histórico."""

    name = "price_analyst_agent"
    role = "Price & Deal Analyst"

    def __init__(self, repository: IRepository | None = None):
        self.repository = repository or Repository()
        self.fake_discount_detector = DetectFakeDiscountSkill()

    async def run(
        self,
        product: Product,
        scraped_results: list[tuple[Source, ScrapedData]],
    ) -> list[DealAnalysis]:
        """Processa os dados coletados, persiste registros e identifica oportunidades reais."""
        analyses: list[DealAnalysis] = []

        # 1. Congelar a linha de base histórica pré-ciclo (estável para todas as fontes do ciclo)
        prev_min = self.repository.get_historical_min_price(product.id)
        prev_avg = self.repository.get_historical_average_price(product.id, days=60)

        for source, scraped in scraped_results:
            if not scraped.success or scraped.preco is None:
                continue

            # 2. Persistir novo registro de preço
            record = PriceRecord(
                source_id=source.id if source.id else 0,
                preco=scraped.preco,
                preco_original=scraped.preco_original,
                moeda=scraped.moeda,
                disponivel=scraped.disponivel,
                cupom=scraped.cupom,
                titulo_coletado=scraped.titulo,
                url_encontrada=scraped.url,
            )
            self.repository.save_price_record(record)

            # 3. Analisar condições de promoção e desconto real
            announced_disc, real_disc, is_fake = self.fake_discount_detector.execute(
                current_price=scraped.preco,
                original_price_announced=scraped.preco_original,
                historical_avg=prev_avg,
                user_max_price=product.preco_maximo,
            )

            # Condições de compra vantajosa
            is_below_target = scraped.preco <= product.preco_alvo
            is_all_time_low = (prev_min is not None and scraped.preco < prev_min)
            is_below_max = scraped.preco <= product.preco_maximo

            # Decisão de Deal
            is_deal = False
            motivo = None
            justificativa_parts = []

            if scraped.disponivel and is_below_max:
                if is_all_time_low:
                    is_deal = True
                    motivo = "minimo_historico"
                    justificativa_parts.append(
                        f"Novo menor preço histórico (R$ {scraped.preco:.2f} < mínima anterior de R$ {prev_min:.2f})."
                    )
                elif is_below_target:
                    is_deal = True
                    motivo = "abaixo_do_alvo"
                    justificativa_parts.append(
                        f"Preço de R$ {scraped.preco:.2f} atingiu seu alvo de compra (R$ {product.preco_alvo:.2f})."
                    )
                elif real_disc and real_disc >= 15.0:
                    is_deal = True
                    motivo = "desconto_real"
                    justificativa_parts.append(
                        f"Desconto real de {real_disc:.1f}% em relação à média histórica recente."
                    )

            if is_fake:
                justificativa_parts.append(
                    "Alerta de 'metade do dobro': o preço original anunciado pelo site está inflado."
                )

            analysis = DealAnalysis(
                product_id=product.id,
                source_id=source.id if source.id else 0,
                marketplace=source.marketplace,
                preco_atual=scraped.preco,
                preco_original_anunciado=scraped.preco_original,
                preco_minimo_historico=prev_min,
                preco_medio_historico=prev_avg,
                desconto_anunciado_percent=announced_disc,
                desconto_real_percent=real_disc,
                is_fake_discount=is_fake,
                is_all_time_low=is_all_time_low,
                is_below_target=is_below_target,
                is_deal=is_deal,
                motivo_alerta=motivo,
                justificativa=" ".join(justificativa_parts) if justificativa_parts else "Preço regular de mercado.",
                url=scraped.url,
                cupom=scraped.cupom,
            )
            analyses.append(analysis)

            if is_deal:
                logger.success(
                    f"🎯 [OPORTUNIDADE] {product.nome} em {source.marketplace.upper()}: R$ {scraped.preco:.2f} ({motivo})"
                )
            else:
                logger.info(
                    f"ℹ️ [REGULAR] {product.nome} em {source.marketplace.upper()}: R$ {scraped.preco:.2f} (Alvo: R$ {product.preco_alvo:.2f})"
                )

        return analyses
