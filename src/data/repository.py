"""SQLite 저장소: 스키마 생성 + 읽기/쓰기. (명세서 2.3)"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
    ticker        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    market        TEXT NOT NULL,
    sector        TEXT,
    listed_date   DATE,
    delisted_date DATE,
    currency      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prices (
    ticker    TEXT NOT NULL,
    date      DATE NOT NULL,
    open      REAL, high REAL, low REAL, close REAL,
    volume    INTEGER,
    adj_close REAL NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);

CREATE TABLE IF NOT EXISTS dividends (
    ticker TEXT, ex_date DATE, amount REAL,
    PRIMARY KEY (ticker, ex_date)
);

CREATE TABLE IF NOT EXISTS splits (
    ticker TEXT, date DATE, ratio REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    pair TEXT, date DATE, rate REAL,
    PRIMARY KEY (pair, date)
);

CREATE TABLE IF NOT EXISTS sync_log (
    ticker TEXT PRIMARY KEY,
    last_synced_date DATE,
    synced_at TIMESTAMP
);
"""

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "market.db"


class Repository:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    # ---- tickers ----
    def upsert_ticker(self, ticker: str, name: str, market: str, currency: str,
                      sector: str | None = None, listed_date: date | None = None,
                      delisted_date: date | None = None):
        self.conn.execute(
            "INSERT INTO tickers (ticker,name,market,sector,listed_date,delisted_date,currency) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
            "name=excluded.name, market=excluded.market, sector=excluded.sector, "
            "listed_date=excluded.listed_date, delisted_date=excluded.delisted_date, "
            "currency=excluded.currency",
            (ticker, name, market, sector, listed_date, delisted_date, currency),
        )
        self.conn.commit()

    def search_tickers(self, query: str) -> pd.DataFrame:
        """한글명 또는 티커로 종목 검색."""
        q = f"%{query}%"
        return pd.read_sql_query(
            "SELECT * FROM tickers WHERE ticker LIKE ? OR name LIKE ? ORDER BY ticker",
            self.conn, params=(q, q),
        )

    def universe_at(self, as_of: date) -> pd.DataFrame:
        """생존편향 대응: as_of 시점에 상장되어 있던 종목만 반환."""
        return pd.read_sql_query(
            "SELECT * FROM tickers WHERE (listed_date IS NULL OR listed_date <= ?) "
            "AND (delisted_date IS NULL OR delisted_date > ?)",
            self.conn, params=(as_of, as_of),
        )

    # ---- prices ----
    def save_prices(self, ticker: str, df: pd.DataFrame):
        """df: DatetimeIndex, columns [open, high, low, close, volume, adj_close].
        같은 (ticker, date)는 덮어쓴다 (수정주가 소급 반영 대응)."""
        def f(v):
            return float(v) if v is not None and pd.notna(v) else None

        rows = [
            (ticker, idx.date().isoformat(),
             f(row.get("open")), f(row.get("high")), f(row.get("low")), f(row.get("close")),
             int(row["volume"]) if pd.notna(row.get("volume")) else None,
             float(row["adj_close"]))
            for idx, row in df.iterrows()
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO prices (ticker,date,open,high,low,close,volume,adj_close) "
            "VALUES (?,?,?,?,?,?,?,?)", rows,
        )
        self.conn.commit()

    def load_prices(self, ticker: str, start: date | None = None,
                    end: date | None = None) -> pd.DataFrame:
        sql = "SELECT date, open, high, low, close, volume, adj_close FROM prices WHERE ticker=?"
        params: list = [ticker]
        if start:
            sql += " AND date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY date"
        df = pd.read_sql_query(sql, self.conn, params=params, parse_dates=["date"])
        return df.set_index("date")

    # ---- sync log ----
    def last_synced(self, ticker: str) -> date | None:
        row = self.conn.execute(
            "SELECT last_synced_date FROM sync_log WHERE ticker=?", (ticker,)
        ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def mark_synced(self, ticker: str, last_date: date):
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_log (ticker,last_synced_date,synced_at) "
            "VALUES (?,?,datetime('now'))", (ticker, last_date.isoformat()),
        )
        self.conn.commit()

    # ---- fx ----
    def save_fx(self, pair: str, df: pd.DataFrame):
        rows = [(pair, idx.date().isoformat(), float(v)) for idx, v in df["rate"].items()]
        self.conn.executemany(
            "INSERT OR REPLACE INTO fx_rates (pair,date,rate) VALUES (?,?,?)", rows
        )
        self.conn.commit()

    def load_fx(self, pair: str) -> pd.Series:
        df = pd.read_sql_query(
            "SELECT date, rate FROM fx_rates WHERE pair=? ORDER BY date",
            self.conn, params=(pair,), parse_dates=["date"],
        )
        return df.set_index("date")["rate"]
