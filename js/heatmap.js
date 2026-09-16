/**
 * 코스피/코스닥 히트맵.
 *
 * 업종을 1차 트리맵으로 나눈 뒤, 각 업종 안에서 종목을 2차 트리맵으로 배치한다.
 * 타일 크기는 시가총액, 색은 등락률.
 */

import { squarify, inset } from './treemap.js';

/** 색이 가장 짙어지는 등락률(%) */
export const COLOR_CAP = 3;

const NEUTRAL = [91, 100, 114];
const UP = [212, 52, 42]; // 국내 관례: 상승 빨강
const DOWN = [31, 99, 207]; // 하락 파랑

const SECTOR_HEAD = 15;
const SECTOR_GAP = 1.5;
const TILE_GAP = 1;

/** 등락률 → 타일 배경색 */
export function heatColor(pct) {
  if (!pct) return `rgb(${NEUTRAL.join(' ')})`;

  // 작은 변동도 눈에 띄도록 완만하게 끌어올린다.
  const t = Math.pow(Math.min(Math.abs(pct) / COLOR_CAP, 1), 0.65);
  const target = pct > 0 ? UP : DOWN;
  const rgb = NEUTRAL.map((n, i) => Math.round(n + (target[i] - n) * t));
  return `rgb(${rgb.join(' ')})`;
}

