"""진입 시점 분포 분석 (Phase 3) — 체리피킹 구조적 차단.

"이 종목을 N일(개월) 보유했다면?"을 과거 모든 가능한 시작일에 대해 실행.
numpy 벡터화로 O(1) 수준 처리 (루프 없음).
"""
from __future__ import annotations

import numpy as np

from src.models import DistributionResult

TRADING_DAYS_PER_MONTH = 21


def rolling_returns(adj_close: np.ndarray, holding_days: int) -> np.ndarray:
    """모든 시작 인덱스에 대한 holding_days 보유 수익률 (벡터화).

    returns[i] = adj_close[i + holding_days] / adj_close[i] - 1
    """
    adj_close = np.asarray(adj_close, dtype=float)
    n = len(adj_close)
    if holding_days <= 0 or holding_days >= n:
        return np.array([])
    return adj_close[holding_days:] / adj_close[:-holding_days] - 1.0


def analyze_distribution(
    adj_close: np.ndarray, ticker: str, holding_days: int
) -> DistributionResult:
    """보유기간 수익률 분포 통계."""
    rets = rolling_returns(adj_close, holding_days)
    if len(rets) == 0:
        raise ValueError("holding period longer than available history")
    return DistributionResult(
        ticker=ticker,
        holding_days=holding_days,
        n_windows=len(rets),
        returns=rets,
        mean=float(np.mean(rets)),
        median=float(np.median(rets)),
        std=float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0,
        loss_probability=float(np.mean(rets < 0)),
        worst_5pct=float(np.percentile(rets, 5)),
    )


def loss_probability_curve(
    adj_close: np.ndarray, months_range: list[int] | None = None
) -> list[tuple[int, float, int]]:
    """보유기간(개월)별 손실확률 곡선. 반환: [(개월, 손실확률, 표본수)]."""
    if months_range is None:
        months_range = [1, 3, 6, 12, 24, 36, 60, 84, 120]
    out = []
    n = len(adj_close)
    for m in months_range:
        days = m * TRADING_DAYS_PER_MONTH
        if days >= n:
            break
        rets = rolling_returns(adj_close, days)
        out.append((m, float(np.mean(rets < 0)), len(rets)))
    return out
