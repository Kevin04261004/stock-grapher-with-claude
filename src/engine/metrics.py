"""수익률 지표 계산 모듈.

모든 함수는 순수 함수이며 UI 의존성이 없다.
수익률 계산은 항상 수정주가(adj_close) 기준 시계열을 입력으로 받는다.
"""
from __future__ import annotations

from datetime import date

import numpy as np

TRADING_DAYS_PER_YEAR = 252


def total_return(values: np.ndarray) -> float:
    """단순 총수익률. values[0] 대비 values[-1]의 변화율."""
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or values[0] == 0:
        return 0.0
    return float(values[-1] / values[0] - 1.0)


def cagr(start_value: float, end_value: float, years: float) -> float:
    """연평균 복리 수익률. 적립식(현금흐름 다회)에는 사용 금지 — xirr 사용."""
    if start_value <= 0 or end_value <= 0 or years <= 0:
        return 0.0
    return float((end_value / start_value) ** (1.0 / years) - 1.0)


def max_drawdown(values: np.ndarray) -> tuple[float, np.ndarray]:
    """최대 낙폭(MDD)과 낙폭 시계열을 반환.

    반환값 mdd는 음수(예: -0.35 = 고점 대비 -35%).
    """
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return 0.0, np.array([])
    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1.0
    return float(drawdowns.min()), drawdowns


def annualized_volatility(daily_returns: np.ndarray) -> float:
    """연환산 변동성 = std(daily) * sqrt(252)."""
    daily_returns = np.asarray(daily_returns, dtype=float)
    if len(daily_returns) < 2:
        return 0.0
    return float(np.std(daily_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe_ratio(daily_returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
    """샤프 지수. risk_free_rate는 연율 (예: 0.03 = 3%)."""
    daily_returns = np.asarray(daily_returns, dtype=float)
    if len(daily_returns) < 2:
        return 0.0
    excess = daily_returns - risk_free_rate / TRADING_DAYS_PER_YEAR
    std = np.std(excess, ddof=1)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(daily_returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
    """소르티노 지수. 하방 변동성만 분모에 반영."""
    daily_returns = np.asarray(daily_returns, dtype=float)
    if len(daily_returns) < 2:
        return 0.0
    excess = daily_returns - risk_free_rate / TRADING_DAYS_PER_YEAR
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("inf")
    downside_std = np.sqrt(np.mean(downside**2))
    if downside_std == 0:
        return 0.0
    return float(np.mean(excess) / downside_std * np.sqrt(TRADING_DAYS_PER_YEAR))


def xirr(cashflows: list[tuple[date, float]]) -> float:
    """내부수익률(연환산). 적립식처럼 현금흐름이 여러 번인 경우의 주 지표.

    cashflows: [(날짜, 금액)] — 투자(유출)는 음수, 회수/최종평가액은 양수.
    return: 연환산 수익률 (0.15 = 15%). Excel XIRR()와 소수점 4자리 일치.
    """
    if len(cashflows) < 2:
        raise ValueError("XIRR requires at least 2 cashflows")
    has_neg = any(cf < 0 for _, cf in cashflows)
    has_pos = any(cf > 0 for _, cf in cashflows)
    if not (has_neg and has_pos):
        raise ValueError("XIRR requires both negative and positive cashflows")

    cashflows = sorted(cashflows, key=lambda x: x[0])
    t0 = cashflows[0][0]
    times = np.array([(d - t0).days / 365.0 for d, _ in cashflows])
    if times.max() == 0:
        raise ValueError("XIRR requires cashflows spanning more than one day")
    amounts = np.array([cf for _, cf in cashflows], dtype=float)

    def npv(rate: float) -> float:
        return float(np.sum(amounts / (1.0 + rate) ** times))

    from scipy.optimize import brentq

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    # 브래킷 확장: 극단적 수익률 대응
    while f_lo * f_hi > 0 and hi < 1e6:
        hi *= 10
        f_hi = npv(hi)
    if f_lo * f_hi > 0:
        raise ValueError("XIRR did not converge: no sign change in bracket")
    return float(brentq(npv, lo, hi, xtol=1e-10))
