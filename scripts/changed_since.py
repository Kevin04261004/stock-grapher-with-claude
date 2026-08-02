#!/usr/bin/env python3
"""방금 만든 데이터가 이미 배포된 데이터와 실질적으로 다른지 판단한다.

`fetchedAt` 은 돌릴 때마다 바뀌므로 비교에서 뺀다. 그렇게 하지 않으면 휴장일에도
10분마다 "바뀌었다"고 판단해 의미 없는 배포가 반복된다.

사용법:
    python3 scripts/changed_since.py <배포본이 들어 있는 디렉터리>
    # 표준 출력으로 true / false
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FILES = ("markets.json", "indicators.json")
DATA = Path(__file__).resolve().parents[1] / "docs/data"

IGNORED = ("fetchedAt",)


def signature(text: str) -> str | None:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None
    for key in IGNORED:
        doc.pop(key, None)
    canonical = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: changed_since.py <디렉터리>", file=sys.stderr)
        return 2

    published = Path(sys.argv[1])
    for name in FILES:
        current = DATA / name
        if not current.exists():
            print(f"{name} 이 없음 → 변경으로 간주", file=sys.stderr)
            print("true")
            return 0

        old = published / name
        # 배포본을 못 읽으면(첫 배포 등) 그냥 배포한다.
        old_sig = signature(old.read_text(encoding="utf-8")) if old.exists() else None
        new_sig = signature(current.read_text(encoding="utf-8"))

        if old_sig != new_sig:
            print(f"{name} 달라짐", file=sys.stderr)
            print("true")
            return 0

    print("모두 같음", file=sys.stderr)
    print("false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
