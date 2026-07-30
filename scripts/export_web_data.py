"""GitHub Pages 정적 웹앱용 데이터 내보내기.

FDR로 주가를 받아 SQLite에 캐시한 뒤 docs/data/*.json으로 내보낸다.
웹앱은 이 JSON을 로컬 캐시처럼 사용한다 (런타임 API 호출 없음 = local-first).

실행: python scripts/export_web_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.repository import Repository
from src.data.sources import fetch_fx
from src.data.sync import sync_ticker

OUT_DIR = ROOT / "docs" / "data"
START = date(2005, 1, 1)

# (티커, 이름, 시장, 통화)
TICKERS = [
    ("005930", "삼성전자", "KOSPI", "KRW"),
    ("000660", "SK하이닉스", "KOSPI", "KRW"),
    ("035420", "NAVER", "KOSPI", "KRW"),
    ("035720", "카카오", "KOSPI", "KRW"),
    ("005380", "현대차", "KOSPI", "KRW"),
    ("051910", "LG화학", "KOSPI", "KRW"),
    ("068270", "셀트리온", "KOSPI", "KRW"),
    ("069500", "KODEX 200", "ETF(KR)", "KRW"),
    ("AAPL", "Apple", "NASDAQ", "USD"),
    ("MSFT", "Microsoft", "NASDAQ", "USD"),
    ("NVDA", "NVIDIA", "NASDAQ", "USD"),
    ("TSLA", "Tesla", "NASDAQ", "USD"),
    ("AMZN", "Amazon", "NASDAQ", "USD"),
    ("GOOGL", "Alphabet", "NASDAQ", "USD"),
    ("SPY", "SPDR S&P 500", "ETF(US)", "USD"),
    ("QQQ", "Invesco QQQ", "ETF(US)", "USD"),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    repo = Repository()
    manifest = {"generated": date.today().isoformat(), "tickers": [], "fx": ["USDKRW"]}

    for ticker, name, market, currency in TICKERS:
        print(f"sync {ticker} ({name}) ...", flush=True)
        try:
            n = sync_ticker(repo, ticker, start=START)
        except Exception as e:
            print(f"  SKIP: {e}")
            continue
        repo.upsert_ticker(ticker, name, market, currency)
        df = repo.load_prices(ticker)
        if df.empty:
            print("  SKIP: no data")
            continue
        payload = {
            "ticker": ticker,
            "name": name,
            "market": market,
            "currency": currency,
            "dates": [d.strftime("%Y-%m-%d") for d in df.index],
            "close": [round(float(v), 4) for v in df["close"]],
            "adj_close": [round(float(v), 4) for v in df["adj_close"]],
        }
        (OUT_DIR / f"{ticker}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
        manifest["tickers"].append(
            {"ticker": ticker, "name": name, "market": market, "currency": currency,
             "start": payload["dates"][0], "end": payload["dates"][-1],
             "rows": len(df)}
        )
        print(f"  ok: {len(df)} rows (fetched {n})")

    print("fetch USD/KRW ...", flush=True)
    fx = fetch_fx("USD/KRW", START)
    repo.save_fx("USDKRW", fx)
    (OUT_DIR / "USDKRW.json").write_text(json.dumps({
        "pair": "USDKRW",
        "dates": [d.strftime("%Y-%m-%d") for d in fx.index],
        "rate": [round(float(v), 4) for v in fx["rate"]],
    }, separators=(",", ":")))

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1)
    )
    print(f"done: {len(manifest['tickers'])} tickers → {OUT_DIR}")


if __name__ == "__main__":
    main()
