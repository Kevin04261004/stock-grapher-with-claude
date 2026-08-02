#!/usr/bin/env python3
"""거시·시장 지표(docs/data/indicators.json)를 실제 데이터로 만든다.

출처
- 국내 지수: 네이버 금융 (히트맵과 같은 출처라 값이 어긋나지 않는다)
- 해외 지수·환율·원자재·가상자산: Yahoo Finance chart API
- 한국 고용·금리: FRED CSV (인증키 없이 받을 수 있는 공개 CSV)
- 한국 물가: 한국은행 ECOS, 막히면 IMF CPI(DBnomics 경유). 둘 다 인증키 불필요

지표마다 출처를 여러 개 둘 수 있고 앞에서부터 시도한다. 그마저 전부 실패하면
기존 파일의 값을 그대로 두고 경고만 남긴다. 일부 출처가 잠깐 막혀도 나머지
지표는 갱신되도록 하기 위해서다.

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
from http_util import FetchError, fetch, fetch_json, to_number  # noqa: E402

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
DBNOMICS = "https://api.db.nomics.world/v22/series/{code}?observations=1"

# 한국은행 ECOS. 'sample' 은 한국은행이 공개해 둔 공용 테스트 키다. 개인 키와 달리
# 한 번에 10행까지만 주고, 전 세계가 같이 쓰므로 자주 429/602 가 난다.
# 그래서 (1) 페이지를 나눠 받고 (2) 아래 MACRO_MIN_INTERVAL 로 호출을 아끼고
# (3) 실패하면 조용히 다음 출처로 넘어간다.
ECOS = ("https://ecos.bok.or.kr/api/StatisticSearch/"
        "{key}/json/kr/{start}/{end}/{table}/{cycle}/{begin}/{finish}/{item}")
ECOS_KEY = "sample"
ECOS_PAGE = 10

# 월 단위로 발표되는 지표는 10분마다 다시 받아 봐야 같은 값이다. 공용 키를
# 쓰는 ECOS 를 하루 40번 두드리면 남들 몫까지 막으므로 한 시간에 한 번만 받는다.
# 분/일 단위로 움직이는 시장 지표(naver·yahoo)에는 적용하지 않는다.
MACRO_KINDS = {"fred", "dbnomics", "ecos"}
MACRO_MIN_INTERVAL = dt.timedelta(hours=1)

# (id, 이름, 카테고리, 단위, 소수 자릿수, [(출처종류, 심볼), ...])
#
# 출처는 앞에서부터 시도해 처음 성공한 것을 쓴다. 대부분은 하나뿐이고,
# 여러 개인 건 앞쪽이 더 최신이지만 덜 안정적인 경우다.
#
# 국내 지수를 맨 앞에 두는 데는 이유가 있다. 장중 갱신은 fetch_markets.py 직후에
# 이 스크립트를 돌리는데, 두 파일의 지수 값이 어긋나면 check_data.py 가 배포를
# 막는다. 네이버를 먼저 찍어야 그 사이 지수가 움직일 틈이 가장 좁다.
SPECS = [
    ("kospi", "KOSPI", "시장", "pt", 2, [("naver", "KOSPI")]),
    ("kosdaq", "KOSDAQ", "시장", "pt", 2, [("naver", "KOSDAQ")]),
    ("sp500", "S&P 500", "시장", "pt", 2, [("yahoo", "^GSPC")]),
    ("nasdaq", "나스닥 종합", "시장", "pt", 2, [("yahoo", "^IXIC")]),
    ("usdkrw", "원/달러 환율", "환율", "원", 2, [("yahoo", "KRW=X")]),
    ("ust10y", "미국 10년물 국채금리", "금리", "%", 3, [("yahoo", "^TNX")]),
    ("callrate", "한국 콜금리", "금리", "%", 2, [("fred", "IRSTCI01KRM156N")]),
    # 물가는 FRED 를 쓸 수 없다. OECD 가 MEI 데이터베이스를 접으면서 FRED 의
    # 한국 CPI 계열(CPALTT01KRM659N, KORCPIALLMINMEI 등)이 2023-11 에서 통째로
    # 멈췄고, 대체 계열도 2025-04 이 한계다.
    # 1순위는 한국은행 ECOS — 통계 작성 주체라 가장 빠르다. 다만 공용 테스트 키를
    # 쓰므로 막힐 때가 있어, 그때는 IMF(1년쯤 뒤처짐)로 내려간다.
    # ECOS 는 지수(2020=100)로 주므로 전년동월비로 환산한다. IMF 는 이미 %.
    ("cpi", "한국 소비자물가 상승률", "물가", "%", 2, [
        ("ecos", "901Y009/M/0", "yoy"),
        ("dbnomics", "IMF/CPI/M.KR.PCPI_PC_CP_A_PT"),
    ]),
    ("unemployment", "한국 실업률", "고용", "%", 2, [("fred", "LRHUTTTTKRM156S")]),
    ("wti", "WTI 유가", "원자재", "USD", 2, [("yahoo", "CL=F")]),
    ("btc", "비트코인", "가상자산", "USD", 0, [("yahoo", "BTC-USD")]),
]

SOURCE_LABEL = "네이버 금융 · Yahoo Finance · FRED · 한국은행 · IMF"


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


def dbnomics_series(code: str) -> list[tuple[str, float]]:
    """DBnomics 시계열. code 는 '제공자/데이터셋/계열' 형식."""
    # 브라우저 흉내 헤더 없이(minimal) 요청해야 정상 응답한다.
    doc = fetch_json(DBNOMICS.format(code=code), timeout=30, minimal=True)
    docs = (doc.get("series") or {}).get("docs") or []
    if not docs:
        raise FetchError(f"{code}: DBnomics 응답에 계열이 없음")
    series = docs[0]

    # period 는 월간이면 '2025-07' 이지만 period_start_day 는 '2025-07-01' 로
    # FRED 와 형식이 같다. 두 출처가 섞여도 날짜 표기가 어긋나지 않도록 이걸 쓴다.
    days = series.get("period_start_day") or series.get("period") or []
    points = [
        (day, float(value))
        for day, value in zip(days, series.get("value") or [])
        if isinstance(value, (int, float))  # 결측치는 "NA" 문자열로 온다
    ]
    if not points:
        raise FetchError(f"{code}: 유효한 관측치가 없음")
    points.sort(key=lambda p: p[0])
    return points


def ecos_series(symbol: str) -> list[tuple[str, float]]:
    """한국은행 ECOS 시계열. symbol 은 '통계표/주기/항목' 형식(예: 901Y009/M/0)."""
    table, cycle, item = symbol.split("/")

    # 전년동월비를 만들려면 원하는 구간보다 12개월을 더 받아야 한다.
    today = dt.date.today()
    begin = f"{today.year - 5}{today.month:02d}"
    finish = f"{today.year}{today.month:02d}"

    points: list[tuple[str, float]] = []
    row_start = 1
    while True:
        doc = fetch_json(
            ECOS.format(
                key=ECOS_KEY, start=row_start, end=row_start + ECOS_PAGE - 1,
                table=table, cycle=cycle, begin=begin, finish=finish, item=item,
            ),
            timeout=30,
            minimal=True,
        )
        # 오류는 200 응답 본문에 RESULT 로 실려 온다(레이트리밋 602 등).
        if "RESULT" in doc:
            raise FetchError(f"ECOS {table}: {doc['RESULT'].get('MESSAGE', '알 수 없는 오류')}")

        block = doc.get("StatisticSearch") or {}
        rows = block.get("row") or []
        for row in rows:
            stamp, value = row.get("TIME"), to_number(row.get("DATA_VALUE"))
            if value is None or not stamp or len(stamp) != 6:
                continue
            points.append((f"{stamp[:4]}-{stamp[4:6]}-01", float(value)))

        total = int(to_number(block.get("list_total_count")) or 0)
        row_start += ECOS_PAGE
        # 공용 키는 한 번에 10행뿐이라 페이지를 넘겨 가며 받는다.
        if len(rows) < ECOS_PAGE or row_start > total:
            break

    if not points:
        raise FetchError(f"ECOS {table}: 유효한 관측치가 없음")
    points.sort(key=lambda p: p[0])
    return points


def to_yoy(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """지수 시계열을 전년동월비(%)로 바꾼다. 12개월 전 값이 없는 달은 버린다."""
    level = dict(points)
    out = []
    for day, value in points:
        year, month = int(day[:4]), day[5:7]
        base = level.get(f"{year - 1}-{month}-01")
        if base:
            out.append((day, (value / base - 1) * 100))
    if not out:
        raise FetchError("전년동월비를 만들 만큼 이력이 없음")
    return out


TRANSFORMS = {"yoy": to_yoy}


def load_series(kind: str, symbol: str) -> list[tuple[str, float]]:
    if kind == "naver":
        return naver.index_history(symbol, points=60)
    if kind == "yahoo":
        return yahoo.series(symbol, range_="6mo", interval="1d", tz="UTC")
    if kind == "fred":
        return fred_series(symbol)
    if kind == "dbnomics":
        return dbnomics_series(symbol)
    if kind == "ecos":
        return ecos_series(symbol)
    raise FetchError(f"알 수 없는 출처: {kind}")


def parse_stamp(text) -> dt.datetime | None:
    """'2026-08-02T07:57:36Z' → aware datetime. 못 읽으면 None."""
    if not isinstance(text, str):
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_indicator(spec, points_wanted: int) -> dict:
    ind_id, name, category, unit, decimals, sources = spec

    # 출처를 앞에서부터 시도한다. 앞쪽이 더 최신이지만 덜 안정적인 경우가 있어,
    # 막히면 다음 출처로 내려간다. 전부 실패하면 마지막 오류를 그대로 올린다.
    points, used, last_error = None, None, None
    for kind, symbol, *transform in sources:
        try:
            series = load_series(kind, symbol)
            for step in transform:
                series = TRANSFORMS[step](series)
            points, used = series, kind
            break
        except (FetchError, IndexError, ValueError, KeyError) as err:
            last_error = err
            if sources[-1][0] != kind:
                print(f"    {name}: {kind} 실패({err}) → 다음 출처", file=sys.stderr)
    if points is None:
        raise last_error or FetchError(f"{name}: 쓸 수 있는 출처가 없음")

    points = points[-points_wanted:]
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
        "--force",
        action="store_true",
        help="월간 지표 호출 간격(MACRO_MIN_INTERVAL)을 무시하고 전부 새로 받는다",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "docs/data/indicators.json"),
    )
    args = parser.parse_args()

    out = Path(args.out)
    previous, macro_fetched_at = {}, None
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            previous = {i["id"]: i for i in old.get("indicators", [])}
            macro_fetched_at = parse_stamp(old.get("macroFetchedAt"))
        except (json.JSONDecodeError, KeyError):
            pass

    now = dt.datetime.now(dt.timezone.utc)
    # 월간 지표를 방금 받았다면 이번에는 건너뛴다. 값이 바뀔 수가 없는데
    # 공용 키(ECOS)만 소진하기 때문이다. 시장 지표는 언제나 새로 받는다.
    skip_macro = bool(
        not args.force
        and macro_fetched_at
        and now - macro_fetched_at < MACRO_MIN_INTERVAL
        and previous
    )

    indicators, failed, macro_ran = [], [], False
    for spec in SPECS:
        ind_id, name, sources = spec[0], spec[1], spec[5]
        is_macro = all(kind in MACRO_KINDS for kind, *_ in sources)

        if is_macro and skip_macro and ind_id in previous:
            indicators.append(previous[ind_id])
            continue
        macro_ran = macro_ran or is_macro

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
    stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    doc = {
        # updatedAt = 가장 최근 관측치의 날짜, fetchedAt = 수집을 돌린 시각
        "updatedAt": updated,
        "fetchedAt": stamp,
        # 월간 지표를 마지막으로 실제로 받아 온 시각(위 MACRO_MIN_INTERVAL 판단용)
        "macroFetchedAt": stamp if macro_ran else (
            macro_fetched_at.isoformat().replace("+00:00", "Z") if macro_fetched_at else stamp
        ),
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
