"""적립식(DCA) 시뮬레이션 (Phase 2)."""
from __future__ import annotations

from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta

from src.engine import metrics
from src.engine.backtest import next_trading_day
from src.engine.costs import CostModel, ZERO_COST
from src.models import DCAResult

FREQUENCIES = ("monthly", "weekly", "quarterly")


def build_schedule(start: date, end: date, frequency: str) -> list[date]:
    """매수 예정일 목록 생성. 실제 체결일은 휴장일 이월 후 결정."""
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {FREQUENCIES}")
    dates = []
    cur = start
    while cur <= end:
        dates.append(cur)
        if frequency == "monthly":
            cur = cur + relativedelta(months=1)
        elif frequency == "quarterly":
            cur = cur + relativedelta(months=3)
        else:
            cur = cur + relativedelta(weeks=1)
    return dates


def run_dca(
    prices: pd.DataFrame,
    ticker: str,
    start: date,
    end: date,
    frequency: str = "monthly",
    amount_per_period: float = 1_000_000.0,
    costs: CostModel = ZERO_COST,
    allow_fractional: bool = True,
) -> DCAResult:
    """적립식 시뮬레이션.

    - 매수 예정일이 휴장일이면 다음 영업일 체결 (동일 체결일 중복 매수는 1회로 합침).
    - allow_fractional=False면 정수 주수만 매수, 잔액은 현금 보유.
    - 주 지표는 XIRR (단순 수익률/CAGR은 적립식에 부적합).
    """
    schedule = build_schedule(start, end, frequency)
    exec_dates: list[date] = []
    for d in schedule:
        td = next_trading_day(prices, d)
        if td is None or td > end:
            continue
        if exec_dates and td == exec_dates[-1]:
            continue
        exec_dates.append(td)
    if not exec_dates:
        raise ValueError("no executable purchase dates in range")

    shares = 0.0
    cash = 0.0
    total_invested = 0.0
    purchases: list[tuple[date, float, float]] = []
    cashflows: list[tuple[date, float]] = []

    adj = prices["adj_close"]

    for d in exec_dates:
        px = float(adj.loc[pd.Timestamp(d)])
        total_invested += amount_per_period
        cashflows.append((d, -amount_per_period))
        net = costs.apply_buy(amount_per_period + cash)
        cash_used_gross = amount_per_period + cash
        if allow_fractional:
            qty = net / px
            cash = 0.0
        else:
            qty = int(net / px)
            spent_net = qty * px
            # 사용하지 않은 금액은 현금으로 보존 (비용은 실제 매수분에만 부과 근사)
            cash = cash_used_gross - spent_net / (1.0 - costs.buy_cost_rate()) if qty > 0 else cash_used_gross
        shares += qty
        purchases.append((d, px, qty))

    # 평가 구간: 첫 체결일 ~ end
    last_day = next_trading_day(prices, end)
    if last_day is None:
        last_day = prices.index[-1].date()
    window = prices.loc[pd.Timestamp(exec_dates[0]): pd.Timestamp(last_day)]

    # 누적 투입/평가 곡선
    invested_curve = pd.Series(0.0, index=window.index)
    shares_curve = pd.Series(0.0, index=window.index)
    cum_inv, cum_sh = 0.0, 0.0
    p_iter = iter(purchases)
    nxt = next(p_iter, None)
    inv_vals, sh_vals = [], []
    for ts in window.index:
        while nxt is not None and pd.Timestamp(nxt[0]) <= ts:
            cum_inv += amount_per_period
            cum_sh += nxt[2]
            nxt = next(p_iter, None)
        inv_vals.append(cum_inv)
        sh_vals.append(cum_sh)
    invested_curve = pd.Series(inv_vals, index=window.index)
    shares_curve = pd.Series(sh_vals, index=window.index)
    value_curve = shares_curve * window["adj_close"] + cash

    final_price = float(window["adj_close"].iloc[-1])
    final_value = costs.apply_sell(shares * final_price) + cash

    cashflows.append((window.index[-1].date(), final_value))
    if final_value <= 0:
        xirr_v = -1.0
    elif window.index[-1].date() == exec_dates[0]:
        xirr_v = final_value / total_invested - 1.0  # 기간 0일 → 단순 수익률
    else:
        xirr_v = metrics.xirr(cashflows)

    total_qty = sum(q for _, _, q in purchases)
    avg_price = (
        sum(px * q for _, px, q in purchases) / total_qty if total_qty > 0 else 0.0
    )

    # 일시불(Lump Sum) 비교: 총액을 첫 체결일에 전액 매수
    first_px = purchases[0][1]
    ls_shares = costs.apply_buy(total_invested) / first_px
    ls_final = costs.apply_sell(ls_shares * final_price)

    return DCAResult(
        ticker=ticker,
        total_invested=total_invested,
        final_value=float(final_value),
        xirr=float(xirr_v),
        avg_buy_price=float(avg_price),
        final_price=final_price,
        n_purchases=len(purchases),
        shares=float(shares),
        invested_curve=invested_curve,
        value_curve=value_curve,
        purchases=purchases,
        lump_sum_final_value=float(ls_final),
        lump_sum_return=float(ls_final / total_invested - 1.0),
    )
