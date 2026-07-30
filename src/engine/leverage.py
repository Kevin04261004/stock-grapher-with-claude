"""레버리지 상품 시뮬레이션 (Phase 3) — 변동성 감쇄(volatility decay) 정량화.

일간 리밸런싱 구조를 그대로 재현한다. 실제 레버리지 ETF는
'기간 수익률 × 배율'이 아니라 '일간 수익률 × 배율'을 복리로 쌓는다.
"""
from __future__ import annotations

import numpy as np

from src.models import LeverageResult

TRADING_DAYS_PER_YEAR = 252


def simulate_leveraged(
    daily_returns: np.ndarray,
    leverage: float = 2.0,
    expense_ratio: float = 0.0064,   # 연 보수 0.64%
    financing_rate: float = 0.035,   # 차입 비용 연 3.5%
) -> np.ndarray:
    """일간 리밸런싱 레버리지 ETF의 누적 수익 경로 (1.0 시작)."""
    daily_returns = np.asarray(daily_returns, dtype=float)
    daily_cost = (expense_ratio + financing_rate * (leverage - 1.0)) / TRADING_DAYS_PER_YEAR
    lev_returns = daily_returns * leverage - daily_cost
    # 일간 -100% 초과 하락은 상품 가치 0으로 바닥 처리
    lev_returns = np.maximum(lev_returns, -1.0)
    return np.cumprod(1.0 + lev_returns)


def analyze_leverage(
    daily_returns: np.ndarray,
    leverage: float = 2.0,
    expense_ratio: float = 0.0064,
    financing_rate: float = 0.035,
) -> LeverageResult:
    """기초자산 vs 레버리지 상품 vs '감쇄 없는 가상 경로(기초 × 배율)' 비교."""
    daily_returns = np.asarray(daily_returns, dtype=float)
    base_path = np.cumprod(1.0 + daily_returns)
    lev_path = simulate_leveraged(daily_returns, leverage, expense_ratio, financing_rate)

    base_return = float(base_path[-1] - 1.0)
    lev_return = float(lev_path[-1] - 1.0)
    naive_return = base_return * leverage           # 흔한 오해: 기간수익률 × 배율
    naive_path = 1.0 + (base_path - 1.0) * leverage

    return LeverageResult(
        leverage=leverage,
        base_path=base_path,
        leveraged_path=lev_path,
        naive_path=naive_path,
        base_return=base_return,
        leveraged_return=lev_return,
        naive_return=naive_return,
        decay=float(naive_return - lev_return),
    )


def breakeven_required_gain(current_loss: float) -> float:
    """현재 손실률에서 본전 회복에 필요한 상승률.

    current_loss: 0.3 = -30% 손실 상태. 반환: 필요한 상승률 (0.4286 = +42.86%).
    """
    if not 0 <= current_loss < 1:
        raise ValueError("current_loss must be in [0, 1)")
    if current_loss == 0:
        return 0.0
    return current_loss / (1.0 - current_loss)


def breakeven_table(
    current_loss: float,
    leverage: float = 2.0,
    annual_vols: list[float] | None = None,
    expense_ratio: float = 0.0064,
    financing_rate: float = 0.035,
) -> list[dict]:
    """손익분기 계산기: 손실 X%에서 본전까지 기초자산이 얼마나 올라야 하는가.

    변동성이 있으면 감쇄 때문에 '필요 상승률 / 배율'보다 훨씬 더 올라야 한다.
    변동성·연간 시나리오별로 필요 기초자산 상승률을 수치 탐색.
    """
    if annual_vols is None:
        annual_vols = [0.10, 0.20, 0.30, 0.40]
    horizon_years = [0.5, 1.0, 2.0, 3.0]
    rows = []
    rng = np.random.default_rng(42)  # 재현 가능한 시나리오
    for vol in annual_vols:
        for years in horizon_years:
            n = int(TRADING_DAYS_PER_YEAR * years)
            daily_vol = vol / np.sqrt(TRADING_DAYS_PER_YEAR)
            # 필요 기초 상승률을 이분 탐색 (몬테카를로 평균 경로 사용)
            sims = 200
            noise = rng.standard_normal((sims, n)) * daily_vol

            def lev_final(base_total_return: float) -> float:
                mu = (np.log1p(base_total_return)) / n + 0.5 * daily_vol**2
                daily = np.expm1(mu + noise - 0.5 * daily_vol**2)
                finals = [
                    simulate_leveraged(d, leverage, expense_ratio, financing_rate)[-1]
                    for d in daily
                ]
                return float(np.mean(finals))

            lo, hi = 0.0, 5.0
            target = 1.0 / (1.0 - current_loss)  # 레버리지 상품이 회복해야 할 배수
            for _ in range(30):
                mid = (lo + hi) / 2
                if lev_final(mid) < target:
                    lo = mid
                else:
                    hi = mid
            rows.append(
                {
                    "annual_vol": vol,
                    "years": years,
                    "required_base_gain": (lo + hi) / 2,
                    "naive_required": breakeven_required_gain(current_loss) / leverage,
                }
            )
    return rows
