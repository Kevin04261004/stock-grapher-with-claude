/**
 * UI 레이어 — 데이터 로드, 폼 바인딩, Plotly 렌더링.
 * 계산은 전부 engine.js의 순수 함수에 위임한다.
 */
"use strict";

const state = {
  manifest: null,
  cache: new Map(),   // ticker -> data json
  fx: null,           // USDKRW
  rendered: new Set(),  // 성공적으로 실행된 렌더 함수 — 테마 전환 시 재실행
};

/* ---------- 데이터 로드 (정적 JSON = 로컬 캐시) ---------- */

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`데이터 로드 실패: ${path}`);
  return res.json();
}

async function getTickerData(ticker) {
  if (!state.cache.has(ticker)) {
    state.cache.set(ticker, await loadJSON(`data/${ticker}.json`));
  }
  return state.cache.get(ticker);
}

async function getFX() {
  if (!state.fx) state.fx = await loadJSON("data/USDKRW.json");
  return state.fx;
}

/* ---------- 포맷 ---------- */

function fmtMoney(v, ccy) {
  if (ccy === "USD") return "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return "₩" + Math.round(v).toLocaleString("ko-KR");
}
function fmtPct(v, digits = 2) {
  return (v >= 0 ? "+" : "") + (v * 100).toFixed(digits) + "%";
}
function pctClass(v) { return v >= 0 ? "pos" : "neg"; }

function tile(label, value, cls = "", sub = "") {
  return `<div class="tile"><div class="k">${label}</div>` +
    `<div class="v ${cls}">${value}</div>` +
    (sub ? `<div class="s">${sub}</div>` : "") + `</div>`;
}

/* ---------- Plotly 공통 ---------- */

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function baseLayout(overrides = {}) {
  return Object.assign({
    paper_bgcolor: cssVar("--surface"),
    plot_bgcolor: cssVar("--surface"),
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: cssVar("--ink-2"), size: 12 },
    margin: { l: 60, r: 20, t: 40, b: 60 },
    xaxis: { gridcolor: cssVar("--grid"), linecolor: cssVar("--baseline"), zerolinecolor: cssVar("--baseline") },
    yaxis: { gridcolor: cssVar("--grid"), linecolor: cssVar("--baseline"), zerolinecolor: cssVar("--baseline") },
    hovermode: "x unified",
    showlegend: true,
    legend: { orientation: "h", y: -0.28 },
  }, overrides);
}

const PLOTLY_CONF = { responsive: true, displaylogo: false, locale: "ko" };

function seriesColors() {
  return [cssVar("--series-1"), cssVar("--series-2"), cssVar("--series-3"), cssVar("--series-4")];
}

function plot(el, traces, layout) {
  Plotly.newPlot(el, traces, layout, PLOTLY_CONF);
}

/* ---------- 초기화 ---------- */

async function init() {
  state.manifest = await loadJSON("data/manifest.json");
  const sel = document.getElementById("tickerSel");
  for (const t of state.manifest.tickers) {
    const opt = document.createElement("option");
    opt.value = t.ticker;
    opt.textContent = `${t.name} (${t.ticker} · ${t.market})`;
    sel.appendChild(opt);
  }
  sel.addEventListener("change", updateDataRange);
  updateDataRange();
  document.getElementById("genDate").textContent = `데이터 스냅샷: ${state.manifest.generated}`;

  // 날짜 기본값
  const today = state.manifest.tickers[0].end;
  const set = (id, v) => { document.getElementById(id).value = v; };
  set("btBuy", addMonths(today, -36)); set("btSell", today);
  set("dcaStart", addMonths(today, -60)); set("dcaEnd", today);
  set("cmpStart", addMonths(today, -60));

  // 탭
  document.getElementById("tabs").addEventListener("click", e => {
    if (e.target.tagName !== "BUTTON") return;
    document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("active", b === e.target));
    document.querySelectorAll(".panel").forEach(p =>
      p.classList.toggle("active", p.id === "panel-" + e.target.dataset.tab));
  });

  // 테마 토글 — 전환 후 기존 차트를 새 팔레트로 재렌더
  document.getElementById("themeToggle").addEventListener("click", async () => {
    const root = document.documentElement;
    const cur = root.dataset.theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    root.dataset.theme = cur === "dark" ? "light" : "dark";
    for (const fn of state.rendered) {
      try { await fn(); } catch (_) { /* 입력이 바뀐 패널은 건너뜀 */ }
    }
  });

  // 비교 pills
  const pills = document.getElementById("cmpPills");
  state.manifest.tickers.forEach((t, i) => {
    const b = document.createElement("button");
    b.className = "pill" + (i < 2 ? " on" : "");
    b.textContent = t.name;
    b.dataset.ticker = t.ticker;
    b.addEventListener("click", () => {
      if (!b.classList.contains("on") &&
          document.querySelectorAll("#cmpPills .pill.on").length >= 4) {
        alert("팔레트 가독성을 위해 최대 4개까지 비교할 수 있습니다.");
        return;
      }
      b.classList.toggle("on");
    });
    pills.appendChild(b);
  });

  document.getElementById("btRun").addEventListener("click", guard(runBT));
  document.getElementById("cmpRun").addEventListener("click", guard(runCMP));
  document.getElementById("dcaRun").addEventListener("click", guard(runDCAUI));
  document.getElementById("distRun").addEventListener("click", guard(runDIST));
  document.getElementById("levRun").addEventListener("click", guard(runLEV));
  document.getElementById("beRun").addEventListener("click", guard(runBE));
}

