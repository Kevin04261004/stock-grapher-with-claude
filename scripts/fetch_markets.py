#!/usr/bin/env python3
"""코스피·코스닥 히트맵 데이터(docs/data/markets.json)를 실제 시세로 만든다.

종목·지수 모두 네이버 금융 모바일 API 에서 읽는다.
(업종 목록 → 업종별 종목, 지수 시세)

지표 화면(indicators.json)의 KOSPI/KOSDAQ 도 같은 출처를 쓴다. 두 화면의
지수 값이 어긋나면 안 되기 때문이다.

사용법:
    python3 scripts/fetch_markets.py [--kospi 40] [--kosdaq 30] [--sectors 12] [--out PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import naver  # noqa: E402
from http_util import FetchError, fetch_json, to_number  # noqa: E402

NAVER = naver.BASE
PAGE_SIZE = 100

MARKETS = [
    # (id, 표시 이름, 네이버 거래소 코드, 네이버 지수 코드)
    ("kospi", "코스피", "KS", "KOSPI"),
    ("kosdaq", "코스닥", "KQ", "KOSDAQ"),
]


def fetch_industries() -> list[dict]:
    # pageSize 를 주지 않으면 20개만 온다(전체 79개).
    data = fetch_json(f"{NAVER}/stocks/industry?page=1&pageSize={PAGE_SIZE}")
    groups = data.get("groups") or []
    total = data.get("totalCount") or len(groups)
    if not groups:
        raise FetchError("업종 목록이 비어 있음")
    if len(groups) < total:
        raise FetchError(f"업종 목록이 잘림 ({len(groups)}/{total})")
    return groups


def fetch_industry_stocks(no: int) -> list[dict]:
    """한 업종에 속한 종목을 전부 가져온다."""
    out, page = [], 1
    while True:
        data = fetch_json(f"{NAVER}/stocks/industry/{no}?page={page}&pageSize={PAGE_SIZE}")
        stocks = data.get("stocks") or []
        out.extend(stocks)

        total = data.get("totalCount") or len(out)
        if not stocks or len(out) >= total or page > 50:
            return out
        page += 1


def parse_stock(raw: dict, industry: str) -> dict | None:
    """네이버 종목 항목을 앱 데이터 형식으로 옮긴다. 대상이 아니면 None."""
    code = raw.get("itemCode") or ""
    name = (raw.get("stockName") or "").strip()

    # ETF·ETN·리츠 등은 제외하고 보통주만 담는다.
    # (국내 종목코드는 보통주가 0 으로 끝나고 우선주는 5·7·9 로 끝난다)
    if raw.get("stockEndType") != "stock" or not code or not name:
        return None
    if len(code) != 6 or not code.endswith("0"):
        return None

    price = to_number(raw.get("closePrice"))
    cap = to_number(raw.get("marketValue"))  # 단위: 억원
    change = to_number(raw.get("compareToPreviousClosePrice"), 0)
    pct = to_number(raw.get("fluctuationsRatio"), 0.0)
    if price is None or cap is None or cap <= 0:
        return None

    # 등락 부호는 별도 코드로 오므로 절댓값에 부호를 다시 붙인다.
    sign = naver.direction_sign(raw)
    change = sign * abs(change or 0)
    pct = sign * abs(pct or 0.0)

    return {
        "code": code,
        "name": name,
        "industry": industry,
        "price": price,
        "change": change,
        "changePct": round(pct, 2),
        "cap": cap,
        "exchange": (raw.get("stockExchangeType") or {}).get("code"),
    }


def collect_stocks() -> list[dict]:
    industries = fetch_industries()
    print(f"업종 {len(industries)}개", file=sys.stderr)

    seen: dict[str, dict] = {}
    for i, group in enumerate(industries, 1):
        name = (group.get("name") or "").strip() or "기타"
        try:
            rows = fetch_industry_stocks(group["no"])
        except FetchError as err:
            print(f"  ! {name} 건너뜀: {err}", file=sys.stderr)
            continue

        for raw in rows:
            stock = parse_stock(raw, name)
            if stock:
                seen.setdefault(stock["code"], stock)

        if i % 20 == 0:
            print(f"  {i}/{len(industries)} 업종, 누적 {len(seen)}종목", file=sys.stderr)

    if not seen:
        raise FetchError("수집된 종목이 없음")
    return list(seen.values())


def make_sector(name: str, rows: list[dict]) -> dict:
    cap = sum(r["cap"] for r in rows)
    return {
        "name": name,
        "cap": cap,
        "changePct": round(sum(r["changePct"] * r["cap"] for r in rows) / cap, 2),
        "stocks": [
            {k: r[k] for k in ("code", "name", "price", "change", "changePct", "cap")}
            for r in sorted(rows, key=lambda r: -r["cap"])
        ],
    }


def build_market(market_id, name, exchange, index_id, stocks, top_n, max_sectors):
    picked = sorted(
        (s for s in stocks if s["exchange"] == exchange),
        key=lambda s: -s["cap"],
    )[:top_n]
    if not picked:
        raise FetchError(f"{name}: 종목을 하나도 못 찾음")

    by_industry: dict[str, list[dict]] = defaultdict(list)
    for stock in picked:
        by_industry[stock["industry"]].append(stock)

    groups = sorted(
        by_industry.items(),
        key=lambda kv: -sum(r["cap"] for r in kv[1]),
    )

    # 네이버 업종 분류(79개)를 그대로 쓰면 1종목짜리 업종이 잔뜩 생겨 히트맵이
    # 잘게 부서진다. 시총 상위 업종만 남기고 나머지는 '기타' 로 합친다.
    sectors = [make_sector(industry, rows) for industry, rows in groups[:max_sectors]]
    leftover = [row for _, rows in groups[max_sectors:] for row in rows]
    if len(leftover) == 1:
        # 한 업종만 남으면 굳이 이름을 지울 이유가 없다.
        industry, rows = groups[max_sectors]
        sectors.append(make_sector(industry, rows))
    elif leftover:
        sectors.append(make_sector("기타", leftover))

    sectors.sort(key=lambda s: -s["cap"])

    index = naver.index_latest(index_id)
    return {
        "id": market_id,
        "name": name,
        "index": {
            "value": round(index["value"], 2),
            "change": round(index["change"], 2),
            "changePct": round(index["changePct"], 2),
        },
        "totalCap": sum(s["cap"] for s in sectors),
        "sectors": sectors,
    }, index["date"], len(picked)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kospi", type=int, default=40, help="코스피 상위 종목 수")
    parser.add_argument("--kosdaq", type=int, default=30, help="코스닥 상위 종목 수")
    parser.add_argument(
        "--sectors", type=int, default=12, help="시장별로 남길 업종 수 (나머지는 '기타')"
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "docs/data/markets.json"),
    )
    args = parser.parse_args()
    top = {"kospi": args.kospi, "kosdaq": args.kosdaq}

    stocks = collect_stocks()
    print(f"보통주 {len(stocks)}종목 수집", file=sys.stderr)

    markets, dates = [], []
    for market_id, name, exchange, index_id in MARKETS:
        market, date, count = build_market(
            market_id, name, exchange, index_id, stocks, top[market_id], args.sectors
        )
        markets.append(market)
        dates.append(date)
        print(
            f"{name}: {count}종목 / {len(market['sectors'])}업종 / "
            f"지수 {market['index']['value']} ({market['index']['changePct']:+}%)",
            file=sys.stderr,
        )

    doc = {
        # updatedAt = 데이터의 기준일, fetchedAt = 수집을 돌린 시각
        "updatedAt": max(dates),
        "fetchedAt": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "source": "네이버 금융",
        "capUnit": "억원",
        "markets": markets,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as err:
        print(f"수집 실패: {err}", file=sys.stderr)
        sys.exit(1)
