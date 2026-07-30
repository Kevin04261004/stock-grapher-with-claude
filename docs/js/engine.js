/**
 * 계산 엔진 (Python src/engine의 JavaScript 포팅판).
 * 순수 함수만 포함 — DOM/차트 의존성 없음.
 * 모든 수익률 계산은 수정주가(adj_close) 기준.
 */
"use strict";

const TRADING_DAYS_PER_YEAR = 252;
const TRADING_DAYS_PER_MONTH = 21;

/* ---------- 기본 지표 ---------- */

function totalReturn(values) {
  if (values.length < 2 || values[0] === 0) return 0;
  return values[values.length - 1] / values[0] - 1;
}

function cagr(startValue, endValue, years) {
  if (startValue <= 0 || endValue <= 0 || years <= 0) return 0;
  return Math.pow(endValue / startValue, 1 / years) - 1;
}

function maxDrawdown(values) {
  let peak = -Infinity, mdd = 0;
  const dd = new Array(values.length);
  for (let i = 0; i < values.length; i++) {
    if (values[i] > peak) peak = values[i];
    dd[i] = values[i] / peak - 1;
    if (dd[i] < mdd) mdd = dd[i];
  }
  return { mdd, drawdowns: dd };
}

function dailyReturns(values) {
  const out = new Array(values.length - 1);
  for (let i = 1; i < values.length; i++) out[i - 1] = values[i] / values[i - 1] - 1;
  return out;
}

function mean(a) { return a.reduce((s, v) => s + v, 0) / a.length; }

function std(a, ddof = 1) {
  if (a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((s, v) => s + (v - m) * (v - m), 0) / (a.length - ddof));
}

function annualizedVolatility(rets) {
  return std(rets) * Math.sqrt(TRADING_DAYS_PER_YEAR);
}

function sharpeRatio(rets, riskFree = 0) {
  if (rets.length < 2) return 0;
  const rf = riskFree / TRADING_DAYS_PER_YEAR;
  const excess = rets.map(r => r - rf);
  const s = std(excess);
  if (s === 0) return 0;
  return mean(excess) / s * Math.sqrt(TRADING_DAYS_PER_YEAR);
}

function percentile(sorted, p) {
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  return percentile(s, 0.5);
}

/**
 * XIRR — 내부수익률 (연환산). Excel XIRR() 정의식과 동일:
 * sum(cf / (1+r)^(days/365)) = 0 의 근을 이분탐색으로 구한다.
 * cashflows: [{date: Date, amount: number}], 유출 음수 / 유입 양수.
 */
function xirr(cashflows) {
  if (cashflows.length < 2) throw new Error("XIRR requires at least 2 cashflows");
  const cfs = [...cashflows].sort((a, b) => a.date - b.date);
  const t0 = cfs[0].date;
  const times = cfs.map(c => (c.date - t0) / 86400000 / 365);
  if (Math.max(...times) === 0) throw new Error("XIRR requires cashflows spanning more than one day");
  const npv = r => cfs.reduce((s, c, i) => s + c.amount / Math.pow(1 + r, times[i]), 0);

  let lo = -0.9999, hi = 10;
  let fLo = npv(lo), fHi = npv(hi);
  while (fLo * fHi > 0 && hi < 1e6) { hi *= 10; fHi = npv(hi); }
  if (fLo * fHi > 0) throw new Error("XIRR did not converge");
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    const fMid = npv(mid);
    if (fLo * fMid <= 0) { hi = mid; fHi = fMid; } else { lo = mid; fLo = fMid; }
    if (hi - lo < 1e-10) break;
  }
  return (lo + hi) / 2;
}

/* ---------- 거래 비용 ---------- */

const COST_PRESETS = {
  KR: { buyFee: 0.00015, sellFee: 0.00015, sellTax: 0.0018, slippage: 0.0005, fxSpread: 0 },
  US: { buyFee: 0, sellFee: 0, sellTax: 0, slippage: 0.0003, fxSpread: 0.001 },
  ZERO: { buyFee: 0, sellFee: 0, sellTax: 0, slippage: 0, fxSpread: 0 },
};

