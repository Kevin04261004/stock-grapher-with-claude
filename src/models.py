"""공용 데이터클래스 정의."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd


@dataclass
class Ticker:
    ticker: str
    name: str
    market: str          # KOSPI / KOSDAQ / NASDAQ / NYSE / ETF / INDEX
    currency: str        # KRW / USD
    sector: str | None = None
    listed_date: date | None = None
    delisted_date: date | None = None  # None이면 상장 유지


@dataclass
class BacktestResult:
    ticker: str
    buy_date: date
    sell_date: date
    invested: float
    final_value: float
    total_return: float
    cagr: float
    mdd: float
    volatility: float
    sharpe: float
    period_high: float
    period_low: float
    equity_curve: pd.Series = field(repr=False)          # 날짜별 평가액
    drawdown_curve: pd.Series = field(repr=False)        # 날짜별 낙폭
    forced_liquidation: bool = False                     # 상장폐지로 강제 청산 여부


@dataclass
class DCAResult:
    ticker: str
    total_invested: float
    final_value: float
    xirr: float
    avg_buy_price: float
    final_price: float
    n_purchases: int
    shares: float
    invested_curve: pd.Series = field(repr=False)        # 누적 투입금
    value_curve: pd.Series = field(repr=False)           # 누적 평가액
    purchases: list[tuple[date, float, float]] = field(default_factory=list, repr=False)
    # (체결일, 체결가, 매수 수량)
    lump_sum_final_value: float = 0.0                    # 동일 총액 일시불 비교
    lump_sum_return: float = 0.0


@dataclass
class DistributionResult:
    ticker: str
    holding_days: int
    n_windows: int
    returns: np.ndarray = field(repr=False)              # 모든 시작일의 수익률
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0
    loss_probability: float = 0.0                        # 수익률 < 0 비율
    worst_5pct: float = 0.0                              # 하위 5% 분위수


@dataclass
class LeverageResult:
    leverage: float
    base_path: np.ndarray = field(repr=False)            # 기초자산 누적 경로 (1.0 시작)
    leveraged_path: np.ndarray = field(repr=False)       # 레버리지 상품 누적 경로
    naive_path: np.ndarray = field(repr=False)           # 기초자산 수익률 × 배율 (감쇄 없는 가상 경로)
    base_return: float = 0.0
    leveraged_return: float = 0.0
    naive_return: float = 0.0
    decay: float = 0.0                                   # naive 대비 실제 성과 괴리