function guard(fn) {
  return async () => {
    try {
      await fn();
      state.rendered.add(fn);
    } catch (e) { alert(e.message); }
  };
}

function currentTicker() { return document.getElementById("tickerSel").value; }
function currentMeta() {
  return state.manifest.tickers.find(t => t.ticker === currentTicker());
}
function currentCosts(currency) {
  return costModelFor(currency, document.getElementById("useCosts").checked);
}

function updateDataRange() {
  const m = currentMeta();
  if (m) document.getElementById("dataRange").textContent =
    `보유 데이터: ${m.start} ~ ${m.end} (${m.rows.toLocaleString()}일)`;
}

/* ---------- Phase 1: 단일 백테스트 ---------- */

async function runBT() {
  const meta = currentMeta();
  const data = await getTickerData(meta.ticker);
  const buy = document.getElementById("btBuy").value;
  const sell = document.getElementById("btSell").value;
  const amount = Number(document.getElementById("btAmount").value);
  const r = runBacktest(data, buy, sell, amount, currentCosts(meta.currency));

  const out = document.getElementById("btOut");
  out.innerHTML = `
    <div class="metrics">
      ${tile("최종 평가액", fmtMoney(r.finalValue, meta.currency), pctClass(r.totalReturn))}
      ${tile("총수익률", fmtPct(r.totalReturn), pctClass(r.totalReturn))}
      ${tile("CAGR (연평균)", fmtPct(r.cagr), pctClass(r.cagr))}
      ${tile("MDD (최대낙폭)", fmtPct(r.mdd), "neg")}
      ${tile("변동성 (연환산)", (r.volatility * 100).toFixed(1) + "%")}
      ${tile("샤프 지수", r.sharpe.toFixed(2))}
      ${tile("기간 최고가", fmtMoney(r.periodHigh, meta.currency), "", "수정주가 기준")}
      ${tile("기간 최저가", fmtMoney(r.periodLow, meta.currency), "", "수정주가 기준")}
    </div>
    <p class="note">체결: ${r.buyDate} 매수 → ${r.sellDate} 매도 (휴장일은 다음 영업일 이월)</p>
    <div class="chart" id="btChart"></div>
    <div class="chart" id="btDD"></div>`;

  const c = seriesColors();
  plot(document.getElementById("btChart"), [{
    x: r.dates, y: r.equity, type: "scatter", mode: "lines",
    name: "평가액", line: { color: c[0], width: 2 },
    hovertemplate: "%{y:,.0f}<extra></extra>",
  }], baseLayout({ title: { text: `${meta.name} 평가액 곡선`, font: { size: 14, color: cssVar("--ink") } }, showlegend: false }));

  plot(document.getElementById("btDD"), [{
    x: r.dates, y: r.drawdowns, type: "scatter", mode: "lines",
    name: "낙폭", line: { color: c[1], width: 2 }, fill: "tozeroy",
    hovertemplate: "%{y:.1%}<extra></extra>",
  }], baseLayout({
    title: { text: "낙폭(Drawdown) — 하방 위험", font: { size: 14, color: cssVar("--ink") } },
    yaxis: { tickformat: ".0%", gridcolor: cssVar("--grid"), linecolor: cssVar("--baseline") },
    showlegend: false,
  }));
}

