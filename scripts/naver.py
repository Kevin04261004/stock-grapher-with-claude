"""네이버 금융 모바일 API 접근 도우미."""

from __future__ import annotations

from http_util import FetchError, fetch_json, to_number

BASE = "https://m.stock.naver.com/api"

# compareToPreviousPrice.code — 네이버 등락 구분
RISING = {"1", "2"}   # 상한, 상승
FALLING = {"4", "5"}  # 하한, 하락


def direction_sign(raw: dict) -> int:
    """등락 부호. 네이버는 등락폭을 절댓값으로 주고 방향을 따로 알려 준다."""
    code = (raw.get("compareToPreviousPrice") or {}).get("code")
    if code in RISING:
        return 1
    if code in FALLING:
        return -1
    return 0


def index_history(index_id: str, points: int = 40) -> list[tuple[str, float]]:
    """지수 일별 종가를 (날짜, 값) 오름차순으로 돌려준다."""
    rows = fetch_json(f"{BASE}/index/{index_id}/price?pageSize={points}&page=1")
    if not isinstance(rows, list) or not rows:
        raise FetchError(f"{index_id}: 지수 시세 이력이 비어 있음")

    series = []
    for row in rows:
        date = (row.get("localTradedAt") or "")[:10]
        close = to_number(row.get("closePrice"))
        if date and close is not None:
            series.append((date, float(close)))

    if not series:
        raise FetchError(f"{index_id}: 유효한 지수 종가가 없음")

    series.sort(key=lambda p: p[0])
    return series


def index_latest(index_id: str, points: int = 40) -> dict:
    series = index_history(index_id, points)
    date, value = series[-1]
    prev = series[-2][1] if len(series) > 1 else value
    change = value - prev

    return {
        "date": date,
        "value": value,
        "change": change,
        "changePct": (change / prev * 100) if prev else 0.0,
        "history": series,
    }