function buyCostRate(c) { return c.buyFee + c.slippage + c.fxSpread / 2; }
function sellCostRate(c) { return c.sellFee + c.sellTax + c.slippage + c.fxSpread / 2; }

function costModelFor(currency, useCosts) {
  if (!useCosts) return COST_PRESETS.ZERO;
  return currency === "KRW" ? COST_PRESETS.KR : COST_PRESETS.US;
}

/* ---------- 날짜 유틸 ---------- */

/** dates: "YYYY-MM-DD" 오름차순 배열. target 이후(포함) 첫 거래일 인덱스. 없으면 -1. */
function nextTradingIdx(dates, target) {
  let lo = 0, hi = dates.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] < target) lo = mid + 1; else hi = mid;
  }
  return lo < dates.length ? lo : -1;
}

function addMonths(iso, n) {
  const [y, m, d] = iso.split("-").map(Number);
  const total = (m - 1) + n;
  const ny = y + Math.floor(total / 12);
  const nm = (total % 12 + 12) % 12 + 1;
  const lastDay = new Date(Date.UTC(ny, nm, 0)).getUTCDate();
  const nd = Math.min(d, lastDay);
  return `${ny}-${String(nm).padStart(2, "0")}-${String(nd).padStart(2, "0")}`;
}

function addDays(iso, n) {
  const dt = new Date(iso + "T00:00:00Z");
  dt.setUTCDate(dt.getUTCDate() + n);
  return dt.toISOString().slice(0, 10);
}

/* ---------- Phase 1: 단일 구간 백테스트 ---------- */

/**
 * data: {dates, adj_close}, costs: 비용 모델.
 * 매수/매도일이 휴장일이면 다음 영업일로 이월.
 */
function runBacktest(data, buyDate, sellDate, amount, costs) {
  if (buyDate >= sellDate) throw new Error("매수일이 매도일보다 빨라야 합니다");
  const i0 = nextTradingIdx(data.dates, buyDate);
  if (i0 < 0) throw new Error("매수일 이후 거래일이 없습니다");
  let i1 = nextTradingIdx(data.dates, sellDate);
  if (i1 < 0) i1 = data.dates.length - 1;
  if (i1 - i0 < 1) throw new Error("구간에 데이터가 부족합니다");

  const adj = data.adj_close.slice(i0, i1 + 1);
  const dates = data.dates.slice(i0, i1 + 1);
  const netInvest = amount * (1 - buyCostRate(costs));
  const shares = netInvest / adj[0];
  const equity = adj.map(p => shares * p);
  const finalValue = equity[equity.length - 1] * (1 - sellCostRate(costs));
  equity[equity.length - 1] = finalValue;

  const years = (new Date(dates[dates.length - 1]) - new Date(dates[0])) / 86400000 / 365;
  const { mdd, drawdowns } = maxDrawdown(adj);
  const rets = dailyReturns(adj);

  return {
    buyDate: dates[0], sellDate: dates[dates.length - 1],
    invested: amount, finalValue,
    totalReturn: finalValue / amount - 1,
    cagr: years > 0 ? cagr(amount, finalValue, years) : 0,
    mdd, volatility: annualizedVolatility(rets), sharpe: sharpeRatio(rets),
    periodHigh: Math.max(...adj), periodLow: Math.min(...adj),
    dates, equity, drawdowns,
  };
}

/* ---------- Phase 2: 종목 비교 ---------- */

/** 여러 시계열을 공통 거래일 교집합에서 시작=100으로 정규화. */
function normalizeForComparison(seriesList) {
  // seriesList: [{label, dates, values}]
  const common = seriesList.reduce((acc, s) => {
    const set = new Set(s.dates);
    return acc === null ? new Set(s.dates) : new Set([...acc].filter(d => set.has(d)));
  }, null);
  const dates = [...common].sort();
  if (dates.length < 2) throw new Error("겹치는 기간이 없습니다");
  const out = seriesList.map(s => {
    const map = new Map(s.dates.map((d, i) => [d, s.values[i]]));
    const vals = dates.map(d => map.get(d));
    const base = vals[0];
    return { label: s.label, values: vals.map(v => v / base * 100), raw: vals };
  });
  return { dates, series: out };
}

