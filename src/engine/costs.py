"""거래 비용 모델: 수수료, 증권거래세, 슬리피지, 환전 스프레드."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    buy_fee: float = 0.0        # 매수 수수료율
    sell_fee: float = 0.0       # 매도 수수료율
    sell_tax: float = 0.0       # 증권거래세율 (매도 시)
    slippage: float = 0.0       # 슬리피지 (매수/매도 각각 적용)
    fx_spread: float = 0.0      # 환전 스프레드 (해외 종목, 왕복 절반씩)

    def buy_cost_rate(self) -> float:
        """매수 시 총 비용률 (체결가 대비)."""
        return self.buy_fee + self.slippage + self.fx_spread / 2

    def sell_cost_rate(self) -> float:
        """매도 시 총 비용률 (체결가 대비)."""
        return self.sell_fee + self.sell_tax + self.slippage + self.fx_spread / 2

    def apply_buy(self, amount: float) -> float:
        """투자금 amount로 실제 매수 가능한 순금액."""
        return amount * (1.0 - self.buy_cost_rate())

    def apply_sell(self, gross: float) -> float:
        """매도 대금 gross에서 비용 차감 후 수령액."""
        return gross * (1.0 - self.sell_cost_rate())


# 현실적 기본값 (명세서 4.3)
KOREA_DEFAULT = CostModel(buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0018, slippage=0.0005)
US_DEFAULT = CostModel(buy_fee=0.0, sell_fee=0.0, sell_tax=0.0, slippage=0.0003, fx_spread=0.001)
ZERO_COST = CostModel()


def default_for_market(market: str) -> CostModel:
    if market.upper() in ("KOSPI", "KOSDAQ", "KRX"):
        return KOREA_DEFAULT
    return US_DEFAULT
