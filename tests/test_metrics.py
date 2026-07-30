"""계산 엔진 정확도 테스트 — 명세서 7장 필수 케이스."""
from datetime import date

import numpy as np
import pytest

from src.engine import metrics


class TestXIRR:
    def test_excel_parity_simple(self):
        """Excel XIRR() 검증 케이스: 소수점 4자리 일치.

        Excel: =XIRR({-10000;2750;4250;3250;2750}, {"2008-01-01";"2008-03-01";
        "2008-10-30";"2009-02-15";"2009-04-01"}) = 0.373362535
        """
        cfs = [
            (date(2008, 1, 1), -10000.0),
            (date(2008, 3, 1), 2750.0),
            (date(2008, 10, 30), 4250.0),
            (date(2009, 2, 15), 3250.0),
            (date(2009, 4, 1), 2750.0),
        ]
        assert metrics.xirr(cfs) == pytest.approx(0.373362535, abs=1e-4)

    def test_one_year_double(self):
        """1년 뒤 2배 회수 → XIRR = 100%."""
        cfs = [(date(2020, 1, 1), -1000.0), (date(2021, 1, 1), 2000.0)]
        # 365일 기준 (2020년은 366일이므로 근사 허용)
        assert metrics.xirr(cfs) == pytest.approx(1.0, abs=0.01)

    def test_negative_return(self):
        cfs = [(date(2020, 1, 1), -1000.0), (date(2021, 1, 1), 500.0)]
        assert metrics.xirr(cfs) < 0

    def test_monthly_contributions(self):
        """매월 100씩 12회 투입, 최종 1300 회수 — Excel 대조값."""
        cfs = [(date(2023, m, 1), -100.0) for m in range(1, 13)]
        cfs.append((date(2024, 1, 1), 1300.0))
        # Excel XIRR 정의식(365일 기준)의 근: 독립 이분탐색으로 검증
        assert metrics.xirr(cfs) == pytest.approx(0.1566984, abs=1e-4)

    def test_requires_mixed_signs(self):
        with pytest.raises(ValueError):
            metrics.xirr([(date(2020, 1, 1), -100.0), (date(2021, 1, 1), -100.0)])


class TestCAGR:
    def test_identity_one_year_double(self):
        """1년 100% 수익 → CAGR = 1.0 (항등성)."""
        assert metrics.cagr(100, 200, 1.0) == pytest.approx(1.0)

    def test_two_years(self):
        """2년 뒤 4배 → CAGR = 100%."""
        assert metrics.cagr(100, 400, 2.0) == pytest.approx(1.0)

    def test_flat(self):
        assert metrics.cagr(100, 100, 5.0) == pytest.approx(0.0)


class TestMDD:
    def test_manual_series(self):
        """수동 계산 시계열 대조: 100→120→60→90 → MDD = -50% (120 대비 60)."""
        mdd, dd = metrics.max_drawdown(np.array([100, 120, 60, 90]))
        assert mdd == pytest.approx(-0.5)
        assert dd[0] == pytest.approx(0.0)
        assert dd[2] == pytest.approx(-0.5)
        assert dd[3] == pytest.approx(-0.25)

    def test_monotonic_up_no_drawdown(self):
        mdd, _ = metrics.max_drawdown(np.array([1, 2, 3, 4, 5]))
        assert mdd == pytest.approx(0.0)


class TestVolatilitySharpe:
    def test_volatility_annualization(self):
        rng = np.random.default_rng(0)
        daily = rng.normal(0, 0.01, 10000)
        vol = metrics.annualized_volatility(daily)
        assert vol == pytest.approx(0.01 * np.sqrt(252), rel=0.05)

    def test_sharpe_zero_for_zero_returns(self):
        assert metrics.sharpe_ratio(np.zeros(100)) == 0.0

    def test_sortino_ignores_upside(self):
        """상방 변동만 있으면 Sortino는 inf."""
        rets = np.array([0.01, 0.02, 0.03, 0.01])
        assert metrics.sortino_ratio(rets) == float("inf")