function correlationMatrix(normalized) {
  const retsList = normalized.series.map(s => dailyReturns(s.raw));
  const n = retsList.length;
  const mat = [];
  for (let i = 0; i < n; i++) {
    mat.push([]);
    for (let j = 0; j < n; j++) {
      mat[i].push(pearson(retsList[i], retsList[j]));
    }
  }
  return mat;
}

function pearson(a, b) {
  const ma = mean(a), mb = mean(b);
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < a.length; i++) {
    num += (a[i] - ma) * (b[i] - mb);
    da += (a[i] - ma) ** 2;
    db += (b[i] - mb) ** 2;
  }
  const den = Math.sqrt(da * db);
  return den === 0 ? 0 : num / den;
}

/** KRW 기준통화로 환산: USD 종목 가격 × USDKRW 환율 (날짜 정렬, 직전값 채움) */
function convertCurrency(data, fx, toKRW) {
  const rateMap = new Map(fx.dates.map((d, i) => [d, fx.rate[i]]));
  let lastRate = fx.rate[0];
  const values = data.dates.map((d, i) => {
    if (rateMap.has(d)) lastRate = rateMap.get(d);
    return toKRW ? data.adj_close[i] * lastRate : data.adj_close[i] / lastRate;
  });
  return values;
}

/* ---------- Phase 2: 적립식(DCA) ---------- */

function buildSchedule(start, end, frequency) {
  const dates = [];
  let cur = start;
  while (cur <= end) {
    dates.push(cur);
    if (frequency === "monthly") cur = addMonths(cur, 1);
    else if (frequency === "quarterly") cur = addMonths(cur, 3);
    else cur = addDays(cur, 7);
  }
  return dates;
}

/**
 * 적립식 시뮬레이션. 휴장일은 다음 영업일 체결, 중복 체결일은 1회로 합침.
 * allowFractional=false면 정수 주수만 매수, 잔액은 현금 보유.
 * 주 지표는 XIRR.
 */
function runDCA(data, start, end, frequency, amountPerPeriod, costs, allowFractional = true) {
  const schedule = buildSchedule(start, end, frequency);
  const execIdx = [];
  for (const d of schedule) {
    const i = nextTradingIdx(data.dates, d);
    if (i < 0 || data.dates[i] > end) continue;
    if (execIdx.length && i === execIdx[execIdx.length - 1]) continue;
    execIdx.push(i);
  }
  if (!execIdx.length) throw new Error("구간 내 체결 가능일이 없습니다");

  let shares = 0, cash = 0, totalInvested = 0;
  const purchases = [];
  const cashflows = [];
  const bRate = buyCostRate(costs);

  for (const i of execIdx) {
    const px = data.adj_close[i];
    totalInvested += amountPerPeriod;
    cashflows.push({ date: new Date(data.dates[i]), amount: -amountPerPeriod });
    const grossAvail = amountPerPeriod + cash;
    const net = grossAvail * (1 - bRate);
    let qty;
    if (allowFractional) { qty = net / px; cash = 0; }
    else {
      qty = Math.floor(net / px);
      cash = qty > 0 ? grossAvail - (qty * px) / (1 - bRate) : grossAvail;
    }
    shares += qty;
    purchases.push({ date: data.dates[i], price: px, qty, cashAfter: cash });
  }

  let endIdx = nextTradingIdx(data.dates, end);
  if (endIdx < 0) endIdx = data.dates.length - 1;
  const i0 = execIdx[0];
  const dates = data.dates.slice(i0, endIdx + 1);

  const investedCurve = [], valueCurve = [];
  let cumInv = 0, cumShares = 0, cumCash = 0, pi = 0;
  for (let k = i0; k <= endIdx; k++) {
    while (pi < purchases.length && purchases[pi].date <= data.dates[k]) {
      cumInv += amountPerPeriod;
      cumShares += purchases[pi].qty;
      cumCash = purchases[pi].cashAfter;
      pi++;
    }
    investedCurve.push(cumInv);
    valueCurve.push(cumShares * data.adj_close[k] + cumCash);
  }

  const finalPrice = data.adj_close[endIdx];
  const finalValue = shares * finalPrice * (1 - sellCostRate(costs)) + cash;

  let xirrV;
  if (finalValue <= 0) xirrV = -1;
  else if (data.dates[endIdx] === data.dates[i0]) xirrV = finalValue / totalInvested - 1;
  else {
    cashflows.push({ date: new Date(data.dates[endIdx]), amount: finalValue });
    xirrV = xirr(cashflows);
  }

  const totalQty = purchases.reduce((s, p) => s + p.qty, 0);
  const avgPrice = totalQty > 0 ? purchases.reduce((s, p) => s + p.price * p.qty, 0) / totalQty : 0;

  const lsShares = totalInvested * (1 - bRate) / purchases[0].price;
  const lumpSumFinal = lsShares * finalPrice * (1 - sellCostRate(costs));

  return {
    totalInvested, finalValue, xirr: xirrV,
    avgBuyPrice: avgPrice, finalPrice,
    nPurchases: purchases.length, shares, purchases,
    dates, investedCurve, valueCurve,
    lumpSumFinalValue: lumpSumFinal,
    lumpSumReturn: lumpSumFinal / totalInvested - 1,
  };
}

