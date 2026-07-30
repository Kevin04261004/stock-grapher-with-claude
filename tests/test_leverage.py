"""레버리지 시뮬레이션 + 분포 분석 테스트."""
import numpy as np
import pytest

from src.engine.distribution import analyze_distribution, loss_probability_curve, rolling_returns
from src.engine.leverage import analyze_leverage, breakeven_required_gain, simulate_leveraged


class TestLeverage:
    def test_volatility_decay(self):
        """+10%/-10% 반복 시 2배 상품이 원금 미달 (명세서 필수 케이스).

        기초: 1.1 * 0.9 = 0.99 (약간 손실)
        2배: 1.2 * 0.8 = 0.96 (더 큰 손실) — 감쇄 확인
        """
        rets = np.array([0.10, -0.10] * 50)
        path = simulate_leveraged(rets, leverage=2.0, expense_ratio=0.0, financing_rate=0.0)
        base = np.cumprod(1 + rets)
        assert path[-1] < 1.0            # 원금 미달
        assert path[-1] < base[-1]       # 기초자산보다 더 나쁨

    def test_no_cost_no_vol_equals_multiple(self):
        """변동성 0이면 감쇄 없음: 일정 수익률에서 근사적으로 배율 작동."""
        rets = np.full(252, 0.0005)
        path = simulate_leveraged(rets, 2.0, expense_ratio=0.0, financing_rate=0.0)
        expected = np.cumprod(1 + rets * 2)
        assert path[-1] == pytest.approx(expected[-1])

    def test_costs_reduce_performance(self):
        rets = np.full(252, 0.001)
        free = simulate_leveraged(rets, 2.0, 0.0, 0.0)
        costly = simulate_leveraged(rets, 2.0, 0.0064, 0.035)
        assert costly[-1] < free[-1]

    def test_analyze_decay_positive_in_choppy_market(self):
        """횡보(+10%/-10% 반복) 시장에서 감쇄 확인.

        기초 -39.5%, naive(×2) -79.0%, 실제 2배 상품 -87.0% → decay > 0.
        """
        rets = np.array([0.10, -0.10] * 50)
        r = analyze_leverage(rets, 2.0, expense_ratio=0.0, financing_rate=0.0)
        assert r.decay > 0  # naive(기간수익×2)보다 실제가 나쁨
        assert r.leveraged_return < r.base_return

    def test_cannot_go_below_zero(self):
        rets = np.array([-0.6])  # 3배면 -180% → 0으로 바닥
        path = simulate_leveraged(rets, 3.0, 0.0, 0.0)
        assert path[-1] == pytest.approx(0.0)


class TestBreakeven:
    def test_basic_math(self):
        """-50% 손실 → +100% 필요."""
        assert breakeven_required_gain(0.5) == pytest.approx(1.0)
        assert breakeven_required_gain(0.3) == pytest.approx(0.3 / 0.7)
        assert breakeven_required_gain(0.0) == 0.0

    def test_invalid_input(self):
        with pytest.raises(ValueError):
            breakeven_required_gain(1.5)


class TestDistribution:
    def test_rolling_returns_manual(self):
        prices = np.array([100.0, 110.0, 121.0, 133.1])
        rets = rolling_returns(prices, 1)
        assert rets == pytest.approx([0.1, 0.1, 0.1])
        rets2 = rolling_returns(prices, 2)
        assert rets2 == pytest.approx([0.21, 0.21])

    def test_distribution_stats(self):
        rng = np.random.default_rng(2)
        prices = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 3000))
        r = analyze_distribution(prices, "T", 252)
        assert r.n_windows == 3000 - 252
        assert 0.0 <= r.loss_probability <= 1.0
        assert r.worst_5pct <= r.median

    def test_loss_curve_shrinks_sample(self):
        prices = 100 * np.cumprod(1 + np.full(2000, 0.0005))
        curve = loss_probability_curve(prices, [1, 12, 60])
        # 꾸준한 우상향이므로 손실확률 0
        assert all(lp == 0.0 for _, lp, _ in curve)

    def test_too_long_holding_raises(self):
        with pytest.raises(ValueError):
            analyze_distribution(np.array([1.0, 2.0]), "T", 10)