/* ---------- Phase 2: 종목 비교 ---------- */

async function runCMP() {
  const sel = [...document.querySelectorAll("#cmpPills .pill.on")].map(b => b.dataset.ticker);
  if (sel.length < 2) throw new Error("2개 이상 선택하세요.");
  const startDate = document.getElementById("cmpStart").value;
  const baseCcy = document.getElementById("cmpCcy").value;
  const fx = await getFX();

  const seriesList = [];
  for (const t of sel) {
    const meta = state.manifest.tickers.find(x => x.ticker === t);
    const data = await getTickerData(t);
    let values = data.adj_close;
    if (meta.currency !== baseCcy) {
      values = convertCurrency(data, fx, baseCcy === "KRW");
    }
    const from = nextTradingIdx(data.dates, startDate);
    seriesList.push({
      label: meta.name,
      dates: data.dates.slice(from < 0 ? 0 : from),
      values: values.slice(from < 0 ? 0 : from),
    });
  }
  const norm = normalizeForComparison(seriesList);
  const corr = correlationMatrix(norm);

  // 지표 테이블
  const rows = norm.series.map(s => {
    const rets = dailyReturns(s.raw);
    const years = (new Date(norm.dates[norm.dates.length - 1]) - new Date(norm.dates[0])) / 86400000 / 365;
    const tr = s.raw[s.raw.length - 1] / s.raw[0] - 1;
    return {
      label: s.label, tr,
      cagr: cagr(s.raw[0], s.raw[s.raw.length - 1], years),
      mdd: maxDrawdown(s.raw).mdd,
      vol: annualizedVolatility(rets),
      sharpe: sharpeRatio(rets),
    };
  });

  const out = document.getElementById("cmpOut");
  out.innerHTML = `
    <div class="chart" id="cmpChart"></div>
    <h3>지표 비교 (${baseCcy} 기준, 공통 구간 ${norm.dates[0]} ~ ${norm.dates[norm.dates.length - 1]})</h3>
    <table class="simple"><thead><tr>
      <th>종목</th><th>총수익률</th><th>CAGR</th><th>MDD</th><th>변동성</th><th>샤프</th>
    </tr></thead><tbody>
      ${rows.map(r => `<tr><td>${r.label}</td><td>${fmtPct(r.tr)}</td><td>${fmtPct(r.cagr)}</td>
        <td>${fmtPct(r.mdd)}</td><td>${(r.vol * 100).toFixed(1)}%</td><td>${r.sharpe.toFixed(2)}</td></tr>`).join("")}
    </tbody></table>
    <h3>상관계수 행렬 (일간 수익률)</h3>
    <table class="simple"><thead><tr><th></th>${norm.series.map(s => `<th>${s.label}</th>`).join("")}</tr></thead>
    <tbody>${corr.map((row, i) =>
      `<tr><td>${norm.series[i].label}</td>${row.map(v => `<td>${v.toFixed(3)}</td>`).join("")}</tr>`).join("")}
    </tbody></table>`;

  const c = seriesColors();
  plot(document.getElementById("cmpChart"),
    norm.series.map((s, i) => ({
      x: norm.dates, y: s.values, type: "scatter", mode: "lines",
      name: s.label, line: { color: c[i], width: 2 },
      hovertemplate: "%{y:.1f}<extra>" + s.label + "</extra>",
    })),
    baseLayout({ title: { text: "정규화 성과 (시작=100)", font: { size: 14, color: cssVar("--ink") } } }));
}

/* ---------- Phase 2: DCA ---------- */

