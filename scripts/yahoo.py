"""Yahoo Finance chart API 로 시세 시계열을 읽는다.

`https://query1.finance.yahoo.com/v8/finance/chart/<symbol>` 만 사용한다.
인증(crumb)이 필요한 quote/quoteSummary 계열은 쓰지 않는다.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from http_util import FetchError, fetch_json

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


def series(symbol: str, *, range_: str = "6mo", interval: str = "1d", tz: str = "UTC"):
    """
    종가 시계열을 (날짜, 값) 목록으로 돌려준다.

    거래가 없던 날은 close 가 None 으로 오므로 걸러낸다. 날짜는 해당 시장의
    시간대로 변환해야 하루씩 밀리지 않는다(예: 국내 지수를 UTC 로 읽으면
    장 마감 시각이 전날로 표시된다).
    """
    url = f"{BASE}/{symbol}?range={range_}&interval={interval}"
    payload = fetch_json(url)

    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise FetchError(f"{symbol}: {chart['error']}")

    results = chart.get("result") or []
    if not results:
        raise FetchError(f"{symbol}: 응답에 결과가 없음")

    result = results[0]
    stamps = result.get("timestamp") or []
    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []

    zone = ZoneInfo(tz)
    points = [
        (dt.datetime.fromtimestamp(ts, zone).date().isoformat(), float(close))
        for ts, close in zip(stamps, closes)
        if close is not None
    ]
    if not points:
        raise FetchError(f"{symbol}: 유효한 종가가 없음")

    return points


def latest(symbol: str, **kwargs) -> dict:
    """마지막 두 종가로 현재값·전일대비를 계산한다."""
    points = series(symbol, **kwargs)
    date, value = points[-1]
    prev = points[-2][1] if len(points) > 1 else value

    change = value - prev
    return {
        "date": date,
        "value": value,
        "prev": prev,
        "change": change,
        "changePct": (change / prev * 100) if prev else 0.0,
        "history": points,
    }
