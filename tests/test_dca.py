"""DCA 시뮬레이션 테스트."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.engine.backtest import next_trading_day, run_backtest
from src.engine.costs import ZERO_COST, CostModel
from src.engine.dca import build_schedule, run_dca


def make_prices(start="2020-01-01", periods=500, daily_ret=0.001) -> pd.DataFrame:
    """영업일 인덱스의 합성 가격 시계열."""
    idx = pd.bdate_range(start, periods=periods)
    prices = 100.0 * np.cumprod(np.full(periods, 1 + daily_ret))
    return pd.DataFrame({"adj_close": prices, "close": prices}, index=idx)


class TestSchedule:
    def test_monthly_count(self):
        s = build_schedule(date(2020, 1, 15), date(2020, 12, 15), "monthly")
        assert len(s) == 12
        assert s[0] == date(2020, 1, 15)
        assert s[-1] == date(2020, 12, 15)

    def test_holiday_rollover(self):
        """매수 예정일이 휴장일(주말) → 다음 영업일 체결."""
        prices = make_prices()
        # 2020-01-04는 토요일 → 다음 영업일 2020-01-06(월)
        td = next_trading_day(prices, date(2020, 1, 4))
        assert td == date(2020, 1, 6)


class TestDCA:
    def test_no_cost_single_purchase_equals_lump_sum(self):
        """무비용 + DCA 1회 = 일시불 결과와 동일 (명세서 필수 케이스)."""
        prices = make_prices()
        start = date(2020, 1, 6)
        end = date(2020, 3, 2)
        # quarterly 주기 + 2개월 구간 → 매수는 첫 회 1번뿐
        dca = run_dca(prices, "TEST", start, end, "quarterly", 1000.0, ZERO_COST)
        assert dca.n_purchases == 1

        bt = run_backtest(prices, "TEST", start, end, 1000.0, ZERO_COST)
        assert dca.final_value == pytest.approx(bt.final_value)
        assert dca.final_value == pytest.approx(dca.lump_sum_final_value)

    def test_invested_and_value_curves(self):
        prices = make_prices()
        r = run_dca(prices, "TEST", date(2020, 1, 6), date(2020, 6, 30),
                    "monthly", 100.0, ZERO_COST)
        assert r.n_purchases == 6
        assert r.total_invested == pytest.approx(600.0)
        assert r.invested_curve.iloc[-1] == pytest.approx(600.0)
        # 우상향 시계열이므로 평가액 > 투입금
        assert r.final_value > r.total_invested
        assert r.xirr > 0

    def test_avg_price_below_final_in_uptrend(self):
        prices = make_prices()
        r = run_dca(prices, "TEST", date(2020, 1, 6), date(2020, 12, 31),
                    "monthly", 100.0, ZERO_COST)
        assert r.avg_buy_price < r.final_price

    def test_costs_reduce_final_value(self):
        prices = make_prices()
        free = run_dca(prices, "T", date(2020, 1, 6), date(2020, 12, 31),
                       "monthly", 100.0, ZERO_COST)
        costly = run_dca(prices, "T", date(2020, 1, 6), date(2020, 12, 31),
                         "monthly", 100.0,
                         CostModel(buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0018))
        assert costly.final_value < free.final_value

    def test_integer_shares_option(self):
        prices = make_prices()
        r = run_dca(prices, "T", date(2020, 1, 6), date(2020, 6, 30),
                    "monthly", 250.0, ZERO_COST, allow_fractional=False)
        # 정수 주수만 보유
        total_qty = sum(q for _, _, q in r.purchases)
        assert total_qty == int(total_qty)


class TestBacktestEdge:
    def test_forced_liquidation_on_delisting(self):
        """상장폐지 → 상폐일 종가로 강제 청산 (명세서 필수 케이스)."""
        prices = make_prices(periods=100)
        delist = prices.index[50].date()
        r = run_backtest(prices, "DEAD", date(2020, 1, 6), date(2021, 12, 31),
                         1000.0, ZERO_COST, delisted_date=delist)
        assert r.forced_liquidation
        assert r.sell_date <= delist

    def test_buy_on_holiday_rolls_forward(self):
        prices = make_prices()
        r = run_backtest(prices, "T", date(2020, 1, 4), date(2020, 6, 30), 1000.0)
        assert r.buy_date == date(2020, 1, 6)
