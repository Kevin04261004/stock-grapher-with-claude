"""수집 스크립트 공용 HTTP 도우미.

CI 에서 별도 설치 없이 돌도록 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request

# 짧은 UA 를 쓰는 데는 이유가 있다. Yahoo 의 엣지는 상세한 브라우저 UA 와
# 도구 UA(curl/python-urllib) 를 429 로 돌려보내면서 이 값만 통과시킨다.
# 네이버·FRED 도 이 값으로 정상 응답한다(FRED 는 minimal=True 로 헤더를 비운다).
UA = "Mozilla/5.0"

RETRIES = 4
BACKOFF = 1.5
# 429(레이트리밋)는 네트워크 오류보다 오래 기다려야 풀린다.
THROTTLE_BACKOFF = 8.0
# 데이터 제공처에 부담을 주지 않도록 요청 간 최소 간격을 둔다.
MIN_INTERVAL = 0.12

_last_call = 0.0


class FetchError(RuntimeError):
    pass


def fetch(url: str, *, headers: dict | None = None, timeout: int = 20,
          minimal: bool = False) -> bytes:
    """
    GET 요청. 실패하면 몇 번 다시 시도하고, 그래도 안 되면 FetchError.

    minimal=True 면 브라우저 흉내 헤더를 붙이지 않는다. FRED 처럼 브라우저
    User-Agent 를 받으면 응답을 끊어 버리는 곳이 있다.
    """
    global _last_call

    req_headers = {} if minimal else {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    if headers:
        req_headers.update(headers)

    last_error: Exception | None = None
    for attempt in range(RETRIES):
        gap = MIN_INTERVAL - (time.monotonic() - _last_call)
        if gap > 0:
            time.sleep(gap)
        _last_call = time.monotonic()

        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as res:
                raw = res.read()
                if res.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as err:
            last_error = err
            if err.code not in (429, 500, 502, 503, 504) or attempt == RETRIES - 1:
                break
            # 레이트리밋은 잠깐 기다리면 풀린다. Retry-After 가 오면 그걸 따른다.
            wait = to_number(err.headers.get("Retry-After")) if err.headers else None
            time.sleep(min(float(wait or 0), 30) or THROTTLE_BACKOFF * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            last_error = err
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))

    raise FetchError(f"{url} 요청 실패: {last_error}")


def fetch_json(url: str, **kwargs) -> dict:
    raw = fetch(url, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise FetchError(f"{url} JSON 파싱 실패: {err}") from err


def to_number(text, default=None):
    """'15,346,481' → 15346481, '26.81' → 26.81, '-'/'N/A' → default"""
    if text is None:
        return default
    if isinstance(text, (int, float)):
        return text

    cleaned = str(text).replace(",", "").replace("%", "").strip()
    if cleaned in ("", "-", "N/A", "null"):
        return default
    try:
        value = float(cleaned)
    except ValueError:
        return default
    return int(value) if value.is_integer() else value
