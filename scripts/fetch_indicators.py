#!/usr/bin/env python3
"""거시·시장 지표(docs/data/indicators.json)를 실제 데이터로 만든다.

출처
- 국내 지수: 네이버 금융 (히트맵과 같은 출처라 값이 어긋나지 않는다)
- 해외 지수·환율·원자재·가상자산: Yahoo Finance chart API
- 한국 물가·고용·금리: FRED CSV (인증키 없이 받을 수 있는 공개 CSV)

한 지표를 못 가져오면 기존 파일의 값을 그대로 두고 경고만 남긴다.
일부 출처가 잠깐 막혀도 나머지 지표는 갱신되도록 하기 위해서다.

사용법:
    python3 scripts/fetch_indicators.py [--points 30] [--out PATH]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import naver  # noqa: E402
import yahoo  # noqa: E402
from http_util import FetchError, fetch  # noqa: E402

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

# (id, 이름, 카테고리, 단위, 소수 자릿수, 출처종류, 심볼)
SPECS = [
    ("kospi", "KOSPI", "시장", "pt", 2, "naver", "KOSPI"),
    ("kosdaq", "KOSDAQ", "시장", "pt", 2, "naver", "KOSDAQ"),
    ("sp500", "S&P 500", "시장", "pt", 2, "yahoo", "^GSPC"),
    ("nasdaq", "나스닥 종합", "시장", "pt", 2, "yahoo", "^IXIC"),
    ("usdkrw", "원/달러 환율", "환율", "원", 2, "yahoo", "KRW=X"),
    ("ust10y", "미국 10년물 국채금리", "금리", "%", 3, "yahoo", "^TNX"),
    ("callrate", "한국 콜금리", "금리", "%", 2, "fred", "IRSTCI01KRM156N"),
    ("cpi", "한국 소비자물가 상승률", "물가", "%", 2, "fred", "CPALTT01KRM659N"),
    ("unemployment", "한국 실업률", "고용", "%", 2, "fred", "LRHUTTTTKRM156S"),
    ("wti", "WTI 유가", "원자재", "USD", 2, "yahoo", "CL=F"),
    ("btc", "비트코인", "가상자산", "USD", 0, "yahoo", "BTC-USD"),
]

SOURCE_LABEL = "네이버 금융 · Yahoo Finance · FRED"


def fred_series(series_id: str) -> list[tuple[str, float]]:
    # FRED 는 브라우저 User-Agent 로 오는 요청에 응답하지 않으므로 헤더를 비운다.
    raw = fetch(FRED_CSV.format(series=series_id), timeout=30, minimal=True)
    raw = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw)))
    if len(rows) < 2:
        raise FetchError(f"{series_id}: FRED 응답이 비어 있음")

    points = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        date, value = row[0].strip(), row[1].strip()
        if not date or value in ("", "."):
            continue  # 결측치는 '.' 로 온다
        try:
            points.append((date, float(value)))
        except ValueError:
            continue

    if not points:
        raise FetchError(f"{series_id}: 유효한 관측치가 없음")
    points.sort(key=lambda p: p[0])
    return points


def load_series(kind: str, symbol: str) -> list[tuple[str, float]]:
    if kind == "naver":
        return naver.index_history(symbol, points=60)
    if kind == "yahoo":
        return yahoo.series(symbol, range_="6mo", interval="1d", tz="UTC")
    if kind == "fred":
        return fred_series(symbol)
    raise FetchError(f"알 수 없는 출처: {kind}")


def build_indicator(spec, points_wanted: int) -> dict:
    ind_id, name, category, unit, decimals, kind, symbol = spec

    points = load_series(kind, symbol)[-points_wanted:]
    value = points[-1][1]
    prev = points[-2][1] if len(points) > 1 else value
    change = value - prev

    return {
        "id": ind_id,
        "name": name,
        "category": category,
        "unit": unit,
        "decimals": decimals,
        "value": round(value, decimals),
        "change": round(change, decimals),
        "changePct": round((change / prev * 100) if prev else 0.0, 2),
        "history": [{"d": d, "v": round(v, decimals)} for d, v in points],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=30, help="시계열 표본 수")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="장중용. 국내 지수만 갱신하고 나머지는 기존 값을 그대로 둔다",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "docs/data/indicators.json"),
    )
    args = parser.parse_args()

    out = Path(args.out)
    previous = {}
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            previous = {i["id"]: i for i in old.get("indicators", [])}
        except (json.JSONDecodeError, KeyError):
            pass

    indicators, failed = [], []
    for spec in SPECS:
        ind_id, name, kind = spec[0], spec[1], spec[5]

        # 장중에는 국내 지수만 새로 받는다. 히트맵과 지수 값이 어긋나면 안 되므로
        # 이 둘은 반드시 갱신하고, 해외·거시 지표는 장중에 바뀔 일이 거의 없다.
        if args.quick and kind != "naver" and ind_id in previous:
            indicators.append(previous[ind_id])
            continue

        try:
            indicator = build_indicator(spec, args.points)
            indicators.append(indicator)
            print(
                f"  {name}: {indicator['value']} ({indicator['changePct']:+}%) "
                f"/ {len(indicator['history'])}점",
                file=sys.stderr,
            )
        except (FetchError, IndexError, ValueError) as err:
            failed.append(name)
            print(f"  ! {name} 실패: {err}", file=sys.stderr)
            if ind_id in previous:
                indicators.append(previous[ind_id])
                print(f"    → 기존 값 유지", file=sys.stderr)

    if not indicators:
        raise FetchError("지표를 하나도 못 가져옴")
    if len(failed) > len(SPECS) // 2:
        raise FetchError(f"실패가 너무 많음: {', '.join(failed)}")

    updated = max(i["history"][-1]["d"] for i in indicators if i.get("history"))
    doc = {
        # updatedAt = 가장 최근 관측치의 날짜, fetchedAt = 수집을 돌린 시각
        "updatedAt": updated,
        "fetchedAt": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "source": SOURCE_LABEL,
        "indicators": indicators,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(indicators)}개 지표, 실패 {len(failed)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as err:
        print(f"수집 실패: {err}", file=sys.stderr)
        sys.exit(1)
