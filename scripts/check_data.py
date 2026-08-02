#!/usr/bin/env python3
"""수집한 데이터가 앱에 내보내도 되는 상태인지 검사한다.

수집이 '성공'했는데 내용이 망가진 경우(빈 업종, 말도 안 되는 등락률, 두 화면의
지수 불일치 등)를 배포 전에 잡는다. 문제가 있으면 종료 코드 1.

사용법:
    python3 scripts/check_data.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "docs/data"

# 국내 주식 가격제한폭은 ±30% 다. 반올림 여유를 두고 판단한다.
PRICE_LIMIT = 31.0
MAX_STALE_DAYS = 7  # 연휴를 감안한 여유


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def check_markets(doc: dict, problems: list[str]) -> dict:
    markets = doc.get("markets") or []
    if len(markets) < 2:
        problems.append(f"markets.json: 시장이 {len(markets)}개뿐")

    indices = {}
    for market in markets:
        label = market.get("name") or market.get("id")
        sectors = market.get("sectors") or []
        stocks = [s for sec in sectors for s in sec.get("stocks", [])]

        if not sectors:
            problems.append(f"{label}: 업종이 없음")
        if len(stocks) < 10:
            problems.append(f"{label}: 종목이 {len(stocks)}개뿐")

        codes = [s["code"] for s in stocks]
        if len(codes) != len(set(codes)):
            problems.append(f"{label}: 종목코드 중복")

        for stock in stocks:
            name = stock.get("name", "?")
            if not (stock.get("cap", 0) > 0):
                problems.append(f"{label}/{name}: 시가총액이 0 이하")
            if not (stock.get("price", 0) > 0):
                problems.append(f"{label}/{name}: 주가가 0 이하")
            if abs(stock.get("changePct", 0)) > PRICE_LIMIT:
                problems.append(f"{label}/{name}: 등락률 {stock['changePct']}% 는 제한폭 밖")

        for sector in sectors:
            total = sum(s["cap"] for s in sector.get("stocks", []))
            if total != sector.get("cap"):
                problems.append(f"{label}/{sector.get('name')}: 업종 시총 합이 안 맞음")

        index = market.get("index") or {}
        if not (index.get("value", 0) > 0):
            problems.append(f"{label}: 지수 값이 없음")
        indices[market.get("id")] = index

    return indices


def check_indicators(doc: dict, problems: list[str], indices: dict) -> None:
    indicators = doc.get("indicators") or []
    if len(indicators) < 8:
        problems.append(f"indicators.json: 지표가 {len(indicators)}개뿐")

    for indicator in indicators:
        name = indicator.get("name", "?")
        history = indicator.get("history") or []
        if len(history) < 2:
            problems.append(f"{name}: 시계열이 {len(history)}점뿐")
            continue
        dates = [p["d"] for p in history]
        if dates != sorted(dates):
            problems.append(f"{name}: 시계열 날짜가 오름차순이 아님")
        if history[-1]["v"] != indicator.get("value"):
            problems.append(f"{name}: 마지막 시계열 값과 현재값이 다름")

    # 히트맵과 지표 화면이 같은 지수를 다르게 보여 주면 안 된다.
    for market_id, index in indices.items():
        match = next((i for i in indicators if i.get("id") == market_id), None)
        if not match:
            continue
        if (match["value"], match["changePct"]) != (index["value"], index["changePct"]):
            problems.append(
                f"{market_id}: 지표({match['value']}, {match['changePct']}%) 와 "
                f"히트맵({index['value']}, {index['changePct']}%) 불일치"
            )


def check_freshness(doc: dict, label: str, problems: list[str]) -> None:
    raw = doc.get("updatedAt")
    try:
        stamp = dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        problems.append(f"{label}: updatedAt 이 이상함 ({raw!r})")
        return

    age = (dt.datetime.now(dt.timezone.utc).date() - stamp).days
    if age > MAX_STALE_DAYS:
        problems.append(f"{label}: 데이터가 {age}일 지남 ({raw})")
    if age < 0:
        problems.append(f"{label}: updatedAt 이 미래 ({raw})")


def main() -> int:
    problems: list[str] = []

    try:
        markets = load("markets.json")
        indicators = load("indicators.json")
    except (OSError, json.JSONDecodeError) as err:
        print(f"데이터를 읽지 못함: {err}", file=sys.stderr)
        return 1

    indices = check_markets(markets, problems)
    check_indicators(indicators, problems, indices)
    check_freshness(markets, "markets.json", problems)
    check_freshness(indicators, "indicators.json", problems)

    if problems:
        print(f"검사 실패 — 문제 {len(problems)}건", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    stocks = sum(
        len(sec["stocks"]) for m in markets["markets"] for sec in m["sectors"]
    )
    print(
        f"검사 통과: {len(markets['markets'])}개 시장 {stocks}종목, "
        f"지표 {len(indicators['indicators'])}개, 기준일 {markets['updatedAt']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
