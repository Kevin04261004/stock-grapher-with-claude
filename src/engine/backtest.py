"""단일 종목 구간 백테스트 (Phase 1)."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.engine import metrics
from src.engine.costs import CostModel, ZERO_COST
from src.models import BacktestResult


def next_trading_day(prices: pd.DataFrame, target: date) -> date | None:
    """target 이후(포함) 첫 거래일. 휴장일이면 다음 영업일로 이월."""
    idx = prices.index
    ts = pd.Timestamp(target)
    pos = idx.searchsorted(ts)
    if pos >= len(idx):
        return None
    return idx[pos].date()


def run_backtest(
    prices: pd.DataFrame,
    ticker: str,
    buy_date: date,
    sell_date: date,
    amount: float,
    costs: CostModel = ZERO_COST,
    delisted_date: date | None = None,
) -> BacktestResult:
    """구간 백테스트.

    prices: DatetimeIndex + 'adj_close' 컬럼 필수.
    매수/매도일이 휴장일이면 다음 영업일로 이월.
    delisted_date가 구간 내에 있으면 상폐일 종가로 강제 청산.
    """
    if buy_date >= sell_date:
        raise ValueError("buy_date must be before sell_date")

    actual_buy = next_trading_day(prices, buy_date)
    if actual_buy is None:
        raise ValueError(f"no trading day on/after {buy_date}")

    forced = False
    if delisted_date is not None and delisted_date < sell_date:
        sell_date = delisted_date
        forced = True

    actual_sell = next_trading_day(prices, sell_date)
    if actual_sell is None or actual_sell > prices.index[-1].date():
        actual_sell = prices.index[-1].date()
    if forced:
        # 상폐일 이후 데이터가 없을 수 있으므로 마지막 거래일로 청산
        window = prices.loc[: pd.Timestamp(sell_date)]
        if len(window) > 0:
            actual_sell = window.index[-1].date()

    window = prices.loc[pd.Timestamp(actual_buy): pd.Timestamp(actual_sell)]
    if len(window) < 2:
        raise ValueError("not enough data in the selected period")

    adj = window["adj_close"].to_numpy(dtype=float)

    buy_price = adj[0]
    net_invest = costs.apply_buy(amount)
    shares = net_invest / buy_price

    equity = shares * adj
    # 마지막 시점은 매도 비용 반영
    final_value = costs.apply_sell(equity[-1])
    equity_net = equity.copy()
    equity_net[-1] = final_value

    tr = final_value / amount - 1.0
    years = (actual_sell - actual_buy).days / 365.0
    cagr_v = metrics.cagr(amount, final_value, years) if years > 0 else 0.0
    mdd_v, dd = metrics.max_drawdown(equity)
    daily_ret = np.diff(adj) / adj[:-1]
    vol = metrics.annualized_volatility(daily_ret)
    sharpe = metrics.sharpe_ratio(daily_ret)

    return BacktestResult(
        ticker=ticker,
        buy_date=actual_buy,
        sell_date=actual_sell,
        invested=amount,
        final_value=float(final_value),
        total_return=float(tr),
        cagr=float(cagr_v),
        mdd=float(mdd_v),
        volatility=float(vol),
        sharpe=float(sharpe),
        period_high=float(adj.max()),
        period_low=float(adj.min()),
        equity_curve=pd.Series(equity_net, index=window.index),
        drawdown_curve=pd.Series(dd, index=window.index),
        forced_liquidation=forced,
    )


def normalize_for_comparison(price_map: dict[str, pd.Series]) -> pd.DataFrame:
    """여러 종목을 공통 구간에서 시작점=100으로 정규화 (Phase 2 종목 비교)."""
    df = pd.DataFrame(price_map).dropna()
    if df.empty:
        raise ValueError("no overlapping period among tickers")
    return df / df.iloc[0] * 100.0


def correlation_matrix(price_map: dict[str, pd.Series]) -> pd.DataFrame:
    """일간 수익률 기준 상관계수 행렬."""
    df = pd.DataFrame(price_map).dropna()
    return df.pct_change().dropna().corr()
