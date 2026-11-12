"""Price analyst subagent for deal evaluation and discount verification."""

from loguru import logger

from src.core.ports.analyst_port import IAnalyst
from src.core.ports.matcher_port import IProductMatcher
from src.core.ports.repository_port import IRepository
from src.data.models import (
    Coupon,
    DealAnalysis,
    PriceRecord,
    Product,
    ScrapedData,
    Source,
)
from src.data.repository import Repository
from src.skills.detect_fake_discount.detector import DetectFakeDiscountSkill
from src.skills.parse_coupon.parser import ParseCouponSkill
from src.skills.price_statistics.analyzer import PriceStatisticsSkill
from src.subagents.base import BaseSubagent
from src.subagents.matcher.hybrid_matcher import default_matcher


class PriceAnalystSubagent(BaseSubagent, IAnalyst):
    """Subagente responsável por normalizar, persistir e analisar ofertas com base no histórico."""

    name = "price_analyst_agent"
    role = "Price & Deal Analyst"

    def __init__(
        self,
        repository: IRepository | None = None,
        matcher: IProductMatcher | None = None,
        statistics_skill: PriceStatisticsSkill | None = None,
    ):
        self.repository = repository or Repository()
        self.matcher = matcher or default_matcher
        self.fake_discount_detector = DetectFakeDiscountSkill()
        self.statistics_skill = statistics_skill or PriceStatisticsSkill()

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
        history_records = self.repository.get_price_history(product.id, days=90)
        hist_prices = [r.preco for r in history_records if r.preco is not None and r.preco > 0]
        hist_dates = [r.coletado_em for r in history_records if r.preco is not None and r.preco > 0]

        for source, scraped in scraped_results:
            if not scraped.success or scraped.preco is None:
                continue

            # 2a. Deduplicação semântica de variantes (antes de persistir para não poluir histórico com acessórios)
            if scraped.titulo:
                match_result = await self.matcher.match(
                    target=product,
                    candidate_title=scraped.titulo,
                    candidate_url=scraped.url,
                )
            else:
                from src.data.models import MatchResult
                match_result = MatchResult(is_match=True, confidence=1.0, method_used="empty_title_passthrough")

            # Proteção contra falsos positivos de peças/acessórios muito baratos (< 30% do alvo)
            is_implausibly_cheap = bool(
                product.preco_alvo > 0 and scraped.preco < (product.preco_alvo * 0.30)
            )

            # 2b. Persistir registro de preço apenas quando compatível e plausível
            saved_record_id: int | None = None
            if match_result.is_match and not is_implausibly_cheap:
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
                saved = self.repository.save_price_record(record)
                saved_record_id = saved.id if saved else record.id

            # 2c. Detecção e persistência de cupom promocional
            parsed_coupon: Coupon | None = None
            preco_efetivo = scraped.preco
            if scraped.cupom and match_result.is_match and not is_implausibly_cheap:
                parsed_coupon = ParseCouponSkill.parse(
                    raw_text=scraped.cupom,
                    marketplace=source.marketplace,
                    product_id=product.id,
                )
                if parsed_coupon:
                    if hasattr(self.repository, "save_coupon"):
                        self.repository.save_coupon(parsed_coupon)
                    if parsed_coupon.desconto_percentual:
                        preco_efetivo = scraped.preco * (1.0 - (parsed_coupon.desconto_percentual / 100.0))
                    elif parsed_coupon.desconto_fixo:
                        preco_efetivo = max(0.0, scraped.preco - parsed_coupon.desconto_fixo)

            # 3. Analisar condições de promoção, desconto real e estatística de série temporal
            announced_disc, real_disc, is_fake = self.fake_discount_detector.execute(
                current_price=scraped.preco,
                original_price_announced=scraped.preco_original,
                historical_avg=prev_avg,
                user_max_price=product.preco_maximo,
            )

            # Cálculo de Métricas de Ciência de Dados sobre a série temporal
            stat_profile = self.statistics_skill.execute(
                historical_prices=hist_prices,
                current_price=scraped.preco,
                historical_dates=hist_dates,
                target_price=product.preco_alvo,
                user_max_price=product.preco_maximo,
                is_fake_discount=is_fake,
            )

            # Condições de compra vantajosa
            is_below_target = scraped.preco <= product.preco_alvo or preco_efetivo <= product.preco_alvo
            is_all_time_low = prev_min is not None and (scraped.preco < prev_min or preco_efetivo < prev_min)
            is_below_max = scraped.preco <= product.preco_maximo or preco_efetivo <= product.preco_maximo
            is_stat_anomaly = (
                stat_profile.robust_z_score <= -1.8
                and stat_profile.sample_size >= 3
                and not is_fake
            )

            # Decisão de Deal (somente se a variante for compatível e preço plausível)
            is_deal = False
            motivo = None
            justificativa_parts = []

            if not match_result.is_match:
                logger.info(
                    f"[{source.marketplace.upper()}] Anúncio desconsiderado para deal: {match_result.divergence_reason}"
                )
                justificativa_parts.append(
                    f"Variante divergente desconsiderada: {match_result.divergence_reason}."
                )
            elif is_implausibly_cheap:
                logger.info(
                    f"[{source.marketplace.upper()}] Preço suspeito/acessório ignorado: R$ {scraped.preco:.2f}"
                )
                justificativa_parts.append(
                    f"Cotação ignorada (R$ {scraped.preco:.2f} < 30% do alvo — provável acessório/peça)."
                )
            elif scraped.disponivel and is_below_max:
                if is_all_time_low:
                    is_deal = True
                    motivo = "minimo_historico"
                    justificativa_parts.append(
                        f"Novo menor preço histórico (R$ {scraped.preco:.2f} < mínima anterior de R$ {prev_min:.2f})."
                    )
                elif is_below_target:
                    is_deal = True
                    if preco_efetivo <= product.preco_alvo and scraped.preco > product.preco_alvo and parsed_coupon:
                        motivo = "cupom_promocional"
                        justificativa_parts.append(
                            f"Cupom '{parsed_coupon.codigo}' reduz o preço para R$ {preco_efetivo:.2f}, atingindo seu alvo de compra (R$ {product.preco_alvo:.2f})."
                        )
                    else:
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
                elif parsed_coupon and (parsed_coupon.desconto_percentual or parsed_coupon.desconto_fixo):
                    is_deal = True
                    motivo = "cupom_promocional"
                    justificativa_parts.append(
                        f"Cupom promocional '{parsed_coupon.codigo}' detectado (preço c/ desconto: R$ {preco_efetivo:.2f})."
                    )
                elif is_stat_anomaly:
                    is_deal = True
                    motivo = "queda_anomala_estatistica"
                    justificativa_parts.append(
                        f"Queda estatisticamente anômala (Z-Score Robusto {stat_profile.robust_z_score:.2f}, "
                        f"Percentil {stat_profile.percentile_rank:.0f}% frente à mediana de R$ {stat_profile.median:.2f})."
                    )

            if stat_profile.sample_size >= 3 and stat_profile.robust_z_score <= -1.5 and not is_stat_anomaly:
                justificativa_parts.append(
                    f"Sinal estatístico: Z-Score Robusto {stat_profile.robust_z_score:.2f} (Percentil {stat_profile.percentile_rank:.0f}%)."
                )

            if parsed_coupon and not is_deal:
                justificativa_parts.append(f"Cupom disponível: {parsed_coupon.codigo}.")

            if is_fake:
                justificativa_parts.append(
                    "Alerta de 'metade do dobro': o preço original anunciado pelo site está inflado."
                )

            analysis = DealAnalysis(
                product_id=product.id,
                source_id=source.id if source.id else 0,
                price_record_id=saved_record_id,
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
                z_score=stat_profile.z_score,
                robust_z_score=stat_profile.robust_z_score,
                percentile_rank=stat_profile.percentile_rank,
                cv_volatilidade_percent=stat_profile.cv_percent,
                tendencia_diaria_brl=stat_profile.trend_slope_brl_per_day,
                regime_preco=stat_profile.regime_preco,
                deal_score=stat_profile.deal_confidence_score,
                match_confidence=match_result.confidence,
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
