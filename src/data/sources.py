"""외부 데이터 소스 래퍼 (FinanceDataReader / yfinance).

네트워크 호출은 이 모듈에만 존재한다. 백테스트 연산은 절대 여기 의존하지 않는다.
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def fetch_prices(ticker: str, start: date | str, end: date | str | None = None) -> pd.DataFrame:
    """FDR로 일봉 조회 → 표준 컬럼(open/high/low/close/volume/adj_close)으로 정규화.

    - 한국(FDR/네이버 소스): Close가 이미 수정주가 → adj_close = close
    - 미국(야후 소스): Adj Close 컬럼 존재 시 사용
    """
    import FinanceDataReader as fdr

    df = fdr.DataReader(ticker, start, end)
    df = df.rename(columns=str.lower)
    if "adj close" in df.columns:
        df["adj_close"] = df["adj close"]
    else:
        df["adj_close"] = df["close"]
    cols = [c for c in ("open", "high", "low", "close", "volume", "adj_close") if c in df.columns]
    out = df[cols].dropna(subset=["adj_close"])
    out.index = pd.to_datetime(out.index)
    return out


def fetch_fx(pair: str = "USD/KRW", start: date | str = "2000-01-01",
             end: date | str | None = None) -> pd.DataFrame:
    """환율 조회. 반환: DatetimeIndex + 'rate' 컬럼."""
    import FinanceDataReader as fdr

    df = fdr.DataReader(pair, start, end)
    df = df.rename(columns=str.lower)
    col = "adj close" if "adj close" in df.columns else "close"
    out = df[[col]].rename(columns={col: "rate"}).dropna()
    out.index = pd.to_datetime(out.index)
    return out


def fetch_krx_listing() -> pd.DataFrame:
    """KRX 전종목 메타데이터 (KOSPI+KOSDAQ)."""
    import FinanceDataReader as fdr

    return fdr.StockListing("KRX")


def fetch_dividends_yf(ticker: str) -> pd.Series:
    """yfinance로 배당 이력 보강 (미국 종목)."""
    import yfinance as yf

    return yf.Ticker(ticker).dividends
