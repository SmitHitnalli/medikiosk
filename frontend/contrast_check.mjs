// Guards Phase 5 item 3 (default WCAG AA contrast): fails if any of these
// secondary-text colors regress below the 4.5:1 threshold for normal text.
// Run: node contrast_check.mjs
import assert from "node:assert/strict";

function hex2rgb(h) {
  h = h.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

function luminance([r, g, b]) {
  const f = (v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrastRatio(fgHex, bgHex) {
  const l1 = luminance(hex2rgb(fgHex));
  const l2 = luminance(hex2rgb(bgHex));
  const [lighter, darker] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

// Secondary-text colors used in index.css against the light backgrounds they
// actually render on, after darkening them to meet WCAG AA in Phase 5.
const PAIRS = [
  ["#607974", "#fffdf8"], // .subtitle, .staff-pin-copy, .trust-metric-note
  ["#6a7772", "#fffdf8"], // .muted-value, .trust-flag-time
  ["#5e706b", "#e8f3f0"], // .dashboard-footnote
  ["#647873", "#fffdf8"], // .detail-item dt / .ocr-fields dt
  ["#677773", "#fffdf8"], // .disclaimer
  ["#57776e", "#effaf3"], // .completion-card p
];

for (const [fg, bg] of PAIRS) {
  const ratio = contrastRatio(fg, bg);
  assert.ok(ratio >= 4.5, `${fg} on ${bg} is only ${ratio.toFixed(2)}:1, below WCAG AA 4.5:1`);
}
console.log(`contrast_check: ${PAIRS.length}/${PAIRS.length} pairs pass WCAG AA (4.5:1)`);
