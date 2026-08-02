# 지표추적자

시장·금리·물가 지표를 한 화면에서 추적하는 **모바일 우선** 웹앱.
빌드 도구·외부 라이브러리 없이 순수 HTML/CSS/JS 로 동작하며, GitHub Pages 로 배포된다.

## 현재 구현 범위

기본 골격까지 완성된 상태다.

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
- 차트는 외부 라이브러리 없이 SVG 스파크라인으로 직접 그린다

> 표시되는 값은 **샘플 데이터**이며 실제 시세가 아니다. (`docs/data/indicators.json`)

## 구조

```
docs/                        # 그대로 배포되는 정적 사이트
├── index.html
├── manifest.webmanifest
├── css/style.css
├── js/app.js                # 상태·렌더링·이벤트 (의존성 없는 ES 모듈)
├── icons/
└── data/indicators.json     # 지표 데이터
.github/workflows/deploy-pages.yml
```

### 데이터 형식

```jsonc
{
  "updatedAt": "2026-08-01",
  "source": "샘플 데이터 (실제 시세 아님)",
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

- 실제 지표 데이터 수집 파이프라인 (스케줄 워크플로우로 `indicators.json` 갱신)
- 기간 선택(1개월/6개월/1년)과 전체 차트
- 지표 임계값 알림, 지표 간 비교