async function runDCAUI() {
  const meta = currentMeta();
  const data = await getTickerData(meta.ticker);
  const r = runDCA(
    data,
    document.getElementById("dcaStart").value,
    document.getElementById("dcaEnd").value,
    document.getElementById("dcaFreq").value,
    Number(document.getElementById("dcaAmount").value),
    currentCosts(meta.currency),
    document.getElementById("dcaFrac").checked,
  );

  const diff = r.finalValue - r.lumpSumFinalValue;
  const out = document.getElementById("dcaOut");
  out.innerHTML = `
    <div class="metrics">
      ${tile("총 투입금", fmtMoney(r.totalInvested, meta.currency), "", `매수 ${r.nPurchases}회`)}
      ${tile("최종 평가액", fmtMoney(r.finalValue, meta.currency), pctClass(r.finalValue - r.totalInvested))}
      ${tile("XIRR (연환산·주 지표)", fmtPct(r.xirr), pctClass(r.xirr), "적립식은 CAGR이 아닌 XIRR로 평가")}
      ${tile("평균 매입단가", fmtMoney(r.avgBuyPrice, meta.currency), "", `최종가 ${fmtMoney(r.finalPrice, meta.currency)}`)}
      ${tile("일시불이었다면", fmtMoney(r.lumpSumFinalValue, meta.currency), pctClass(r.lumpSumReturn),
        `적립식 ${diff >= 0 ? "우세" : "열세"} ${fmtMoney(Math.abs(diff), meta.currency)}`)}
    </div>
    <div class="chart" id="dcaChart"></div>`;

  const c = seriesColors();
  plot(document.getElementById("dcaChart"), [
    { x: r.dates, y: r.investedCurve, type: "scatter", mode: "lines",
      name: "누적 투입금", line: { color: c[1], width: 2, dash: "dot" },
      hovertemplate: "%{y:,.0f}<extra>투입금</extra>" },
    { x: r.dates, y: r.valueCurve, type: "scatter", mode: "lines",
      name: "평가액", line: { color: c[0], width: 2 },
      hovertemplate: "%{y:,.0f}<extra>평가액</extra>" },
  ], baseLayout({ title: { text: `${meta.name} 적립식 — 투입금 vs 평가액`, font: { size: 14, color: cssVar("--ink") } } }));
}

/* ---------- Phase 3: 분포 ---------- */

async function runDIST() {
  const meta = currentMeta();
  const data = await getTickerData(meta.ticker);
  const months = Number(document.getElementById("distMonths").value);
  const r = analyzeDistribution(data.adj_close, months * TRADING_DAYS_PER_MONTH);
  const curve = lossProbabilityCurve(data.adj_close);

  const out = document.getElementById("distOut");
  out.innerHTML = `
    <div class="metrics">
      ${tile("손실 확률", (r.lossProbability * 100).toFixed(1) + "%",
        r.lossProbability > 0.3 ? "neg" : "", "수익률 < 0으로 끝난 진입 시점 비율")}
      ${tile("하위 5% (최악)", fmtPct(r.worst5pct), "neg", "이보다 나쁠 확률 5%")}
      ${tile("중앙값", fmtPct(r.median), pctClass(r.median))}
      ${tile("평균", fmtPct(r.mean), pctClass(r.mean))}
      ${tile("표준편차", (r.std * 100).toFixed(1) + "%p")}
      ${tile("표본 수", r.nWindows.toLocaleString() + "개", "", "모든 가능한 진입 시점")}
    </div>
    <div class="chart" id="distChart"></div>
    <div class="chart" id="lossChart"></div>
    <p class="note">손실 확률과 하위 5%를 먼저 보세요 — 단일 시나리오의 화려한 수익률보다
      분포와 하방 위험이 실제 의사결정에 유용합니다.</p>`;

  const c = seriesColors();
  plot(document.getElementById("distChart"), [{
    x: r.returns, type: "histogram", nbinsx: 80,
    marker: { color: c[0] }, name: "빈도",
    hovertemplate: "수익률 %{x:.0%}: %{y}건<extra></extra>",
  }], baseLayout({
    title: { text: `${meta.name} — ${months}개월 보유 수익률 분포 (전체 진입 시점 ${r.nWindows.toLocaleString()}건)`,
      font: { size: 14, color: cssVar("--ink") } },
    xaxis: { tickformat: ".0%", gridcolor: cssVar("--grid"), linecolor: cssVar("--baseline") },
    showlegend: false, bargap: 0.05,
    shapes: [{ type: "line", x0: 0, x1: 0, yref: "paper", y0: 0, y1: 1,
      line: { color: cssVar("--bad"), width: 1.5, dash: "dash" } }],
  }));

  plot(document.getElementById("lossChart"), [{
    x: curve.map(p => p.months), y: curve.map(p => p.lossProb),
    type: "scatter", mode: "lines+markers",
    line: { color: c[1], width: 2 }, marker: { size: 8 },
    hovertemplate: "%{x}개월 보유: 손실확률 %{y:.1%}<extra></extra>",
  }], baseLayout({
    title: { text: "보유기간별 손실확률", font: { size: 14, color: cssVar("--ink") } },
    xaxis: { title: { text: "보유기간 (개월)" }, gridcolor: cssVar("--grid"), linecolor: cssVar("--baseline") },
    yaxis: { tickformat: ".0%", rangemode: "tozero", gridcolor: cssVar("--grid"), linecolor: cssVar("--baseline") },
    showlegend: false,
  }));
}

