# 지표추적자

시장·금리·물가 지표를 한 화면에서 추적하는 **모바일 우선** 웹앱.
빌드 도구·외부 라이브러리 없이 순수 HTML/CSS/JS 로 동작하며, GitHub Pages 로 배포된다.

## 현재 구현 범위

- **히트맵 (첫 화면)** — 코스피 / 코스닥 두 시장의 시가총액 트리맵.
  타일 크기와 글자 크기는 시가총액, 색은 등락률(상승 빨강 / 하락 파랑)이고
  업종별로 묶인다.
  타일을 누르면 종목 상세가 열린다. 마지막에 본 시장은 기억한다.
  **미국 시장은 다루지 않는다.**
- **대시보드** — 요약 통계, 즐겨찾기 지표, 변동폭 상위 지표
- **지표 목록** — 검색 + 카테고리 필터
- **상세 시트** — 카드를 누르면 올라오는 바텀시트 (기간 최고/최저, 기간 변화율)
- **설정** — 테마(시스템/라이트/다크), 데이터 메타 정보, 즐겨찾기 초기화

모바일 대응

- 하단 탭 내비게이션, 44px 이상 터치 타깃
- iOS 노치·홈 인디케이터 대응 (`env(safe-area-inset-*)`, `viewport-fit=cover`)
- 입력 폰트 16px 로 iOS 자동 확대 방지
- 홈 화면에 추가 가능 (PWA 매니페스트 + 아이콘)
- 라이트/다크 자동 전환, `prefers-reduced-motion` 존중
- 히트맵은 화면 높이에 맞춰 자동으로 늘고 줄며, 회전하면 다시 배치된다
- 차트는 외부 라이브러리 없이 SVG 스파크라인·트리맵으로 직접 그린다

## 데이터

실제 시세를 쓴다. **실시간이 아니라 평일 장 마감 후 하루 한 번 갱신되는 종가 기준**이다.

| 데이터 | 출처 | 비고 |
| --- | --- | --- |
| 코스피·코스닥 종목 (가격·등락·시가총액·업종) | 네이버 금융 모바일 API | 시총 상위만 추림 |
| 코스피·코스닥 지수 | 네이버 금융 | 히트맵·지표 화면이 같은 값을 쓴다 |
| S&P 500 · 나스닥 · 원/달러 · 미10년물 · WTI · 비트코인 | Yahoo Finance chart API | |
| 한국 콜금리 · 소비자물가 상승률 · 실업률 | FRED (공개 CSV) | 월 단위 |

인증키가 필요한 출처는 쓰지 않으므로 별도 시크릿 설정 없이 동작한다.
수집 스크립트도 표준 라이브러리만 쓴다(설치할 의존성 없음).

