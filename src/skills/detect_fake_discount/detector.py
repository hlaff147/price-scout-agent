"""Fake discount detection and real discount calculation skill."""


from src.skills.base import BaseSkill


class DetectFakeDiscountSkill(BaseSkill):
    """Detecta inflação artificial de preços originais e calcula desconto real."""

    name = "detect_fake_discount"
    description = "Calcula desconto real e identifica promoções maquiadas ('metade do dobro')."

    def execute(
        self,
        current_price: float,
        original_price_announced: float | None,
        historical_avg: float | None,
        user_max_price: float | None = None,
    ) -> tuple[float | None, float | None, bool]:
        """Calcula descontos e indica se há indício de desconto inflado.
        
        Retorna:
            (desconto_anunciado_percent, desconto_real_percent, is_fake_discount)
        """
        # Desconto anunciado pela loja
        announced_discount = None
        if original_price_announced and original_price_announced > current_price:
            announced_discount = round(
                ((original_price_announced - current_price) / original_price_announced) * 100, 1
            )

        # Desconto real calculado contra a média histórica
        real_discount = None
        is_fake = False

        if historical_avg and historical_avg > 0:
            if current_price < historical_avg:
                real_discount = round(
                    ((historical_avg - current_price) / historical_avg) * 100, 1
                )

            # Heurística 1: Preço original anunciado mais de 35% acima da média histórica real
            if original_price_announced and original_price_announced > (historical_avg * 1.35):
                is_fake = True

        # Heurística 2: Preço original anunciado mais de 45% acima do teto máximo definido pelo usuário
        # (funciona mesmo sem histórico prévio, ex: 1º dia de execução)
        if (
            user_max_price
            and original_price_announced
            and original_price_announced > (user_max_price * 1.45)
        ):
            is_fake = True

        return announced_discount, real_discount, is_fake