/* ---------- Phase 3: 레버리지 ---------- */

async function runLEV() {
  const meta = currentMeta();
  const data = await getTickerData(meta.ticker);
  const lev = Number(document.getElementById("levX").value);
  const er = Number(document.getElementById("levER").value) / 100;
  const fr = Number(document.getElementById("levFR").value) / 100;
  const years = Number(document.getElementById("levYears").value);

  const cutoff = addMonths(data.dates[data.dates.length - 1], -12 * years);
  let i0 = nextTradingIdx(data.dates, cutoff);
  if (i0 < 0) i0 = 0;
  const adj = data.adj_close.slice(i0);
  const dates = data.dates.slice(i0 + 1);
  const rets = dailyReturns(adj);
  const r = analyzeLeverage(rets, lev, er, fr);

  const out = document.getElementById("levOut");
  out.innerHTML = `
    <div class="metrics">
      ${tile("기초자산", fmtPct(r.baseReturn), pctClass(r.baseReturn), `${meta.name} · 최근 ${years}년`)}
      ${tile(`${lev}x 상품 (실제 재현)`, fmtPct(r.levReturn), pctClass(r.levReturn), "일간 리밸런싱 + 보수 + 차입비용")}
      ${tile(`기초 × ${lev} (흔한 오해)`, fmtPct(r.naiveReturn), pctClass(r.naiveReturn), "기간수익률 단순 곱")}
      ${tile("감쇄 손실분", (r.decay * 100).toFixed(1) + "%p", r.decay > 0 ? "neg" : "pos", "오해 대비 실제 성과 괴리")}
    </div>
    <div class="chart" id="levChart"></div>`;

  const c = seriesColors();
  plot(document.getElementById("levChart"), [
    { x: dates, y: r.basePath, name: "기초자산", type: "scatter", mode: "lines",
      line: { color: c[0], width: 2 }, hovertemplate: "%{y:.2f}<extra>기초</extra>" },
    { x: dates, y: r.levPath, name: `${lev}x 일간 리밸런싱`, type: "scatter", mode: "lines",
      line: { color: c[1], width: 2 }, hovertemplate: "%{y:.2f}<extra>" + lev + "x</extra>" },
    { x: dates, y: r.naivePath, name: `기초 × ${lev} (가상)`, type: "scatter", mode: "lines",
      line: { color: c[2], width: 2, dash: "dot" }, hovertemplate: "%{y:.2f}<extra>가상</extra>" },
  ], baseLayout({ title: { text: "누적 성과 경로 (1.0 시작)", font: { size: 14, color: cssVar("--ink") } } }));
}

function runBE() {
  const loss = Number(document.getElementById("beLoss").value) / 100;
  const need = breakevenRequiredGain(loss);
  const rows = [10, 20, 30, 40, 50, 60, 70, 80, 90].map(l => {
    const n = breakevenRequiredGain(l / 100);
    return `<tr><td>-${l}%</td><td>${fmtPct(n, 1)}</td></tr>`;
  }).join("");
  document.getElementById("beOut").innerHTML = `
    <div class="metrics">
      ${tile(`현재 -${(loss * 100).toFixed(0)}% 손실이라면`, fmtPct(need, 1), "neg",
        "본전까지 상품 가격이 올라야 하는 폭")}
    </div>
    <p class="note">레버리지 상품은 하락 후 같은 폭의 기초자산 반등으로는 본전에 못 돌아옵니다
      (변동성 감쇄). 손실이 깊어질수록 필요 상승폭은 비선형으로 커집니다.</p>
    <table class="simple" style="max-width:360px">
      <thead><tr><th>손실률</th><th>본전 필요 상승률</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
}

init().catch(e => {
  document.querySelector(".wrap").insertAdjacentHTML("beforeend",
    `<p class="error">초기화 실패: ${e.message}</p>`);
});