> **주의**
> - 지연된 종가이고 오류·누락이 있을 수 있다. 투자 판단의 근거로 쓰지 말 것.
> - 네이버 금융 데이터는 공식 공개 API 가 아니다. 개인 학습용으로 쓰고,
>   재배포·상업적 이용은 각 출처의 이용약관을 확인해야 한다.
>   공식 경로가 필요하면 [KRX 오픈API](http://openapi.krx.co.kr) 로 바꿔 끼우면 된다
>   (무료지만 인증키 발급이 필요하고, 발급받은 키는 저장소 시크릿으로 넣어야 한다).

### 갱신

`.github/workflows/update-data.yml` 이 **평일 16:10 KST**(장 마감 15:30 이후)에 돌면서
데이터를 받아 검사하고, 바뀐 게 있으면 커밋한 뒤 바로 배포한다.
수동 실행은 Actions 탭의 *Update market data* → *Run workflow*.

로컬에서 직접 돌릴 수도 있다.

```bash
python3 scripts/fetch_markets.py       # docs/data/markets.json
python3 scripts/fetch_indicators.py    # docs/data/indicators.json
python3 scripts/check_data.py          # 내보내도 되는 상태인지 검사
```

`fetch_markets.py` 옵션: `--kospi 40 --kosdaq 30 --sectors 12`.
종목 수를 늘리면 정보량이 늘지만 휴대폰에서는 타일이 작아져 이름이 사라진다.

## 구조

```
docs/                        # 그대로 배포되는 정적 사이트
├── index.html
├── manifest.webmanifest
├── css/style.css
├── js/
│   ├── app.js               # 상태·렌더링·이벤트 (의존성 없는 ES 모듈)
│   ├── heatmap.js           # 히트맵 렌더링
│   └── treemap.js           # squarified treemap 레이아웃
├── icons/
└── data/
    ├── indicators.json      # 거시 지표
    └── markets.json         # 코스피·코스닥 종목
scripts/                     # 데이터 수집 (표준 라이브러리만)
├── http_util.py             # 재시도·레이트리밋 대응 HTTP
├── naver.py                 # 네이버 금융 API
├── yahoo.py                 # Yahoo Finance chart API
├── fetch_markets.py
├── fetch_indicators.py
└── check_data.py            # 배포 전 데이터 검사
.github/workflows/
├── deploy-pages.yml         # docs/ 변경 시 배포
└── update-data.yml          # 평일 데이터 갱신 + 배포
```

### 지표 데이터 형식

```jsonc
{
  "updatedAt": "2026-07-31",   // 가장 최근 관측치의 날짜
  "fetchedAt": "2026-08-02T05:20:00Z", // 수집을 돌린 시각
  "source": "네이버 금융 · Yahoo Finance · FRED",
  "indicators": [
    {
      "id": "kospi",
      "name": "KOSPI",
      "category": "시장",     // 카테고리 칩이 여기서 자동 생성된다
      "unit": "pt",
      "decimals": 2,          // 표시 소수 자릿수
      "value": 2712.4,        // 최신값
      "change": 12.3,         // 직전 대비 절대 변화
      "changePct": 0.46,      // 직전 대비 % 변화
      "history": [{ "d": "2026-07-03", "v": 2610.0 }]
    }
  ]
}
```

지표를 추가하려면 이 배열에 항목을 넣기만 하면 된다. 코드 수정은 필요 없다.

### 히트맵 데이터 형식

```jsonc
{
  "updatedAt": "2026-07-31",           // 종가 기준일
  "fetchedAt": "2026-08-02T05:20:00Z", // 수집을 돌린 시각
  "source": "네이버 금융",
  "capUnit": "억원",
  "markets": [
    {
      "id": "kospi",
      "name": "코스피",
      "index": { "value": 2971.44, "change": 22.71, "changePct": 0.77 },
      "sectors": [
        {
          "name": "반도체",          // 업종 = 히트맵의 1차 묶음
          "cap": 5798000,            // 업종 시가총액 합
          "changePct": 1.46,         // 시가총액 가중 등락률
          "stocks": [
            {
              "code": "005930",
              "name": "삼성전자",
              "price": 84500,        // 현재가(원)
              "change": 1700,        // 전일 대비(원)
              "changePct": 2.05,     // 타일 색을 정한다
              "cap": 4200000         // 타일 크기를 정한다 (억원)
            }
          ]
        }
      ]
    }
  ]
}
```

업종·종목을 추가하면 트리맵이 알아서 다시 배치된다. `docs/js/heatmap.js` 상수로
표현을 조정할 수 있다.

| 상수 | 뜻 |
| --- | --- |
| `COLOR_CAP` | 색이 가장 짙어지는 등락률 (기본 ±3%) |
| `FONT_MIN` / `FONT_MAX` | 타일 글자 크기 범위. 시총 1위 종목이 `FONT_MAX` 가 된다 |

글자 크기는 시장 안에서의 상대 시총으로 정하되, 타일 밖으로 넘치면 줄인다.

## 로컬 실행

`fetch` 로 JSON 을 읽기 때문에 `file://` 로 열면 동작하지 않는다. 정적 서버로 띄운다.

```bash
python3 -m http.server 8000 --directory docs
# http://localhost:8000
```

같은 와이파이의 휴대폰에서 확인하려면 `http://<PC의 IP>:8000` 으로 접속한다.

## 배포

`docs/**` 변경이 푸시되면 GitHub Actions 가 `gh-pages` 브랜치로 발행한다.
저장소 **Settings → Pages** 에서 소스를 `gh-pages` 브랜치 `/ (root)` 로 지정하면 된다.

## 다음 단계 후보

- 히트맵 기준 전환(등락률 / 거래대금 / 시가총액)과 기간 선택
- 종목 상세에 주가 차트, 히트맵에서 즐겨찾기 종목만 보기
- 지표 임계값 알림, 지표 간 비교
