/**
 * 지표추적자 — 앱 진입점
 *
 * 의존성 없는 순수 ES 모듈. 데이터는 ./data/indicators.json 에서 읽는다.
 */

const DATA_URL = './data/indicators.json';
const KEY_PINS = 'jp.pins';
const KEY_THEME = 'jp.theme';

const state = {
  indicators: [],
  meta: {},
  pins: loadPins(),
  query: '',
  category: '전체',
  view: 'dashboard',
};

const $ = (sel) => document.querySelector(sel);

/* -------------------------------------------------------------------------
   저장소
   ------------------------------------------------------------------------- */

function loadPins() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY_PINS) || '[]');
    return new Set(Array.isArray(raw) ? raw : []);
  } catch (_) {
    return new Set();
  }
}

function savePins() {
  try {
    localStorage.setItem(KEY_PINS, JSON.stringify([...state.pins]));
  } catch (_) {
    /* 시크릿 모드 등에서 저장이 막혀도 앱은 계속 동작한다 */
  }
}

/* -------------------------------------------------------------------------
   포맷
   ------------------------------------------------------------------------- */

function fmtNumber(value, decimals = 2) {
  return new Intl.NumberFormat('ko-KR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

function fmtSigned(value, decimals = 2) {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return sign + fmtNumber(Math.abs(value), decimals);
}

function fmtDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${y}. ${Number(m)}. ${Number(d)}.`;
}

function trendOf(value) {
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return 'flat';
}

const TREND_GLYPH = { up: '▲', down: '▼', flat: '–' };

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/* -------------------------------------------------------------------------
   스파크라인 (외부 차트 라이브러리 없이 SVG 직접 생성)
   ------------------------------------------------------------------------- */

function sparkline(values, trend, { w = 100, h = 40, pad = 3 } = {}) {
  if (!values.length) return '';

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const n = values.length;

  const x = (i) => (n === 1 ? w / 2 : (i / (n - 1)) * w);
  const y = (v) => h - pad - ((v - min) / span) * (h - pad * 2);

  const line = values
    .map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(2)} ${y(v).toFixed(2)}`)
    .join(' ');
  const area = `${line} L${w} ${h} L0 ${h} Z`;

  return `
    <svg class="spark spark--${trend}" viewBox="0 0 ${w} ${h}"
         preserveAspectRatio="none" role="img" aria-hidden="true" focusable="false">
      <path d="${area}" fill="currentColor" fill-opacity="0.1" />
      <path d="${line}" fill="none" stroke="currentColor" stroke-width="1.6"
            stroke-linecap="round" stroke-linejoin="round"
            vector-effect="non-scaling-stroke" />
    </svg>`;
}

/* -------------------------------------------------------------------------
   렌더링
   ------------------------------------------------------------------------- */

function cardHtml(ind) {
  const trend = trendOf(ind.changePct);
  const pinned = state.pins.has(ind.id);
  const values = ind.history.map((p) => p.v);

  return `
    <article class="card">
      <button class="card__main" type="button" data-open="${ind.id}">
        <span class="card__head">
          <span>
            <span class="card__name">${escapeHtml(ind.name)}</span>
            <span class="card__cat">${escapeHtml(ind.category)}</span>
          </span>
        </span>
        <span class="card__value">
          ${fmtNumber(ind.value, ind.decimals)}<span class="card__unit">${escapeHtml(ind.unit)}</span>
        </span>
        <span class="delta delta--${trend}">
          ${TREND_GLYPH[trend]} ${fmtSigned(ind.change, ind.decimals)}
          (${fmtSigned(ind.changePct, 2)}%)
        </span>
        ${sparkline(values, trend)}
      </button>
      <button class="pin" type="button" data-pin="${ind.id}"
              aria-pressed="${pinned}"
              aria-label="${escapeHtml(ind.name)} 즐겨찾기 ${pinned ? '해제' : '추가'}">★</button>
    </article>`;
}

function renderGrid(el, list, emptyMessage) {
  if (!list.length) {
    el.innerHTML = `<p class="empty">${escapeHtml(emptyMessage)}</p>`;
    return;
  }
  el.innerHTML = list.map(cardHtml).join('');
}

