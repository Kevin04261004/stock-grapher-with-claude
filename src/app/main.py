"""Streamlit 진입점 — 로컬 실행용 UI.

실행: streamlit run src/app/main.py
계산은 전부 src/engine에 위임한다 (엔진은 Streamlit을 모른다).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data.repository import Repository
from src.data.sync import sync_ticker
from src.engine import metrics
from src.engine.backtest import correlation_matrix, normalize_for_comparison, run_backtest
from src.engine.costs import KOREA_DEFAULT, US_DEFAULT, ZERO_COST
from src.engine.dca import run_dca
from src.engine.distribution import analyze_distribution, loss_probability_curve
from src.engine.leverage import analyze_leverage, breakeven_required_gain

st.set_page_config(page_title="주식 백테스팅 시뮬레이터", layout="wide")

DISCLAIMER = (
    "⚠️ 과거 성과는 미래 수익을 보장하지 않습니다. 백테스트에는 생존편향·과최적화 "
    "위험이 내재하며, 투자 판단의 근거로 사용 시 책임은 사용자에게 있습니다."
)

DEFAULT_TICKERS = {
    "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER",
    "069500": "KODEX 200", "AAPL": "Apple", "MSFT": "Microsoft",
    "SPY": "SPDR S&P 500", "QQQ": "Invesco QQQ",
}


@st.cache_resource
def get_repo() -> Repository:
    return Repository()


@st.cache_data(ttl=3600)
def load_prices(ticker: str) -> pd.DataFrame:
    repo = get_repo()
    df = repo.load_prices(ticker)
    if df.empty:
        sync_ticker(repo, ticker)
        df = repo.load_prices(ticker)
    return df


def cost_model_for(ticker: str):
    return KOREA_DEFAULT if ticker.isdigit() else US_DEFAULT


st.title("📈 주식 백테스팅 시뮬레이터")
st.caption(DISCLAIMER)

ticker_input = st.sidebar.text_input("종목 코드 (예: 005930, AAPL)", "005930")
st.sidebar.write("자주 쓰는 종목:", ", ".join(f"{k}({v})" for k, v in DEFAULT_TICKERS.items()))
use_costs = st.sidebar.checkbox("거래 비용 반영", value=True)

tab_bt, tab_cmp, tab_dca, tab_dist, tab_lev = st.tabs(
    ["단일 백테스트", "종목 비교", "적립식(DCA)", "진입 시점 분포", "레버리지 시뮬"]
)

with tab_bt:
    c1, c2, c3 = st.columns(3)
    buy = c1.date_input("매수일", date.today() - timedelta(days=365 * 3))
    sell = c2.date_input("매도일", date.today())
    amount = c3.number_input("투자금액", value=10_000_000, step=1_000_000)
    if st.button("백테스트 실행"):
        prices = load_prices(ticker_input)
        costs = cost_model_for(ticker_input) if use_costs else ZERO_COST
        r = run_backtest(prices, ticker_input, buy, sell, float(amount), costs)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("최종 평가액", f"{r.final_value:,.0f}")
        m2.metric("총수익률", f"{r.total_return:+.2%}")
        m3.metric("CAGR", f"{r.cagr:+.2%}")
        m4.metric("MDD", f"{r.mdd:.2%}")
        fig = go.Figure()
        fig.add_scatter(x=r.equity_curve.index, y=r.equity_curve.values, name="평가액")
        st.plotly_chart(fig, use_container_width=True)
        fig2 = go.Figure()
        fig2.add_scatter(x=r.drawdown_curve.index, y=r.drawdown_curve.values,
                         fill="tozeroy", name="낙폭")
        fig2.update_layout(title="낙폭(Drawdown)", yaxis_tickformat=".0%")
        st.plotly_chart(fig2, use_container_width=True)

with tab_cmp:
    others = st.text_input("비교 종목 (쉼표 구분)", "005930, AAPL, SPY")
    if st.button("비교 실행"):
        tickers = [t.strip() for t in others.split(",") if t.strip()]
        series = {t: load_prices(t)["adj_close"] for t in tickers}
        norm = normalize_for_comparison(series)
        fig = go.Figure()
        for col in norm.columns:
            fig.add_scatter(x=norm.index, y=norm[col], name=col)
        fig.update_layout(title="정규화 성과 (시작=100)")
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("상관계수 행렬 (일간 수익률)")
        st.dataframe(correlation_matrix(series).style.format("{:.3f}"))

with tab_dca:
    c1, c2, c3, c4 = st.columns(4)
    d_start = c1.date_input("시작일", date.today() - timedelta(days=365 * 5), key="ds")
    d_end = c2.date_input("종료일", date.today(), key="de")
    freq = c3.selectbox("주기", ["monthly", "weekly", "quarterly"])
    per = c4.number_input("회차당 금액", value=500_000, step=100_000)
    if st.button("DCA 실행"):
        prices = load_prices(ticker_input)
        costs = cost_model_for(ticker_input) if use_costs else ZERO_COST
        r = run_dca(prices, ticker_input, d_start, d_end, freq, float(per), costs)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 투입금", f"{r.total_invested:,.0f}")
        m2.metric("최종 평가액", f"{r.final_value:,.0f}")
        m3.metric("XIRR (연환산)", f"{r.xirr:+.2%}")
        m4.metric("일시불이었다면", f"{r.lump_sum_final_value:,.0f}")
        st.write(f"평균 매입단가 {r.avg_buy_price:,.0f} vs 최종가 {r.final_price:,.0f} · 매수 {r.n_purchases}회")
        fig = go.Figure()
        fig.add_scatter(x=r.invested_curve.index, y=r.invested_curve.values, name="누적 투입금")
        fig.add_scatter(x=r.value_curve.index, y=r.value_curve.values, name="평가액")
        st.plotly_chart(fig, use_container_width=True)

with tab_dist:
    months = st.slider("보유기간 (개월)", 1, 120, 12)
    if st.button("분포 분석 실행"):
        prices = load_prices(ticker_input)
        adj = prices["adj_close"].to_numpy()
        r = analyze_distribution(adj, ticker_input, months * 21)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("중앙값", f"{r.median:+.2%}")
        m2.metric("손실 확률", f"{r.loss_probability:.1%}")
        m3.metric("하위 5%", f"{r.worst_5pct:+.2%}")
        m4.metric("표본 수", f"{r.n_windows:,}")
        fig = go.Figure(go.Histogram(x=r.returns, nbinsx=80))
        fig.update_layout(title=f"{months}개월 보유 수익률 분포 (모든 진입 시점)",
                          xaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
        curve = loss_probability_curve(adj)
        fig2 = go.Figure(go.Scatter(x=[m for m, _, _ in curve],
                                    y=[p for _, p, _ in curve], mode="lines+markers"))
        fig2.update_layout(title="보유기간별 손실확률", xaxis_title="개월",
                           yaxis_tickformat=".0%")
        st.plotly_chart(fig2, use_container_width=True)

with tab_lev:
    c1, c2, c3 = st.columns(3)
    lev = c1.slider("레버리지 배율", 1.0, 3.0, 2.0, 0.5)
    er = c2.number_input("연 보수 (%)", value=0.64) / 100
    fr = c3.number_input("차입 비용 (%)", value=3.5) / 100
    years_back = st.slider("과거 N년", 1, 15, 5)
    if st.button("레버리지 시뮬 실행"):
        prices = load_prices(ticker_input)
        cutoff = pd.Timestamp(date.today() - timedelta(days=int(365 * years_back)))
        adj = prices.loc[prices.index >= cutoff, "adj_close"].to_numpy()
        rets = np.diff(adj) / adj[:-1]
        r = analyze_leverage(rets, lev, er, fr)
        m1, m2, m3 = st.columns(3)
        m1.metric("기초자산", f"{r.base_return:+.2%}")
        m2.metric(f"{lev}x 상품(감쇄 반영)", f"{r.leveraged_return:+.2%}")
        m3.metric("감쇄 손실분", f"{r.decay:.2%}p")
        fig = go.Figure()
        x = prices.loc[prices.index >= cutoff].index[1:]
        fig.add_scatter(x=x, y=r.base_path, name="기초자산")
        fig.add_scatter(x=x, y=r.leveraged_path, name=f"{lev}x (일간 리밸런싱)")
        fig.add_scatter(x=x, y=r.naive_path, name=f"기초 × {lev} (가상)", line=dict(dash="dot"))
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("손익분기 계산기")
        loss = st.slider("현재 손실률 (%)", 0, 90, 30) / 100
        st.write(f"본전까지 상품 자체가 올라야 하는 폭: **{breakeven_required_gain(loss):+.1%}**")

st.divider()
st.caption(DISCLAIMER)