/* ---------- Phase 3: 진입 시점 분포 ---------- */

function rollingReturns(adjClose, holdingDays) {
  const n = adjClose.length;
  if (holdingDays <= 0 || holdingDays >= n) return [];
  const out = new Array(n - holdingDays);
  for (let i = 0; i < n - holdingDays; i++) {
    out[i] = adjClose[i + holdingDays] / adjClose[i] - 1;
  }
  return out;
}

function analyzeDistribution(adjClose, holdingDays) {
  const rets = rollingReturns(adjClose, holdingDays);
  if (!rets.length) throw new Error("보유기간이 데이터 길이보다 깁니다");
  const sorted = [...rets].sort((a, b) => a - b);
  return {
    holdingDays, nWindows: rets.length, returns: rets,
    mean: mean(rets), median: percentile(sorted, 0.5),
    std: std(rets),
    lossProbability: rets.filter(r => r < 0).length / rets.length,
    worst5pct: percentile(sorted, 0.05),
    best5pct: percentile(sorted, 0.95),
  };
}

function lossProbabilityCurve(adjClose, monthsRange) {
  monthsRange = monthsRange || [1, 3, 6, 12, 24, 36, 60, 84, 120];
  const out = [];
  for (const m of monthsRange) {
    const days = m * TRADING_DAYS_PER_MONTH;
    if (days >= adjClose.length) break;
    const rets = rollingReturns(adjClose, days);
    out.push({ months: m, lossProb: rets.filter(r => r < 0).length / rets.length, n: rets.length });
  }
  return out;
}

/* ---------- Phase 3: 레버리지 시뮬 ---------- */

/** 일간 리밸런싱 레버리지 ETF 누적 경로 (1.0 시작). */
function simulateLeveraged(rets, leverage, expenseRatio = 0.0064, financingRate = 0.035) {
  const dailyCost = (expenseRatio + financingRate * (leverage - 1)) / TRADING_DAYS_PER_YEAR;
  const path = new Array(rets.length);
  let v = 1;
  for (let i = 0; i < rets.length; i++) {
    const r = Math.max(rets[i] * leverage - dailyCost, -1);
    v *= 1 + r;
    path[i] = v;
  }
  return path;
}

function analyzeLeverage(rets, leverage, expenseRatio, financingRate) {
  const basePath = [];
  let v = 1;
  for (const r of rets) { v *= 1 + r; basePath.push(v); }
  const levPath = simulateLeveraged(rets, leverage, expenseRatio, financingRate);
  const baseReturn = basePath[basePath.length - 1] - 1;
  const levReturn = levPath[levPath.length - 1] - 1;
  const naiveReturn = baseReturn * leverage;
  const naivePath = basePath.map(b => 1 + (b - 1) * leverage);
  return { leverage, basePath, levPath, naivePath, baseReturn, levReturn, naiveReturn, decay: naiveReturn - levReturn };
}

/** 현재 손실률에서 본전 회복에 필요한 상승률. 0.5 → 1.0 (+100%) */
function breakevenRequiredGain(currentLoss) {
  if (currentLoss <= 0) return 0;
  if (currentLoss >= 1) return Infinity;
  return currentLoss / (1 - currentLoss);
}