function renderDashboard() {
  const { indicators } = state;
  const ups = indicators.filter((i) => i.changePct > 0).length;
  const downs = indicators.filter((i) => i.changePct < 0).length;

  $('#statRow').innerHTML = `
    <div class="stat">
      <div class="stat__value">${indicators.length}</div>
      <div class="stat__label">추적 지표</div>
    </div>
    <div class="stat">
      <div class="stat__value delta--up">${ups}</div>
      <div class="stat__label">상승</div>
    </div>
    <div class="stat">
      <div class="stat__value delta--down">${downs}</div>
      <div class="stat__label">하락</div>
    </div>`;

  const pinned = indicators.filter((i) => state.pins.has(i.id));
  $('#pinnedCount').textContent = pinned.length ? `${pinned.length}개` : '';
  renderGrid($('#pinnedGrid'), pinned, '카드의 ★ 를 눌러 자주 보는 지표를 고정하세요.');

  const movers = [...indicators]
    .sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct))
    .slice(0, 6);
  renderGrid($('#moversGrid'), movers, '표시할 지표가 없습니다.');
}

function renderChips() {
  const categories = ['전체', ...new Set(state.indicators.map((i) => i.category))];
  $('#chipBar').innerHTML = categories
    .map(
      (c) => `<button class="chip" type="button" data-chip="${escapeHtml(c)}"
                aria-pressed="${c === state.category}">${escapeHtml(c)}</button>`
    )
    .join('');
}

function renderList() {
  const q = state.query.trim().toLowerCase();
  const list = state.indicators.filter((i) => {
    const byCategory = state.category === '전체' || i.category === state.category;
    const byQuery =
      !q ||
      i.name.toLowerCase().includes(q) ||
      i.id.includes(q) ||
      i.category.toLowerCase().includes(q);
    return byCategory && byQuery;
  });

  $('#listGrid').innerHTML = list.map(cardHtml).join('');
  $('#emptyState').hidden = list.length > 0;
}

function renderSettings() {
  $('#metaUpdatedAt').textContent = fmtDate(state.meta.updatedAt);
  $('#metaSource').textContent = state.meta.source || '—';
  $('#metaCount').textContent = `${state.indicators.length}개`;
  syncThemeButtons();
}

function renderAll() {
  renderDashboard();
  renderList();
  renderSettings();
}

/* -------------------------------------------------------------------------
   상세 시트
   ------------------------------------------------------------------------- */

function openDetail(id) {
  const ind = state.indicators.find((i) => i.id === id);
  if (!ind) return;

  const values = ind.history.map((p) => p.v);
  const trend = trendOf(ind.changePct);
  const first = values[0];
  const periodPct = first ? ((ind.value - first) / first) * 100 : 0;

  $('#detailBody').innerHTML = `
    <div class="sheet__grip"></div>
    <div class="sheet__head">
      <div>
        <h2 class="sheet__title">${escapeHtml(ind.name)}</h2>
        <span class="card__cat">${escapeHtml(ind.category)}</span>
      </div>
      <button class="pin" type="button" data-pin="${ind.id}"
              aria-pressed="${state.pins.has(ind.id)}"
              aria-label="즐겨찾기 전환">★</button>
    </div>
    <div class="sheet__value">
      ${fmtNumber(ind.value, ind.decimals)}<span class="card__unit">${escapeHtml(ind.unit)}</span>
    </div>
    <div class="delta delta--${trend}">
      ${TREND_GLYPH[trend]} ${fmtSigned(ind.change, ind.decimals)} (${fmtSigned(ind.changePct, 2)}%)
    </div>
    ${sparkline(values, trend, { h: 40 })}
    <dl class="statlist">
      <div><dt>기간 최고</dt><dd>${fmtNumber(Math.max(...values), ind.decimals)}</dd></div>
      <div><dt>기간 최저</dt><dd>${fmtNumber(Math.min(...values), ind.decimals)}</dd></div>
      <div><dt>${values.length}일 변화</dt>
           <dd class="delta--${trendOf(periodPct)}">${fmtSigned(periodPct, 2)}%</dd></div>
      <div><dt>기준일</dt><dd>${fmtDate(ind.history.at(-1)?.d)}</dd></div>
    </dl>
    <button class="sheet__close" type="button" data-close>닫기</button>`;

  $('#detailDialog').showModal();
}

/* -------------------------------------------------------------------------
   테마
   ------------------------------------------------------------------------- */

function currentTheme() {
  try {
    return localStorage.getItem(KEY_THEME) || 'system';
  } catch (_) {
    return 'system';
  }
}

