# 📈 주식 백테스팅 시뮬레이터

한국(KRX) + 미국 시장의 과거 주가 데이터로 수익률을 계산·시각화하는 **local-first** 백테스팅 도구.

**🌐 웹 데모 (GitHub Pages)**: https://kevin04261004.github.io/stock-grapher-with-claude/

## 기능

| 기능 | 설명 |
|---|---|
| 단일 백테스트 | 구간 매수/매도 수익률, CAGR, MDD, 변동성, 샤프 |
| 종목 비교 | 시작=100 정규화 오버레이, 지표 테이블, 상관계수 행렬, 통화 환산 |
| 적립식(DCA) | 매월/매주/매분기 적립 시뮬레이션 — **XIRR** 주 지표, 일시불 대비 비교 |
| 진입 시점 분포 ★ | 과거 *모든* 진입 시점 백테스트 → 수익률 분포·손실확률·하위 5% (체리피킹 차단) |
| 레버리지 시뮬 | 일간 리밸런싱 재현으로 **변동성 감쇄** 정량화 + 손익분기 계산기 |

## 구조

```
├── src/
│   ├── data/          # FDR 래퍼, SQLite 저장소, 증분 동기화
│   ├── engine/        # ★ 순수 계산 엔진 (UI 의존성 없음)
│   │   ├── metrics.py     # CAGR/XIRR/MDD/Sharpe/Sortino
│   │   ├── backtest.py    # 단일 구간 + 종목 비교
│   │   ├── dca.py         # 적립식
│   │   ├── distribution.py# 진입 시점 분포 (numpy 벡터화)
│   │   ├── leverage.py    # 레버리지 감쇄
│   │   └── costs.py       # 수수료/세금/슬리피지
│   ├── models.py      # 데이터클래스
│   └── app/main.py    # Streamlit UI
├── tests/             # 엔진 단위 테스트 (33개)
├── scripts/export_web_data.py   # 웹용 데이터 스냅샷 생성
└── docs/              # GitHub Pages 정적 웹앱 (엔진의 JS 포팅판)
    ├── js/engine.js   # Python 엔진과 결과 일치 검증됨
    └── data/*.json    # 주가 스냅샷 (로컬 캐시 역할)
```

## 실행

### 웹 (GitHub Pages)
정적 웹앱은 `docs/`에서 서빙된다. 계산 엔진(`docs/js/engine.js`)은 Python 엔진의 포팅판이며,
동일 데이터에 대해 **소수점 6자리까지 결과가 일치**함을 검증했다.
Streamlit은 서버가 필요해 Pages에 올릴 수 없으므로, 웹 버전은 순수 클라이언트 사이드로 구현했다.

```bash
# 로컬 미리보기
cd docs && python -m http.server 8000
```

### Streamlit (로컬)
```bash
pip install -r requirements.txt
streamlit run src/app/main.py
```

### 데이터 갱신
```bash
python scripts/export_web_data.py   # FDR에서 받아 SQLite 캐시 + docs/data JSON 갱신
```

### 테스트
```bash
python -m pytest tests/ -v
```

## 설계 원칙 (명세서 기준)

1. **네트워크 최소화** — 데이터는 로컬 캐시(SQLite / 정적 JSON)에서 읽는다. 웹 버전은 Plotly까지 로컬 번들.
2. **엔진 순수성** — `src/engine/`은 UI를 import하지 않는다.
3. **정확성 우선** — XIRR은 Excel 정의식과 동일(테스트로 검증), 모든 수익률은 수정주가 기준.

### 함정 대응
- **생존편향**: 스키마에 `delisted_date` 보유, 상폐 시 강제 청산 로직 구현. 단, 현재 데이터셋은
  상장 유지 종목만 포함하므로 **UI에 편향 존재를 명시**함.
- **수정주가**: 모든 수익률 계산은 `adj_close`, 원주가는 표시 전용.
- **미래참조**: 매수 예정일이 휴장일이면 다음 영업일 체결. 당일 종가 매수 없음.

## 면책

이 도구는 과거 데이터의 기술적 분석 도구이며 미래 수익을 예측하지 않는다.
백테스트 결과에는 생존편향·과최적화 위험이 내재하며, 투자 판단의 근거로 사용 시 책임은 사용자에게 있다.