const nf = new Intl.NumberFormat('ko-KR');
const fmtPct = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}%`;

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

const px = (v) => `${Math.round(v * 10) / 10}px`;

const FONT_MIN = 9;
const FONT_MAX = 24;

const widthCache = new Map();
let measureCtx = null;

/**
 * 이름을 한 줄에 담는 데 필요한 폭(글자 크기 1 기준).
 *
 * 글자 폭은 크기에 비례하므로 100px 로 한 번 재서 나눠 쓴다. 한글/영문/숫자가
 * 섞이면 어림짐작이 잘 빗나가 라벨이 어중간하게 잘리므로 실제로 측정한다.
 */
function nameWidth(name) {
  const cached = widthCache.get(name);
  if (cached !== undefined) return cached;

  let width;
  try {
    if (!measureCtx) {
      measureCtx = document.createElement('canvas').getContext('2d');
      measureCtx.font = `600 100px ${getComputedStyle(document.body).fontFamily}`;
    }
    width = measureCtx.measureText(name).width / 100;
  } catch (_) {
    // canvas 를 못 쓰면 한글 1em, 그 외 0.62em 으로 어림잡는다.
    const wide = (name.match(/[가-힣]/g) || []).length;
    width = wide + (name.length - wide) * 0.62;
  }

  width = width || 1;
  widthCache.set(name, width);
  return width;
}

/**
 * 시가총액이 클수록 글자도 크게. 시총 1위 종목이 FONT_MAX 가 된다.
 *
 * 타일 '넓이'가 시총에 비례하므로 한 변의 길이는 sqrt(시총)에 비례한다.
 * 글자 크기도 길이 차원이라 sqrt 를 기준으로 삼고, 그대로 쓰면 중소형주가
 * 전부 최소 크기에 몰리므로 지수를 한 번 더 완만하게 준다.
 */
function capFontSize(cap, maxCap) {
  const share = maxCap > 0 ? Math.min(Math.max(cap, 0) / maxCap, 1) : 0;
  return FONT_MIN + (FONT_MAX - FONT_MIN) * Math.pow(Math.sqrt(share), 0.6);
}

/**
 * 시총으로 정한 글자 크기를 타일 안에 들어가도록 줄인다.
 *
 * 이름 전체가 들어가야 라벨을 띄우면 '한국타이어앤테크놀로지' 같은 긴 이름은
 * 큰 타일에서도 사라진다. 앞 4글자 정도만 보이면 알아볼 수 있으므로 그 선까지만
 * 요구하고 나머지는 CSS 말줄임에 맡긴다. 너무 작으면 null(라벨 숨김).
 */
function labelSize(rect, name, target) {
  if (rect.w < 30 || rect.h < 20) return null;

  const full = nameWidth(name);
  const em = Math.min(full, 4.2);
  let size = Math.min(target, (rect.w - 6) / em, rect.h * 0.34);

  // 조금만 줄이면 이름이 통째로 들어가는 경우에는 줄여서 다 보여준다.
  // (많이 줄여야 한다면 크기 위계가 무너지므로 그냥 말줄임에 맡긴다)
  const fullSize = (rect.w - 6) / full;
  if (fullSize < size && fullSize >= size * 0.7) size = fullSize;

  return size >= 8 ? size : null;
}

export function createHeatmap({ container, onSelectStock }) {
  let market = null;

  function render() {
    if (!market) return;

    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w <= 0 || h <= 0) return;

    const sectors = market.sectors;
    const rects = squarify(sectors.map((s) => s.cap), { x: 0, y: 0, w, h });
    const parts = [];

    // 글자 크기는 시장 안에서의 상대 시총으로 정한다.
    const maxCap = Math.max(...sectors.flatMap((s) => s.stocks.map((t) => t.cap)), 0);

    sectors.forEach((sector, si) => {
      const box = inset(rects[si], {
        top: SECTOR_GAP, right: SECTOR_GAP, bottom: SECTOR_GAP, left: SECTOR_GAP,
      });
      if (box.w <= 0 || box.h <= 0) return;

      const showHead = box.h >= 40 && box.w >= 50;
      const body = showHead ? inset(box, { top: SECTOR_HEAD }) : box;

      parts.push(
        `<div class="hm-sector" style="left:${px(box.x)};top:${px(box.y)};` +
          `width:${px(box.w)};height:${px(box.h)}">` +
          // 폭이 좁으면 업종명이 통째로 잘려 등락률만 남는다. 그럴 땐 등락률을 뺀다.
          (showHead
            ? `<div class="hm-sector__head"><span>${escapeHtml(sector.name)}</span>` +
              (box.w >= 104
                ? `<span class="hm-sector__pct">${fmtPct(sector.changePct)}</span>`
                : '') +
              '</div>'
            : '') +
          '</div>'
      );

      const tiles = squarify(sector.stocks.map((s) => s.cap), body);

      sector.stocks.forEach((stock, ti) => {
        const t = inset(tiles[ti], {
          top: TILE_GAP, right: TILE_GAP, bottom: TILE_GAP, left: TILE_GAP,
        });
        if (t.w <= 0 || t.h <= 0) return;

        const size = labelSize(t, stock.name, capFontSize(stock.cap, maxCap));
        // '−12.34%' 가 글자 중간에서 잘리지 않을 만큼 폭이 남을 때만 등락률을 넣는다.
        const pctSize = Math.max(8, size * 0.82);
        const showPct = size && t.h >= size * 2.6 + 6 && t.w >= pctSize * 5.2 + 10;
        const label = size
          ? `<span class="hm-tile__name" style="font-size:${px(size)}">` +
            `${escapeHtml(stock.name)}</span>` +
            (showPct
              ? `<span class="hm-tile__pct" style="font-size:${px(pctSize)}">` +
                `${fmtPct(stock.changePct)}</span>`
              : '')
          : '';

        const aria =
          `${stock.name} ${nf.format(stock.price)}원, ` +
          `${fmtPct(stock.changePct).replace('−', '마이너스 ')}`;

        parts.push(
          `<button type="button" class="hm-tile" data-stock="${stock.code}"` +
            ` style="left:${px(t.x)};top:${px(t.y)};width:${px(t.w)};height:${px(t.h)};` +
            `background:${heatColor(stock.changePct)}"` +
            ` aria-label="${escapeHtml(aria)}">${label}</button>`
        );
      });
    });

    container.innerHTML = parts.join('');
  }

  function setMarket(next) {
    market = next;
    render();
  }

  // 회전·창 크기 변경 시 다시 그린다.
  if (typeof ResizeObserver !== 'undefined') {
    let frame = 0;
    new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(render);
    }).observe(container);
  } else {
    window.addEventListener('resize', render);
  }

  container.addEventListener('click', (e) => {
    const tile = e.target.closest('[data-stock]');
    if (!tile || !market) return;

    const code = tile.dataset.stock;
    for (const sector of market.sectors) {
      const stock = sector.stocks.find((s) => s.code === code);
      if (stock) {
        onSelectStock?.(stock, sector, market);
        return;
      }
    }
  });

  return { setMarket, render };
}