function applyTheme(value) {
  if (value === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = value;

  try {
    if (value === 'system') localStorage.removeItem(KEY_THEME);
    else localStorage.setItem(KEY_THEME, value);
  } catch (_) {}

  syncThemeButtons();
}

function syncThemeButtons() {
  const value = currentTheme();
  document
    .querySelectorAll('#themeSegmented button')
    .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themeValue === value)));
}

/* -------------------------------------------------------------------------
   화면 전환
   ------------------------------------------------------------------------- */

function switchView(name) {
  state.view = name;

  document.querySelectorAll('.tab').forEach((tab) => {
    const active = tab.dataset.view === name;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
  });

  document.querySelectorAll('.view').forEach((view) => {
    view.hidden = view.id !== `view-${name}`;
  });

  window.scrollTo({ top: 0 });
}

/* -------------------------------------------------------------------------
   토스트
   ------------------------------------------------------------------------- */

let toastTimer;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 1800);
}

/* -------------------------------------------------------------------------
   이벤트
   ------------------------------------------------------------------------- */

function togglePin(id) {
  const ind = state.indicators.find((i) => i.id === id);
  if (state.pins.has(id)) {
    state.pins.delete(id);
    toast(`${ind?.name ?? '지표'} 즐겨찾기 해제`);
  } else {
    state.pins.add(id);
    toast(`${ind?.name ?? '지표'} 즐겨찾기 추가`);
  }
  savePins();
  renderAll();

  // 열려 있는 상세 시트의 ★ 상태도 맞춰 준다.
  const sheetPin = $('#detailBody .pin');
  if (sheetPin && sheetPin.dataset.pin === id) {
    sheetPin.setAttribute('aria-pressed', String(state.pins.has(id)));
  }
}

function bindEvents() {
  document.addEventListener('click', (e) => {
    const pin = e.target.closest('[data-pin]');
    if (pin) {
      togglePin(pin.dataset.pin);
      return;
    }

    const open = e.target.closest('[data-open]');
    if (open) {
      openDetail(open.dataset.open);
      return;
    }

    const chip = e.target.closest('[data-chip]');
    if (chip) {
      state.category = chip.dataset.chip;
      renderChips();
      renderList();
      return;
    }

    const tab = e.target.closest('.tab');
    if (tab) {
      switchView(tab.dataset.view);
      return;
    }

    if (e.target.closest('[data-close]')) $('#detailDialog').close();

    const themeBtn = e.target.closest('[data-theme-value]');
    if (themeBtn) applyTheme(themeBtn.dataset.themeValue);
  });

  // 배경(백드롭)을 누르면 상세 시트를 닫는다.
  $('#detailDialog').addEventListener('click', (e) => {
    if (e.target.id === 'detailDialog') e.target.close();
  });

  $('#searchInput').addEventListener('input', (e) => {
    state.query = e.target.value;
    renderList();
  });

  $('#themeToggle').addEventListener('click', () => {
    const order = ['system', 'light', 'dark'];
    const next = order[(order.indexOf(currentTheme()) + 1) % order.length];
    applyTheme(next);
    toast({ system: '시스템 테마', light: '라이트 테마', dark: '다크 테마' }[next]);
  });

  $('#resetPins').addEventListener('click', () => {
    state.pins.clear();
    savePins();
    renderAll();
    toast('즐겨찾기를 초기화했습니다.');
  });

  // 탭바 좌우 방향키 이동
  $('.tabbar').addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const tabs = [...document.querySelectorAll('.tab')];
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    next.focus();
    switchView(next.dataset.view);
    e.preventDefault();
  });
}

/* -------------------------------------------------------------------------
   초기화
   ------------------------------------------------------------------------- */

function showLoading() {
  const skeletons = '<div class="skeleton"></div>'.repeat(3);
  $('#moversGrid').innerHTML = skeletons;
}

function showError(message) {
  $('#statRow').innerHTML = '';
  $('#pinnedGrid').innerHTML = '';
  $('#moversGrid').innerHTML = `<p class="empty">${escapeHtml(message)}</p>`;
}

async function init() {
  bindEvents();
  syncThemeButtons();
  showLoading();

  try {
    const res = await fetch(DATA_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const doc = await res.json();
    state.indicators = doc.indicators ?? [];
    state.meta = { updatedAt: doc.updatedAt, source: doc.source };

    renderChips();
    renderAll();
  } catch (err) {
    console.error(err);
    showError('지표 데이터를 불러오지 못했습니다. 로컬에서 열었다면 정적 서버로 실행해 주세요.');
  }
}

init();
