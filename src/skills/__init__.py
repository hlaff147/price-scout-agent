from src.skills.base import BaseSkill
from src.skills.detect_fake_discount.detector import DetectFakeDiscountSkill
from src.skills.format_alert.formatter import FormatAlertSkill
from src.skills.normalize_product.normalizer import NormalizeProductSkill
from src.skills.parse_aliexpress.parser import ParseAliExpressSkill
from src.skills.parse_amazon.parser import ParseAmazonSkill
from src.skills.parse_coupon.parser import ParseCouponSkill
from src.skills.parse_google_shopping.parser import ParseGoogleShoppingSkill
from src.skills.parse_kabum.parser import ParseKabumSkill
from src.skills.parse_mercadolivre.parser import ParseMercadoLivreSkill
from src.skills.parse_shopee.parser import ParseShopeeSkill

__all__ = [
    "BaseSkill",
    "DetectFakeDiscountSkill",
    "FormatAlertSkill",
    "NormalizeProductSkill",
    "ParseAliExpressSkill",
    "ParseAmazonSkill",
    "ParseCouponSkill",
    "ParseGoogleShoppingSkill",
    "ParseKabumSkill",
    "ParseMercadoLivreSkill",
    "ParseShopeeSkill",
]
