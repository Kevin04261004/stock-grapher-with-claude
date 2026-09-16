/**
 * Squarified treemap 레이아웃.
 *
 * Bruls, Huizing, van Wijk (2000) 의 squarify 알고리즘. 타일이 정사각형에
 * 가까워지도록 배치해 좁은 화면에서도 이름과 등락률을 읽을 수 있게 한다.
 */

/**
 * @param {number[]} values 각 항목의 크기(음수는 0으로 취급)
 * @param {{x:number,y:number,w:number,h:number}} rect 채울 영역
 * @returns {{x:number,y:number,w:number,h:number}[]} values 와 같은 순서의 사각형
 */
export function squarify(values, rect) {
  const out = new Array(values.length);
  const empty = { x: rect.x, y: rect.y, w: 0, h: 0 };

  const total = values.reduce((sum, v) => sum + Math.max(0, v), 0);
  if (!(total > 0) || rect.w <= 0 || rect.h <= 0) {
    return out.fill(empty);
  }

  // 값을 넓이 단위로 환산해 두면 이후 계산이 전부 넓이 기준으로 통일된다.
  const scale = (rect.w * rect.h) / total;
  const items = values
    .map((v, i) => ({ i, area: Math.max(0, v) * scale }))
    .filter((it) => it.area > 0)
    .sort((a, b) => b.area - a.area);

  values.forEach((v, i) => {
    if (!(v > 0)) out[i] = { ...empty };
  });

  let { x, y, w, h } = rect;
  let row = [];
  let rowArea = 0;

  /** 행에 candidate 를 넣었을 때 가장 나쁜(가장 길쭉한) 타일의 종횡비 */
  const worstRatio = (candidate) => {
    const side = Math.min(w, h);
    if (side <= 0) return Infinity;

    let area = rowArea;
    let max = row.length ? row[0].area : 0; // 내림차순 정렬이라 첫 항목이 최대
    let min = row.length ? row[row.length - 1].area : Infinity;
    if (candidate) {
      area += candidate.area;
      max = Math.max(max, candidate.area);
      min = Math.min(min, candidate.area);
    }
    if (area <= 0 || min <= 0) return Infinity;

    const side2 = side * side;
    const area2 = area * area;
    return Math.max((side2 * max) / area2, area2 / (side2 * min));
  };

  /** 현재 행을 짧은 변에 붙여 배치하고 남은 영역을 줄인다. */
  const flushRow = () => {
    if (!row.length) return;

    if (w >= h) {
      const colW = h > 0 ? rowArea / h : 0;
      let cy = y;
      for (const it of row) {
        const ih = colW > 0 ? it.area / colW : 0;
        out[it.i] = { x, y: cy, w: colW, h: ih };
        cy += ih;
      }
      x += colW;
      w -= colW;
    } else {
      const rowH = w > 0 ? rowArea / w : 0;
      let cx = x;
      for (const it of row) {
        const iw = rowH > 0 ? it.area / rowH : 0;
        out[it.i] = { x: cx, y, w: iw, h: rowH };
        cx += iw;
      }
      y += rowH;
      h -= rowH;
    }

    row = [];
    rowArea = 0;
  };

  for (const it of items) {
    if (row.length && worstRatio(it) > worstRatio(null)) flushRow();
    row.push(it);
    rowArea += it.area;
  }
  flushRow();

  return out;
}

/**
 * 사각형을 안쪽으로 줄인다. 남는 크기가 없으면 0 으로 눌러 준다.
 */
export function inset(rect, { top = 0, right = 0, bottom = 0, left = 0 }) {
  return {
    x: rect.x + left,
    y: rect.y + top,
    w: Math.max(0, rect.w - left - right),
    h: Math.max(0, rect.h - top - bottom),
  };
}
