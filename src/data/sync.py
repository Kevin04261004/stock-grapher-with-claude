"""증분 동기화 (명세서 2.2).

1. 최초 실행: 벌크 다운로드 → SQLite
2. 이후 실행: 마지막 저장일 - OVERLAP_DAYS ~ 오늘 구간만 요청
   (마지막 며칠 덮어쓰기: 수정주가 소급 반영 대응)
3. 백테스트 연산은 전부 로컬 DB에서 수행
"""
from __future__ import annotations

from datetime import date, timedelta

from src.data.repository import Repository
from src.data.sources import fetch_prices

OVERLAP_DAYS = 7          # 증분 시 덮어쓸 최근 일수
DEFAULT_START = date(2000, 1, 1)


def sync_ticker(repo: Repository, ticker: str, start: date = DEFAULT_START) -> int:
    """단일 종목 동기화. 저장한 행 수 반환."""
    last = repo.last_synced(ticker)
    fetch_start = start if last is None else last - timedelta(days=OVERLAP_DAYS)
    today = date.today()
    if last is not None and fetch_start >= today:
        return 0
    df = fetch_prices(ticker, fetch_start, today)
    if df.empty:
        return 0
    repo.save_prices(ticker, df)
    repo.mark_synced(ticker, df.index[-1].date())
    return len(df)


def sync_many(repo: Repository, tickers: list[str], start: date = DEFAULT_START) -> dict[str, int]:
    """여러 종목 순차 동기화. 실패 종목은 건너뛰고 결과에 -1 기록."""
    result = {}
    for t in tickers:
        try:
            result[t] = sync_ticker(repo, t, start)
        except Exception:
            result[t] = -1
    return result
