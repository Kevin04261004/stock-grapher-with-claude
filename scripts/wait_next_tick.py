#!/usr/bin/env python3
"""장중 10분 눈금(09:00, 09:10 … 15:30 KST)까지 기다린다.

GitHub Actions 의 cron 은 정시에 뜨지 않는다(수 분~수십 분 늦고 건너뛰기도 한다).
그래서 10분마다 워크플로를 새로 띄우는 대신, 워크플로 하나가 살아 있는 동안
이 스크립트로 다음 눈금까지 잠들었다 깨는 방식을 쓴다. 그러면 갱신 시각이
실제 벽시계 기준 정확히 :00, :10, :20 … 이 된다.

동작:
    - 다음 눈금까지 sleep 하고 종료 코드 0
    - 이번 교대(--until) 안에 남은 눈금이 없으면 아무것도 안 하고 종료 코드 1

사용법:
    python3 scripts/wait_next_tick.py --until 11:20
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

KST = dt.timezone(dt.timedelta(hours=9), "KST")

OPEN = dt.time(9, 0)  # 정규장 시작
CLOSE = dt.time(15, 30)  # 정규장 종료(동시호가 포함)
STEP = 10  # 분

# 눈금 직후(초 단위)에 깨어난 경우는 기다리지 않고 그 눈금으로 친다.
GRACE = dt.timedelta(seconds=20)


def ticks(day: dt.date) -> list[dt.datetime]:
    """그날의 10분 눈금 목록. 주말이면 빈 목록."""
    if day.weekday() >= 5:  # 토·일
        return []
    start = dt.datetime.combine(day, OPEN, tzinfo=KST)
    end = dt.datetime.combine(day, CLOSE, tzinfo=KST)
    out = []
    t = start
    while t <= end:
        out.append(t)
        t += dt.timedelta(minutes=STEP)
    return out


def parse_hhmm(text: str) -> dt.time:
    hour, _, minute = text.partition(":")
    return dt.time(int(hour), int(minute))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--until",
        default="15:30",
        help="이번 교대가 담당하는 마지막 눈금 (KST HH:MM, 기본 15:30)",
    )
    args = ap.parse_args()

    now = dt.datetime.now(KST)
    limit = args.until if args.until else "15:30"
    until = dt.datetime.combine(now.date(), parse_hhmm(limit), tzinfo=KST)

    for tick in ticks(now.date()):
        if tick > until:
            break
        if tick + GRACE < now:
            continue  # 이미 지난 눈금 — 늦게 시작했으면 건너뛴다

        wait = (tick - now).total_seconds()
        stamp = tick.strftime("%H:%M")
        if wait > 0:
            print(f"{stamp} KST 까지 {wait:.0f}초 대기", file=sys.stderr)
            time.sleep(wait)
        else:
            print(f"{stamp} KST — 바로 실행", file=sys.stderr)
        return 0

    print(f"{limit} KST 까지 남은 눈금 없음 — 교대 종료", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
