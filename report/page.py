"""The scroll page: one self-contained index.html per run.

render_page(data) returns a single HTML
string with inline CSS, inline JS and the data embedded as JSON. It makes no
network requests and loads no fonts or libraries. Every number on the page is
derived from the embedded data.
"""
import html
import json

NO_SNAPSHOTS_LINE = "No readable snapshots."
NO_WINDOW_LINE = "no snapshots in this window"
FLEET_NO_BEFORE_LINE = "No snapshot before this event was recorded."
NO_EVENTS_LINE = "No restart or release was seen in the recorded span."

_CSS = r"""
:root{
  --ink:#f2f1ee; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835;
  --accent:#ff6f61;
  --m1:#3987e5; --m2:#d95926; --m3:#199e70; --m4:#c98500; --m5:#d55181; --m6:#8f7ae0; --other:#008300;
  --neutral:#8a8983;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --pad:clamp(1.25rem,5vw,4rem);
}
*{box-sizing:border-box}
html{color-scheme:dark;-webkit-text-size-adjust:100%}
body{margin:0;background:#09090a;color:var(--ink);font:400 1rem/1.55 var(--sans);
  overflow-x:clip;transition:background-color .9s ease}
h1,h2,p,ul,figure{margin:0}
p,li,h1,h2,summary{overflow-wrap:anywhere}
.bar{position:fixed;left:0;top:0;height:2px;width:100%;background:var(--ink2);opacity:.45;
  transform-origin:0 50%;transform:scaleX(0);z-index:20;pointer-events:none}
.world{position:relative;min-height:100vh;min-height:100svh;display:flex;align-items:center;
  padding:clamp(4.5rem,11vh,7rem) var(--pad)}
.cv{position:absolute;left:0;top:0;width:100%;height:100%;display:block}
.inner{position:relative;z-index:1;width:100%;max-width:1240px;margin:0 auto}
.eyebrow{font:500 .75rem/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;
  color:var(--muted);margin-bottom:1.25rem}
h2{font-size:clamp(1.6rem,4.2vw,3.1rem);line-height:1.1;font-weight:600;letter-spacing:-.02em}
.sub{color:var(--ink2);font-size:clamp(1rem,1.5vw,1.125rem);margin-top:1rem;max-width:34rem}
.small{color:var(--muted);font-size:.875rem;margin-top:.75rem;max-width:34rem}
.mono{font-family:var(--mono)}

/* reveal on scroll */
.js .rv{opacity:0;transform:translateY(16px);transition:opacity .8s ease,transform .8s ease}
.js .rv.on{opacity:1;transform:none}

/* 1 opening */
#s-open .inner{padding-bottom:3rem}
.name{font-size:clamp(1.5rem,4vw,2.25rem);font-weight:600;letter-spacing:-.02em}
.lede{color:var(--ink2);font-size:clamp(1.05rem,2vw,1.4rem);line-height:1.4;margin-top:.75rem;max-width:34rem}
.hero{font-size:clamp(5.5rem,24vw,16rem);line-height:.86;font-weight:600;letter-spacing:-.045em;
  color:var(--accent);margin-top:clamp(2rem,7vh,4.5rem)}
.hero-label{font-size:clamp(1.05rem,2vw,1.4rem);margin-top:1.25rem;color:var(--ink)}
.meta{color:var(--muted);font-size:.875rem;margin-top:.5rem;max-width:40rem}
.cue{position:absolute;left:50%;bottom:1.75rem;transform:translateX(-50%);z-index:2;display:flex;
  flex-direction:column;align-items:center;gap:.6rem;color:var(--muted);font-size:.68rem;
  letter-spacing:.24em;text-transform:uppercase}
.cue i{display:block;width:1px;height:40px;background:var(--axis);position:relative;overflow:hidden}
.cue i::after{content:"";position:absolute;left:0;top:-45%;width:1px;height:45%;background:var(--ink2);
  animation:drip 2.4s ease-in-out infinite}
@keyframes drip{0%{top:-45%}100%{top:105%}}

/* 2 fleet and 3 event copy */
.copy{position:relative;z-index:1;width:100%;max-width:30rem}
.legend{list-style:none;padding:0;margin-top:1.5rem;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(7rem,1fr));gap:.5rem 1.25rem}
.legend li{display:flex;align-items:center;gap:.6rem;color:var(--ink2);font-size:.9rem}
.legend i{flex:none;width:10px;height:10px;border-radius:50%}
.legend b{font:500 .9rem var(--mono);color:var(--ink);margin-left:auto}
.tall{position:relative;height:400vh}
.sticky{position:sticky;top:0;height:100vh;height:100svh;overflow:hidden;display:flex;
  align-items:center;padding:clamp(4rem,9vh,6rem) var(--pad)}
.clock{font:500 clamp(2.4rem,7vw,5.5rem)/1 var(--mono);letter-spacing:-.03em;
  margin-top:1.25rem;font-variant-numeric:tabular-nums}
.clock small{font-size:.28em;letter-spacing:.1em;color:var(--muted);margin-left:.4em}
.clockdate{color:var(--muted);font:.8rem var(--mono);margin-top:.5rem}
.counter{display:flex;align-items:baseline;gap:.75rem;margin-top:1rem}
.counter b{font:500 clamp(1.6rem,4vw,2.6rem)/1 var(--mono);font-variant-numeric:tabular-nums}
.counter span{color:var(--muted);font-size:.9rem}
.note{opacity:0;transform:translateY(8px);transition:opacity .6s ease,transform .6s ease;
  min-height:1.5em;margin-top:.5rem;color:var(--ink2);font-size:clamp(.95rem,1.6vw,1.2rem)}
.note.on{opacity:1;transform:none}
.note strong{font-weight:600;color:var(--ink)}
.hint{position:absolute;left:50%;bottom:1.5rem;transform:translateX(-50%);color:var(--muted);
  font-size:.7rem;letter-spacing:.2em;text-transform:uppercase;transition:opacity .5s ease;
  z-index:2;white-space:nowrap}
.hint.off{opacity:0}

/* 4 throughput and 6 now: line charts */
.chart{position:relative;height:clamp(240px,44vh,420px);margin-top:2rem}
.chart canvas{position:absolute;left:0;top:0;width:100%;height:100%;display:block;touch-action:pan-y}
.tip{position:absolute;z-index:3;pointer-events:none;background:#161617;
  border:1px solid rgba(255,255,255,.1);border-radius:6px;padding:.5rem .7rem;opacity:0;
  transition:opacity .12s ease;white-space:nowrap}
.tip.on{opacity:1}
.tip b{display:block;font:600 1.15rem/1.2 var(--mono);color:var(--ink)}
.tip span{display:block;color:var(--muted);font-size:.75rem;margin-top:.15rem}
details.tv{margin-top:1.25rem;color:var(--ink2);font-size:.875rem}
details.tv summary{cursor:pointer;color:var(--muted);width:max-content}
details.tv .box{max-height:18rem;overflow:auto;margin-top:.75rem;border:1px solid var(--grid)}
details.tv table{border-collapse:collapse;width:100%;font:.8rem var(--mono)}
details.tv th,details.tv td{padding:.3rem .75rem;text-align:right;border-bottom:1px solid var(--grid)}
details.tv th:first-child,details.tv td:first-child{text-align:left}
details.tv th{position:sticky;top:0;background:#111;color:var(--muted);font-weight:500}

/* 5 left behind */
#s-left .inner{pointer-events:none}
#s-left .copy{max-width:36rem}
.counts{margin-top:1.25rem;display:grid;gap:.4rem;color:var(--ink2)}
.counts strong{color:var(--ink);font-weight:600}

/* 6 now: bars */
.bars{margin-top:2.5rem;max-width:34rem}
.bars h3{font:500 .75rem/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;
  color:var(--muted);margin:0 0 1rem}
.row{display:grid;grid-template-columns:4.5rem 1fr auto;gap:.9rem;align-items:center;
  padding:.45rem 0;color:var(--ink2);font-size:.9rem}
.track{height:12px}
.fill{height:12px;background:var(--accent);border-radius:0 4px 4px 0;width:0;
  transition:width 1.1s cubic-bezier(.2,.7,.2,1)}
.row b{font:500 .9rem var(--mono);color:var(--ink);min-width:2ch;text-align:right}

/* 7 table */
#s-table{display:block;min-height:0}
.tablewrap{margin-top:2rem;overflow-x:auto}
table.ev{border-collapse:collapse;width:100%;font-size:.8rem}
table.ev th{color:var(--muted);font-weight:500;text-align:right;padding:.6rem .5rem;
  border-bottom:1px solid var(--axis);vertical-align:bottom}
table.ev td{padding:.75rem .5rem;text-align:right;border-bottom:1px solid var(--grid);
  font-variant-numeric:tabular-nums;white-space:nowrap}
table.ev th:nth-child(-n+3),table.ev td:nth-child(-n+3),table.ev th:last-child{text-align:left}
table.ev td.chips{text-align:left;white-space:normal;min-width:9rem}
.foot{padding:3rem 0 4rem;color:var(--muted);font-size:.8rem;width:calc(100% - 2 * var(--pad));max-width:1240px;margin:0 auto}
.none{font-size:clamp(1.2rem,2.6vw,1.8rem);color:var(--ink2);max-width:36rem;line-height:1.35}

:focus-visible{outline:2px solid var(--ink2);outline-offset:3px}

#s-left.world{align-items:flex-start}
@media (min-width:900px){
  #s-fleet .copy,#s-event .copy,#s-left .copy{max-width:min(28rem,40%)}
}
@media (max-width:899px){
  #s-fleet.world,.sticky{align-items:flex-start}
  #s-fleet.world{padding-top:4.5rem;padding-bottom:15rem}
  #s-left.world{padding-top:4.5rem;padding-bottom:17rem}
  .sticky{padding-top:4.25rem}
  .clock{margin-top:.75rem}
  .counter{margin-top:.6rem}
}
@media (max-width:1150px){
  table.ev thead{display:none}
  table.ev,table.ev tbody,table.ev tr,table.ev td{display:block;width:100%}
  table.ev tr{border-top:1px solid var(--axis);padding:1rem 0}
  table.ev td{display:flex;justify-content:space-between;gap:1rem;border:0;padding:.2rem 0;text-align:right;
    white-space:normal;overflow-wrap:anywhere}
  table.ev td::before{content:attr(data-label);color:var(--muted);text-align:left}
  table.ev td.chips{text-align:right;min-width:0}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
  .js .rv{opacity:1;transform:none}
  .tall{height:auto}
  .sticky{position:relative;height:auto;min-height:100vh;min-height:100svh}
  .note{opacity:1;transform:none}
  .fill{width:var(--w)!important}
  .hint{display:none}
}
"""

_JS = r"""
(function () {
'use strict';
var D = JSON.parse(document.getElementById('wilt-data').textContent);
var TL = D.timeline || [];
var EVS = D.events || [];
var EV = EVS.length ? EVS[0] : null;
var SN = D.stuck_now || { at: null, count: null, by_chip: {} };
var RM = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
var CS = getComputedStyle(document.documentElement);
function cv(n) { return CS.getPropertyValue(n).trim(); }
var INK = cv('--ink'), INK2 = cv('--ink2'), MUTED = cv('--muted'), GRID = cv('--grid'),
    AXIS = cv('--axis'), ACCENT = cv('--accent'), NEUTRAL = cv('--neutral');
var SANS = cv('--sans'), MONO = cv('--mono');
var CHIPS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'other'];
var CHIPCOL = { M1: cv('--m1'), M2: cv('--m2'), M3: cv('--m3'), M4: cv('--m4'), M5: cv('--m5'), M6: cv('--m6'), other: cv('--other') };
var NO_SNAPSHOTS = 'No readable snapshots.';
var FLEET_NO_BEFORE = 'No snapshot before this event was recorded.';
var TAU = Math.PI * 2, GA = 2.399963229728653;

function $(id) { return document.getElementById(id); }
function clamp(x, a, b) { return x < a ? a : (x > b ? b : x); }
function lerp(a, b, t) { return a + (b - a) * t; }
function eo(t) { t = clamp(t, 0, 1); return 1 - Math.pow(1 - t, 3); }
function ss(t) { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); }
function fmt(x, d) {
  if (x === null || x === undefined || isNaN(x)) return '-';
  return Number(x).toLocaleString('en-US', { maximumFractionDigits: d === undefined ? 1 : d });
}
function pad(n) { return n < 10 ? '0' + n : '' + n; }
function T(iso) { return Date.parse(iso); }
function hms(ms) { var d = new Date(ms); return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()) + ':' + pad(d.getUTCSeconds()); }
function hm(ms) { var d = new Date(ms); return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()); }
function ymd(ms) { var d = new Date(ms); return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()); }
function mdhm(ms) { var d = new Date(ms); return pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()) + ' ' + hm(ms); }
function chipKey(k) { return CHIPS.indexOf(k) >= 0 ? k : 'other'; }
function chipName(k) { return k === 'other' ? 'Other' : k; }
function setText(id, s) { var e = $(id); if (e && e.textContent !== s) e.textContent = s; }
function rng(seed) {
  var a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function evName(e) { return e.kind === 'release' ? 'release ' + e.label : e.label; }
function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function dot(c, x, y, r, col, ring, bg) {
  if (ring) { c.fillStyle = bg; c.beginPath(); c.arc(x, y, r + ring, 0, TAU); c.fill(); }
  c.fillStyle = col; c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
}

/* ---------- stage manager ---------- */
var stages = [];
var vh = window.innerHeight;
function makeStage(canvas, host, prog, draw, bg) {
  var s = { cv: canvas, ctx: canvas.getContext('2d'), host: host, prog: prog, draw: draw,
            bg: bg || '#09090a', w: 1, h: 1, dirty: true, hover: -1 };
  stages.push(s);
  return s;
}
function sizeStage(s) {
  var r = s.cv.getBoundingClientRect();
  var dpr = Math.min(window.devicePixelRatio || 1, 3);
  s.w = Math.max(1, Math.round(r.width));
  s.h = Math.max(1, Math.round(r.height));
  s.cv.width = Math.round(s.w * dpr);
  s.cv.height = Math.round(s.h * dpr);
  s.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (s.layout) s.layout(s);
  s.dirty = true;
}
function enterProg(start, span) {
  return function (r) { return clamp((vh - r.top - vh * start) / (vh * span), 0, 1); };
}
var raf = 0;
function schedule() { if (!raf) raf = requestAnimationFrame(tick); }
var worldSecs = [].slice.call(document.querySelectorAll('[data-bg]'));
var lastBg = '';
function updateWorld() {
  var mid = vh * 0.5, pick = null;
  for (var i = 0; i < worldSecs.length; i++) {
    var r = worldSecs[i].getBoundingClientRect();
    if (r.top <= mid && r.bottom > mid) { pick = worldSecs[i]; break; }
  }
  if (pick) {
    var b = pick.getAttribute('data-bg');
    if (b !== lastBg) { document.body.style.backgroundColor = b; lastBg = b; }
  }
  var bar = $('bar');
  if (bar) {
    var max = document.documentElement.scrollHeight - vh;
    bar.style.transform = 'scaleX(' + (max > 0 ? clamp(window.pageYOffset / max, 0, 1) : 0) + ')';
  }
}
function tick(now) {
  raf = 0;
  vh = window.innerHeight;
  var t = RM ? 0 : now / 1000;
  for (var i = 0; i < stages.length; i++) {
    var s = stages[i];
    var r = s.host.getBoundingClientRect();
    if (r.bottom < -60 || r.top > vh + 60) continue;
    if (RM && !s.dirty && s.hover === s.lastHover) continue;
    var p = RM ? 1 : s.prog(r);
    s.ctx.clearRect(0, 0, s.w, s.h);
    s.draw(s, p, t, r);
    s.dirty = false;
    s.lastHover = s.hover;
  }
  updateWorld();
  if (!RM && !document.hidden) schedule();
}
function resizeAll() {
  vh = window.innerHeight;
  for (var i = 0; i < stages.length; i++) sizeStage(stages[i]);
  schedule();
}
var rz = 0;
window.addEventListener('resize', function () {
  if (rz) cancelAnimationFrame(rz);
  rz = requestAnimationFrame(function () { rz = 0; resizeAll(); });
});
if (RM) window.addEventListener('scroll', schedule, { passive: true });
document.addEventListener('visibilitychange', schedule);

/* ---------- 1 opening ---------- */
(function () {
  var c = $('cv-open');
  if (!c) return;
  var dots = [];
  var s = makeStage(c, $('s-open'), function (r) { return clamp(-r.top / vh, 0, 1); }, function (s, p, t) {
    var g = s.ctx, fade = 1 - clamp(p * 1.3, 0, 1);
    g.fillStyle = INK2;
    for (var i = 0; i < dots.length; i++) {
      var d = dots[i];
      var x = d.x + Math.sin(t * d.sp + d.ph) * d.am;
      var y = d.y + Math.cos(t * d.sp * 0.8 + d.ph2) * d.am * 0.7 - p * s.h * 0.25 * d.r * 0.4;
      g.globalAlpha = d.a * fade;
      g.beginPath(); g.arc(x, y, d.r, 0, TAU); g.fill();
    }
    g.globalAlpha = 1;
  }, '#09090a');
  s.layout = function () {
    var n = clamp(Math.round(s.w * s.h / 6500), 50, 240), q = rng(11);
    dots = [];
    for (var i = 0; i < n; i++) {
      dots.push({ x: q() * s.w, y: q() * s.h, r: 0.6 + q() * 1.8, a: 0.1 + q() * 0.32,
                  ph: q() * TAU, ph2: q() * TAU, sp: 0.05 + q() * 0.12, am: 6 + q() * 24 });
    }
  };
})();

/* ---------- fleet field (sections 2 and 3) ---------- */
function buildField(counts) {
  var out = [], i = 0, k, j, n;
  if (counts) {
    var merged = {};
    for (k in counts) if (Object.prototype.hasOwnProperty.call(counts, k)) {
      var ck = chipKey(k);
      merged[ck] = (merged[ck] || 0) + counts[k];
    }
    for (j = 0; j < CHIPS.length; j++) {
      n = merged[CHIPS[j]] || 0;
      for (var m = 0; m < n; m++) out.push({ chip: CHIPS[j], col: CHIPCOL[CHIPS[j]] });
    }
  }
  return out;
}
function placeField(dots, box) {
  var N = dots.length, q = rng(23);
  var c0 = box.R / Math.sqrt(Math.max(N, 1));
  var rad = clamp(c0 * 0.62, 1.1, 7);
  for (var i = 0; i < N; i++) {
    var d = dots[i];
    d.i = i; d.a0 = i * GA; d.r0 = Math.sqrt((i + 0.5) / N); d.rad = rad;
    d.u = q();
  }
}
function fieldBox(s, copyEl, bottomReserve) {
  var w = s.w, h = s.h, base = h - bottomReserve;
  if (w >= 900) {
    return { cx: w * 0.7, cy: base * 0.5 + 14, R: Math.max(40, Math.min((base - 60) * 0.5, w * 0.27)) };
  }
  var top = h * 0.36;
  if (copyEl) {
    var hr = s.cv.getBoundingClientRect(), cr = copyEl.getBoundingClientRect();
    top = Math.max(top, cr.bottom - hr.top + 14);
  }
  var avail = Math.max(60, base - top);
  var R = Math.max(36, Math.min(w * 0.44, avail * 0.48));
  return { cx: w / 2, cy: top + avail / 2, R: R };
}

/* ---------- 2 the fleet ---------- */
var fleetDots = [];
(function () {
  var c = $('cv-fleet');
  if (!c) return;
  var counts = null;
  if (EV) { counts = EV.chips_before || {}; }
  fleetDots = buildField(counts);
  if (!EV) {
    var last = TL.length ? TL[TL.length - 1].macs : 0;
    fleetDots = [];
    for (var i = 0; i < last; i++) fleetDots.push({ chip: 'none', col: NEUTRAL });
  }
  var N = fleetDots.length;
  var noBefore = !!EV && !EV.chips_before;
  if (noBefore) {
    setText('fleet-title', FLEET_NO_BEFORE);
    setText('fleet-sub', 'The ' + evName(EV) + ' at ' + hm(T(EV.at)) + ' UTC on ' + ymd(T(EV.at)) + ' is the first thing in the recording.');
  } else if (!EV && !TL.length) {
    setText('fleet-title', NO_SNAPSHOTS);
    setText('fleet-sub', '');
  } else {
    setText('fleet-title', fmt(N, 0) + (N === 1 ? ' Mac, one dot each.' : ' Macs, one dot each.'));
  }
  if (noBefore || (!EV && !TL.length)) {
    /* text set above; nothing to list */
  } else if (EV) {
    setText('fleet-sub', 'The last snapshot before the ' + evName(EV) + ' at ' + hm(T(EV.at)) + ' UTC on ' +
      ymd(T(EV.at)) + ', coloured by chip family.');
    var lg = $('legend');
    if (lg) {
      var merged = {};
      fleetDots.forEach(function (d) { merged[d.chip] = (merged[d.chip] || 0) + 1; });
      CHIPS.forEach(function (k) {
        if (!merged[k]) return;
        var li = document.createElement('li'), sw = document.createElement('i'),
            nm = document.createElement('span'), ct = document.createElement('b');
        sw.style.background = CHIPCOL[k];
        nm.textContent = chipName(k);
        ct.textContent = fmt(merged[k], 0);
        li.appendChild(sw); li.appendChild(nm); li.appendChild(ct);
        lg.appendChild(li);
      });
    }
  } else {
    setText('fleet-sub', 'No restart or release was seen, so the chip mix is not available. One dot per Mac in the last snapshot.');
  }
  var box;
  var s = makeStage(c, $('s-fleet'), enterProg(0.1, 0.9), function (s, e, t) {
    var g = s.ctx, rot = (1 - eo(e)) * -1.3 + t * 0.018;
    for (var i = 0; i < N; i++) {
      var d = fleetDots[i];
      var lp = clamp((e * 1.6 - d.i / N * 0.7) / 0.9, 0, 1);
      if (lp <= 0) continue;
      var k = eo(lp), ang = d.a0 + rot, rr = d.r0 * box.R * (0.55 + 0.45 * k);
      g.globalAlpha = k * 0.96;
      g.fillStyle = d.col;
      g.beginPath();
      g.arc(box.cx + Math.cos(ang) * rr, box.cy + Math.sin(ang) * rr, d.rad * (0.3 + 0.7 * k), 0, TAU);
      g.fill();
    }
    g.globalAlpha = 1;
  }, '#101112');
  s.layout = function () {
    box = fieldBox(s, document.querySelector('#s-fleet .copy'), 24);
    placeField(fleetDots, box);
  };
})();

/* ---------- 3 the event ---------- */
(function () {
  var c = $('cv-event');
  if (!c || !EV) return;
  var W = EV.window || [];
  if (!W.length) {
    // no snapshots in the window: the page says so (server-rendered), no clock, no count
    setText('ev-title', cap(evName(EV)));
    setText('ev-date', ymd(T(EV.at)) + ' UTC');
    return;
  }
  var N = 0;
  for (var k in EV.chips_before) if (Object.prototype.hasOwnProperty.call(EV.chips_before, k)) N += EV.chips_before[k];
  var tw = W.map(function (e) { return T(e.t); });
  var mv = W.map(function (e) { return e.macs; });
  var maxM = Math.max.apply(null, mv.concat([N, 1]));
  if (!N) N = maxM;
  var dots = buildField(EV.chips_before);
  if (dots.length < N) { for (var q = dots.length; q < N; q++) dots.push({ chip: 'none', col: NEUTRAL }); }
  var cum = [0];
  for (var i = 1; i < W.length; i++) {
    cum.push(cum[i - 1] + 1 + 8 * Math.abs(mv[i] - mv[i - 1]) / maxM);
  }
  var at = T(EV.at);
  var rec = EV.recovery_minutes;
  var recAt = rec === null || rec === undefined ? null : at + rec * 60000;
  var ev = EV;
  setText('ev-title', cap(evName(ev)));
  setText('ev-date', ymd(at) + ' UTC');
  if (ev.drop === null || ev.drop === undefined) {
    $('ev-drop').textContent = '';
  } else if (ev.drop <= 0) {
    $('ev-drop').textContent = 'No drop in Macs online.';
  } else {
    var st = document.createElement('strong');
    st.textContent = 'about ' + fmt(Math.round(ev.drop), 0);
    $('ev-drop').textContent = 'Dropped ';
    $('ev-drop').appendChild(st);
    $('ev-drop').appendChild(document.createTextNode(' Macs' + (ev.baseline_macs ? ' (median of the 30 minutes before was about ' + fmt(Math.round(ev.baseline_macs), 0) + ').' : '.')));
  }
  var recNote = $('ev-rec');
  if (recAt === null) {
    recNote.textContent = ev.baseline_macs ? 'Did not get back to 95% inside the window.' : '';
  } else {
    var st2 = document.createElement('strong');
    st2.textContent = fmt(rec, 2);
    recNote.textContent = 'Back to 95% in ';
    recNote.appendChild(st2);
    recNote.appendChild(document.createTextNode(' min.'));
  }
  var box, lastClock = '', lastMacs = '';
  function pos(p) {
    if (W.length < 2) return { T: tw[0] || at, macs: mv[0] || 0, end: true };
    var x = clamp((p - 0.03) / 0.94, 0, 1) * cum[cum.length - 1], j = 0;
    while (j < cum.length - 2 && cum[j + 1] <= x) j++;
    var f = clamp((x - cum[j]) / (cum[j + 1] - cum[j]), 0, 1);
    var Tm = lerp(tw[j], tw[j + 1], f), k = j;
    // observed values only: the most recent snapshot at or before the clock
    while (k < tw.length - 1 && tw[k + 1] <= Tm) k++;
    return { T: Tm, macs: mv[k], end: p >= 0.97 };
  }
  var s = makeStage(c, $('s-event'), function (r) {
    return clamp(-r.top / Math.max(1, r.height - vh), 0, 1);
  }, function (s, p, t) {
    var g = s.ctx, ps = pos(p), Tm = ps.T;
    var frac = clamp(ps.macs / N, 0, 1);
    // dots go out and come back in step with Macs online
    var rot = t * 0.012;
    for (var i = 0; i < dots.length; i++) {
      var d = dots[i], ang = d.a0 + rot, rr = d.r0 * box.R;
      var x = box.cx + Math.cos(ang) * rr, y = box.cy + Math.sin(ang) * rr;
      var a = clamp((frac - d.u * 0.94 - 0.03) * 18 + 0.5, 0, 1);
      g.globalAlpha = 0.07;
      g.fillStyle = INK2;
      g.beginPath(); g.arc(x, y, d.rad * 0.8, 0, TAU); g.fill();
      if (a > 0) {
        g.globalAlpha = a * 0.96;
        g.fillStyle = d.col;
        g.beginPath(); g.arc(x, y, d.rad * (0.5 + 0.5 * a), 0, TAU); g.fill();
      }
    }
    g.globalAlpha = 1;
    // time strip: Macs online across the window, playhead follows scroll
    if (W.length > 1) {
      var pl = clamp(s.w * 0.05, 20, 64), x0 = pl, x1 = s.w - pl, yb = s.h - 46, yt = s.h - 108;
      var t0 = tw[0], t1 = tw[tw.length - 1];
      var X = function (tm) { return x0 + (tm - t0) / Math.max(1, t1 - t0) * (x1 - x0); };
      var Y = function (m) { return yb - clamp(m / maxM, 0, 1) * (yb - yt); };
      g.strokeStyle = AXIS; g.lineWidth = 1;
      g.beginPath(); g.moveTo(x0, yb + 0.5); g.lineTo(x1, yb + 0.5); g.stroke();
      g.strokeStyle = INK2; g.lineWidth = 2; g.lineJoin = 'round'; g.lineCap = 'round';
      g.beginPath();
      for (var i2 = 0; i2 < W.length; i2++) {
        if (i2) { g.lineTo(X(tw[i2]), Y(mv[i2 - 1])); g.lineTo(X(tw[i2]), Y(mv[i2])); }
        else g.moveTo(X(tw[i2]), Y(mv[i2]));
      }
      g.stroke();
      var xe = X(at);
      g.strokeStyle = MUTED; g.lineWidth = 1;
      g.beginPath(); g.moveTo(xe + 0.5, yt - 6); g.lineTo(xe + 0.5, yb); g.stroke();
      g.font = '11px ' + MONO; g.fillStyle = MUTED; g.textBaseline = 'alphabetic';
      g.textAlign = 'left'; g.fillText(hm(t0), x0, yb + 18);
      g.textAlign = 'right'; g.fillText(hm(t1), x1, yb + 18);
      g.textAlign = xe > (x0 + x1) / 2 ? 'right' : 'left';
      g.fillText('event', xe + (xe > (x0 + x1) / 2 ? -6 : 6), yt - 8);
      var xp = X(Tm);
      g.strokeStyle = INK; g.globalAlpha = 0.8;
      g.beginPath(); g.moveTo(xp + 0.5, yt - 6); g.lineTo(xp + 0.5, yb); g.stroke();
      g.globalAlpha = 1;
      dot(g, xp, Y(ps.macs), 4, INK, 2, s.bg);
    }
    var cl = hms(Tm), mc = fmt(ps.macs, 0);
    if (cl !== lastClock) { $('ev-clock').firstChild.nodeValue = cl; lastClock = cl; }
    if (mc !== lastMacs) { $('ev-macs').textContent = mc; lastMacs = mc; }
    var passed = Tm >= at, recd = recAt !== null && Tm >= recAt;
    $('ev-drop').classList.toggle('on', RM || passed);
    $('ev-rec').classList.toggle('on', RM || (recAt === null ? ps.end : recd));
    $('ev-hint').classList.toggle('off', RM || p > 0.02);
  }, '#050506');
  s.layout = function () {
    box = fieldBox(s, document.querySelector('#s-event .copy'), 118);
    placeField(dots, box);
  };
})();

/* ---------- line charts (sections 4 and 6) ---------- */
function niceStep(raw) {
  var e = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), f = raw / e;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * e;
}
function lineChart(o) {
  var pts = o.pts, wrap = o.wrap, canvas = o.canvas, tipEl = o.tip, tipFn = o.tipFn;
  if (!pts.length) return null;
  var g = {}, s;
  var vmax = 0, tmin = pts[0].t, tmax = pts[pts.length - 1].t;
  pts.forEach(function (p) { if (p.v !== null && p.v > vmax) vmax = p.v; });
  function layout() {
    g.ml = s.w < 480 ? 46 : 54; g.mr = o.mr ? (s.w < 480 ? o.mr * 0.8 : o.mr) : 16; g.mt = 14; g.mb = 30;
    var step = niceStep(Math.max(vmax, o.integer ? 1 : 1e-9) / 4);
    if (o.integer) step = Math.max(1, step);
    g.step = step; g.ymax = Math.max(step, Math.ceil(vmax / step) * step);
    g.x0 = g.ml; g.x1 = s.w - g.mr; g.yb = s.h - g.mb; g.yt = g.mt;
  }
  function X(t) { return g.x0 + (t - tmin) / Math.max(1, tmax - tmin) * (g.x1 - g.x0); }
  function Y(v) { return g.yb - v / g.ymax * (g.yb - g.yt); }
  function fmtFor(stepMs) {
    if (stepMs >= 86400000) return function (tm) { return mdhm(tm).slice(0, 5); };
    return (tmax - tmin) / 60000 >= 1440 ? mdhm : hm;
  }
  function span() {
    var sp = (tmax - tmin) / 60000;
    var steps = [5, 10, 15, 30, 60, 120, 180, 360, 720, 1440, 2880, 4320, 10080];
    s.ctx.font = '11px ' + MONO;
    for (var i = 0; i < steps.length; i++) {
      var ms = steps[i] * 60000, f = fmtFor(ms);
      var lw = s.ctx.measureText(f(tmin)).width + 18;
      var maxTicks = Math.max(2, Math.floor((g.x1 - g.x0) / lw));
      if (sp / steps[i] <= maxTicks) return ms;
    }
    return steps[steps.length - 1] * 60000;
  }
  s = makeStage(canvas, wrap, enterProg(0.12, 0.55), function (s, p, t) {
    var c = s.ctx, i, first;
    var reveal = eo(p);
    // grid + y labels
    c.lineWidth = 1; c.font = '11px ' + MONO; c.textAlign = 'right'; c.textBaseline = 'middle';
    for (var v = 0; v <= g.ymax + 1e-9; v += g.step) {
      var y = Math.round(Y(v)) + 0.5;
      c.strokeStyle = v === 0 ? AXIS : GRID;
      c.beginPath(); c.moveTo(g.x0, y); c.lineTo(g.x1, y); c.stroke();
      c.fillStyle = MUTED; c.fillText(fmt(v, 0), g.ml - 8, y);
    }
    // x ticks
    var st = span(), tfmt = fmtFor(st);
    c.textBaseline = 'alphabetic';
    var first0 = Math.ceil(tmin / st) * st, lastRight = -1e9;
    for (var tt = first0; tt <= tmax; tt += st) {
      var xx = X(tt), label = tfmt(tt), wl = c.measureText(label).width;
      c.strokeStyle = GRID;
      c.beginPath(); c.moveTo(Math.round(xx) + 0.5, g.yb); c.lineTo(Math.round(xx) + 0.5, g.yb + 4); c.stroke();
      if (xx - wl / 2 > lastRight + 6 && xx - wl / 2 >= 0 && xx + wl / 2 <= s.w) {
        c.textAlign = 'center'; c.fillStyle = MUTED; c.fillText(label, xx, g.yb + 19);
        lastRight = xx + wl / 2;
      }
    }
    if (o.under) o.under(c, g, X, Y, reveal);
    // series: area then line, drawn progressively
    var xr = g.x0 + reveal * (g.x1 - g.x0);
    var segs = [], cur = [];
    pts.forEach(function (pt) {
      if (pt.v === null) { if (cur.length) segs.push(cur); cur = []; } else cur.push(pt);
    });
    if (cur.length) segs.push(cur);
    segs.forEach(function (sg) {
      var xs = X(sg[0].t);
      if (xs > xr) return;
      var path = [];
      for (i = 0; i < sg.length; i++) {
        var px = X(sg[i].t);
        if (px <= xr) { path.push([px, Y(sg[i].v)]); }
        else {
          var q = sg[i - 1] ? X(sg[i - 1].t) : px, f = (xr - q) / Math.max(1e-6, px - q);
          path.push([xr, lerp(Y(sg[i - 1].v), Y(sg[i].v), clamp(f, 0, 1))]);
          break;
        }
      }
      if (o.area && path.length > 1) {
        c.globalAlpha = 0.1; c.fillStyle = o.color;
        c.beginPath(); c.moveTo(path[0][0], g.yb);
        for (i = 0; i < path.length; i++) c.lineTo(path[i][0], path[i][1]);
        c.lineTo(path[path.length - 1][0], g.yb); c.closePath(); c.fill();
        c.globalAlpha = 1;
      }
      c.strokeStyle = o.color; c.lineWidth = 2; c.lineJoin = 'round'; c.lineCap = 'round';
      c.beginPath();
      for (i = 0; i < path.length; i++) { if (i) c.lineTo(path[i][0], path[i][1]); else c.moveTo(path[i][0], path[i][1]); }
      if (path.length === 1) c.lineTo(path[0][0] + 0.01, path[0][1]);
      c.stroke();
    });
    if (o.over) o.over(c, g, X, Y, reveal);
    // hover crosshair and marker
    if (s.hover >= 0 && s.hover < pts.length) {
      var hp = pts[s.hover], hx = X(hp.t);
      c.strokeStyle = INK; c.globalAlpha = 0.35; c.lineWidth = 1;
      c.beginPath(); c.moveTo(Math.round(hx) + 0.5, g.yt); c.lineTo(Math.round(hx) + 0.5, g.yb); c.stroke();
      c.globalAlpha = 1;
      if (hp.v !== null) dot(c, hx, Y(hp.v), 4, o.color, 2, s.bg);
    }
  }, o.bg);
  s.layout = layout;
  canvas.setAttribute('tabindex', '0');
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', o.label);
  function nearest(clientX) {
    var r = canvas.getBoundingClientRect(), x = clientX - r.left;
    var tm = tmin + clamp((x - g.x0) / Math.max(1, g.x1 - g.x0), 0, 1) * (tmax - tmin);
    var lo = 0, hi = pts.length - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (pts[mid].t <= tm) lo = mid; else hi = mid; }
    return Math.abs(pts[lo].t - tm) <= Math.abs(pts[hi].t - tm) ? lo : hi;
  }
  function show(i) {
    s.hover = i;
    var pt = pts[i], d = tipFn(pt);
    while (tipEl.firstChild) tipEl.removeChild(tipEl.firstChild);
    var b = document.createElement('b'); b.textContent = d.value;
    var l1 = document.createElement('span'); l1.textContent = d.label;
    var l2 = document.createElement('span'); l2.textContent = d.time;
    tipEl.appendChild(b); tipEl.appendChild(l1); tipEl.appendChild(l2);
    tipEl.classList.add('on');
    var W2 = wrap.clientWidth, tw2 = tipEl.offsetWidth, px = X(pt.t);
    var left = px + 14 + tw2 > W2 ? px - 14 - tw2 : px + 14;
    tipEl.style.left = Math.max(0, left) + 'px';
    tipEl.style.top = '6px';
    schedule();
  }
  function hide() { s.hover = -1; tipEl.classList.remove('on'); schedule(); }
  canvas.addEventListener('pointermove', function (e) { show(nearest(e.clientX)); });
  canvas.addEventListener('pointerdown', function (e) { show(nearest(e.clientX)); });
  canvas.addEventListener('pointerleave', hide);
  canvas.addEventListener('blur', hide);
  canvas.addEventListener('keydown', function (e) {
    var i = s.hover < 0 ? pts.length - 1 : s.hover;
    if (e.key === 'ArrowLeft') i = Math.max(0, i - 1);
    else if (e.key === 'ArrowRight') i = Math.min(pts.length - 1, i + 1);
    else if (e.key === 'Escape') { hide(); return; }
    else return;
    e.preventDefault(); show(i);
  });
  return { stage: s, X: X, Y: Y, g: g };
}
function tableView(host, cols, rowsFn) {
  var d = host;
  d.addEventListener('toggle', function () {
    if (!d.open || d.getAttribute('data-built')) return;
    d.setAttribute('data-built', '1');
    var box = document.createElement('div'), tb = document.createElement('table'), thd = document.createElement('thead');
    box.className = 'box';
    var hr = document.createElement('tr');
    cols.forEach(function (c) { var th = document.createElement('th'); th.textContent = c; hr.appendChild(th); });
    thd.appendChild(hr); tb.appendChild(thd);
    var tbody = document.createElement('tbody');
    rowsFn().forEach(function (r) {
      var tr = document.createElement('tr');
      r.forEach(function (v) { var td = document.createElement('td'); td.textContent = v; tr.appendChild(td); });
      tbody.appendChild(tr);
    });
    tb.appendChild(tbody); box.appendChild(tb); d.appendChild(box);
  });
}

/* ---------- 4 throughput ---------- */
(function () {
  var canvas = $('cv-thru');
  if (!canvas || !EV) return;
  var W = EV.window || [];
  var pts = W.map(function (e) { return { t: T(e.t), v: e.rpm, macs: e.macs }; });
  var at = T(EV.at);
  function rate(v) { return v === null || v === undefined ? 'no measurement' : fmt(v, 1) + ' requests per minute'; }
  setText('thru-sub', 'Before the event: ' + rate(EV.requests_per_min_before) + '. First 30 minutes after: ' +
    rate(EV.requests_per_min_after) + '.');
  function pill(c, text, x, y, align) {
    c.font = '12px ' + SANS; c.textBaseline = 'alphabetic';
    var w = c.measureText(text).width;
    var lx = align === 'right' ? x - w : x;
    c.fillStyle = '#0d0d0e'; c.globalAlpha = 0.85;
    c.fillRect(lx - 4, y - 13, w + 8, 18);
    c.globalAlpha = 1; c.fillStyle = INK2; c.textAlign = align; c.fillText(text, x, y);
  }
  lineChart({
    canvas: canvas, wrap: $('thru-wrap'), tip: $('thru-tip'), pts: pts, color: INK2, area: false,
    bg: '#0d0d0e', mr: 20,
    label: 'Requests per minute across the event window. Use left and right arrow keys to read values.',
    tipFn: function (p) {
      return { value: p.v === null ? 'no measurement' : fmt(p.v, 1), label: 'requests per minute', time: hms(p.t) + ' UTC' };
    },
    over: function (c, g, X, Y, reveal) {
      var xe = X(at), xr = g.x0 + reveal * (g.x1 - g.x0);
      c.strokeStyle = MUTED; c.lineWidth = 1;
      c.beginPath(); c.moveTo(Math.round(xe) + 0.5, g.yt); c.lineTo(Math.round(xe) + 0.5, g.yb); c.stroke();
      c.font = '11px ' + SANS; c.fillStyle = MUTED; c.textBaseline = 'alphabetic';
      c.textAlign = 'left'; c.fillText(EV.kind === 'release' ? 'release' : 'restart', xe + 6, g.yt + 10);
      if (xr < xe) return;
      var a = clamp((xr - xe) / 60 + 0.3, 0, 1);
      c.globalAlpha = a;
      var vb = EV.requests_per_min_before, va = EV.requests_per_min_after;
      var end = Math.min(g.x1, X(at + 30 * 60000)), narrow = g.x1 - g.x0 < 420;
      var unit = narrow ? '' : ' per min';
      if (vb !== null && vb !== undefined) {
        c.strokeStyle = INK; c.lineWidth = 1;
        c.beginPath(); c.moveTo(g.x0, Math.round(Y(vb)) + 0.5); c.lineTo(xe, Math.round(Y(vb)) + 0.5); c.stroke();
        pill(c, 'before ' + fmt(vb, 1) + unit, g.x0 + 6, Y(vb) - 8, 'left');
      }
      if (va !== null && va !== undefined) {
        c.strokeStyle = INK; c.lineWidth = 1;
        c.beginPath(); c.moveTo(xe, Math.round(Y(va)) + 0.5); c.lineTo(end, Math.round(Y(va)) + 0.5); c.stroke();
        pill(c, 'after ' + fmt(va, 1) + unit, xe + 6, Y(va) + 20, 'left');
      }
      c.globalAlpha = 1;
    }
  });
  var dt = $('thru-details');
  if (dt) tableView(dt, ['Time (UTC)', 'Macs online', 'Requests per min'], function () {
    return pts.map(function (p) { return [hms(p.t), fmt(p.macs, 0), p.v === null ? '-' : fmt(p.v, 1)]; });
  });
})();

/* ---------- 5 left behind ---------- */
(function () {
  var canvas = $('cv-left');
  if (!canvas || !EV) return;
  var name = evName(EV);
  var nbNull = EV.stuck_before === null || EV.stuck_before === undefined;
  var naNull = EV.stuck_after === null || EV.stuck_after === undefined;
  var ncNull = EV.stuck_carried === null || EV.stuck_carried === undefined;
  if (nbNull || naNull || ncNull) {
    var msgB = 'No stuck count: no snapshot with providers in the 30 minutes before the event.';
    var msgA = 'No stuck count: no snapshot with providers in the 3 hours after the event.';
    $('left-title').textContent = 'No stuck count for this event.';
    $('left-before').textContent = nbNull ? msgB : 'Stuck in the last snapshot before the ' + name + ': ' + fmt(EV.stuck_before, 0) + '.';
    $('left-after').textContent = naNull ? msgA : 'Stuck in the snapshot closest to 60 minutes after: ' + fmt(EV.stuck_after, 0) + '.';
    $('left-carried').textContent = '';
    $('left-note').textContent = 'Stuck counts are shown only when a snapshot with providers exists on both sides of the event.';
    canvas.style.display = 'none';
    return;
  }
  var nb = EV.stuck_before, na = EV.stuck_after, nc = Math.min(EV.stuck_carried, nb, na);
  $('left-title').textContent = fmt(nb, 0) + ' stuck before, ' + fmt(na, 0) + ' after.';
  $('left-before').textContent = 'Stuck in the last snapshot before the ' + name + ': ' + fmt(nb, 0) + '.';
  $('left-after').textContent = 'Stuck in the snapshot closest to 60 minutes after: ' + fmt(na, 0) + '.';
  $('left-carried').textContent = fmt(nc, 0) + ' matched the same hardware with identical non-zero request counters, so they stayed stuck through the ' + name + '.';
  $('left-note').textContent = 'Carried counts only matches on non-zero requests_served. The rest cannot be matched from public counters. Dot positions are not machine identities.';
  var A = [], B = [], arcs = [], geo;
  function cluster(n, cx, cy, R) {
    var out = [], rad = clamp(R * 0.6 / Math.sqrt(Math.max(n, 1)), 3, 15);
    for (var i = 0; i < n; i++) {
      var a = i * GA + 0.6, r = Math.sqrt((i + 0.5) / n) * R;
      out.push({ x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r, r: rad });
    }
    return out;
  }
  var s = makeStage(canvas, $('s-left'), enterProg(0.15, 0.7), function (s, p, t) {
    var g = s.ctx;
    var pa = ss(p / 0.4), pc = ss((p - 0.3) / 0.4), pb = ss((p - 0.6) / 0.4);
    // arcs first so the dots sit on top
    g.strokeStyle = ACCENT; g.lineWidth = 1.5; g.lineCap = 'round';
    arcs.forEach(function (ar) {
      if (pc <= 0) return;
      g.globalAlpha = 0.6;
      g.beginPath();
      var steps = 28, last = Math.max(1, Math.round(steps * pc));
      for (var i = 0; i <= last; i++) {
        var u = i / steps, v = 1 - u;
        var x = v * v * ar.x0 + 2 * v * u * ar.cx + u * u * ar.x1;
        var y = v * v * ar.y0 + 2 * v * u * ar.cy + u * u * ar.y1;
        if (i) g.lineTo(x, y); else g.moveTo(x, y);
      }
      g.stroke();
    });
    g.globalAlpha = 1;
    function draw(list, k, carriedSet) {
      list.forEach(function (d, i) {
        var lp = clamp(k * 1.5 - i / Math.max(list.length, 1) * 0.5, 0, 1);
        if (lp <= 0) return;
        var wob = RM ? 0 : Math.sin(t * 0.8 + i * 1.7) * 1.2;
        g.globalAlpha = eo(lp) * (carriedSet[i] ? 1 : 0.42);
        dot(g, d.x, d.y + wob, d.r * (0.4 + 0.6 * eo(lp)), ACCENT, 2, s.bg);
      });
      g.globalAlpha = 1;
    }
    draw(A, pa, geo.carA);
    draw(B, pb, geo.carB);
    g.font = '12px ' + SANS; g.fillStyle = MUTED; g.textAlign = 'center'; g.textBaseline = 'alphabetic';
    g.globalAlpha = pa; g.fillText('Before', geo.ax, geo.ly);
    g.globalAlpha = pb; g.fillText('After', geo.bx, geo.ly);
    g.globalAlpha = 1;
  }, '#141312');
  s.layout = function () {
    var w = s.w, h = s.h, copy = document.querySelector('#s-left .copy');
    var hr = s.cv.getBoundingClientRect(), cr = copy.getBoundingClientRect();
    var top = cr.bottom - hr.top + 24;
    var wide = w >= 900;
    var R = Math.max(30, Math.min(wide ? h * 0.2 : w * 0.2, (h - top - 50) * 0.42));
    var cy = wide ? h * 0.62 : top + (h - top - 40) * 0.5;
    if (wide) top = 0;
    var ax = wide ? w * 0.6 : w * 0.26, bx = wide ? w * 0.88 : w * 0.74;
    if (wide) R = Math.min(R, w * 0.1);
    A = cluster(nb, ax, cy, R); B = cluster(na, bx, cy, R);
    // carried dots: those that face the other cluster, paired top to bottom
    var ia = A.map(function (d, i) { return i; }).sort(function (u, v) { return B.length && A[v].x - A[u].x; }).slice(0, nc)
      .sort(function (u, v) { return A[u].y - A[v].y; });
    var ib = B.map(function (d, i) { return i; }).sort(function (u, v) { return B[u].x - B[v].x; }).slice(0, nc)
      .sort(function (u, v) { return B[u].y - B[v].y; });
    geo = { ax: ax, bx: bx, ly: cy + R + 34, carA: {}, carB: {} };
    arcs = [];
    for (var i = 0; i < nc; i++) {
      geo.carA[ia[i]] = true; geo.carB[ib[i]] = true;
      var d0 = A[ia[i]], d1 = B[ib[i]];
      arcs.push({ x0: d0.x, y0: d0.y, x1: d1.x, y1: d1.y, cx: (d0.x + d1.x) / 2,
                  cy: Math.min(d0.y, d1.y) - R * (0.35 + 0.12 * (i % 3)) });
    }
  };
})();

/* ---------- 6 right now ---------- */
(function () {
  var canvas = $('cv-now');
  if (!canvas) return;
  var pts = TL.map(function (e) { return { t: T(e.t), v: e.stuck, macs: e.macs }; });
  if (!pts.length) return; // the page already says there are no readable snapshots
  var nowAt = SN.at ? T(SN.at) : pts[pts.length - 1].t;
  var noCount = SN.count === null || SN.count === undefined;
  setText('now-title', noCount ? 'Stuck now: no measurement.' : fmt(SN.count, 0) + ' stuck now.');
  setText('now-sub', (noCount ? 'The last snapshot, at ' : 'Online or serving with runtime_verified false, as of ') + hm(nowAt) + ' UTC on ' + ymd(nowAt) +
    (noCount ? ', has no providers, so nothing was observed. ' : '. ') + 'The chart runs across the whole recording.');
  var evTimes = EVS.map(function (e) { return T(e.at); });
  lineChart({
    canvas: canvas, wrap: $('now-wrap'), tip: $('now-tip'), pts: pts, color: ACCENT, area: true, integer: true,
    bg: '#0c0c0d', mr: 92,
    label: 'Stuck Macs across the whole recording. Use left and right arrow keys to read values.',
    tipFn: function (p) {
      return { value: p.v === null ? 'no measurement' : fmt(p.v, 0), label: 'stuck, of ' + fmt(p.macs, 0) + ' Macs online', time: hms(p.t) + ' UTC ' + ymd(p.t) };
    },
    under: function (c, g, X, Y) {
      c.strokeStyle = MUTED; c.lineWidth = 1; c.globalAlpha = 0.6;
      evTimes.forEach(function (tm) {
        if (tm < pts[0].t || tm > pts[pts.length - 1].t) return;
        var x = Math.round(X(tm)) + 0.5;
        c.beginPath(); c.moveTo(x, g.yt); c.lineTo(x, g.yb); c.stroke();
      });
      c.globalAlpha = 1;
    },
    over: function (c, g, X, Y, reveal) {
      if (reveal < 0.999) return;
      var last = pts[pts.length - 1];
      if (last.v === null) return;
      var x = X(last.t), y = Y(last.v);
      dot(c, x, y, 4, ACCENT, 2, '#0c0c0d');
      c.font = '12px ' + SANS; c.fillStyle = INK; c.textAlign = 'left'; c.textBaseline = 'middle';
      c.fillText(fmt(last.v, 0) + ' now', x + 12, y);
    }
  });
  var dt = $('now-details');
  if (dt) tableView(dt, ['Time (UTC)', 'Macs online', 'Stuck'], function () {
    return pts.map(function (p) { return [ymd(p.t) + ' ' + hms(p.t), fmt(p.macs, 0), fmt(p.v, 0)]; });
  });
  // by-chip bars
  var bars = $('bars-list');
  if (bars) {
    var by = {}, mx = 0;
    var src = SN.by_chip || {};
    for (var k in src) if (Object.prototype.hasOwnProperty.call(src, k)) {
      var ck = chipKey(k); by[ck] = (by[ck] || 0) + src[k];
    }
    CHIPS.forEach(function (k) { if (by[k] > mx) mx = by[k]; });
    CHIPS.forEach(function (k) {
      if (!by[k]) return;
      var row = document.createElement('div'), lb = document.createElement('span'),
          tr = document.createElement('div'), fl = document.createElement('div'), ct = document.createElement('b');
      row.className = 'row'; tr.className = 'track'; fl.className = 'fill';
      fl.style.setProperty('--w', (by[k] / mx * 100) + '%');
      lb.textContent = chipName(k); ct.textContent = fmt(by[k], 0);
      tr.appendChild(fl); row.appendChild(lb); row.appendChild(tr); row.appendChild(ct);
      bars.appendChild(row);
    });
    if (noCount) {
      var nm = document.createElement('p'); nm.className = 'small'; nm.textContent = 'No measurement: the last snapshot has no providers.';
      bars.appendChild(nm);
    } else if (!bars.children.length) {
      var none = document.createElement('p'); none.className = 'small'; none.textContent = 'No stuck Macs in the last snapshot.';
      bars.appendChild(none);
    }
  }
})();

/* ---------- reveal on scroll ---------- */
(function () {
  var els = [].slice.call(document.querySelectorAll('.rv'));
  function fills(on) {
    [].slice.call(document.querySelectorAll('.fill')).forEach(function (f) {
      f.style.width = on ? f.style.getPropertyValue('--w') : '0';
    });
  }
  if (RM || !('IntersectionObserver' in window)) {
    els.forEach(function (e) { e.classList.add('on'); });
    fills(true);
    return;
  }
  var io = new IntersectionObserver(function (list) {
    list.forEach(function (en) {
      if (en.isIntersecting) {
        en.target.classList.add('on');
        if (en.target.id === 'bars') fills(true);
      }
    });
  }, { threshold: 0.2 });
  els.forEach(function (e) { io.observe(e); });
})();

resizeAll();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(resizeAll);
})();
"""


def _esc(x):
    return html.escape(str(x), quote=True)


def _num(x, digits=1):
    if x is None:
        return "-"
    if isinstance(x, float):
        s = ("%." + str(digits) + "f") % x
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    return str(x)


def _chips(by_chip):
    if not by_chip:
        return "-"
    return ", ".join("%s:%d" % (k, v) for k, v in sorted(by_chip.items()))


def _stamp(iso):
    if not iso:
        return ""
    return iso.replace("T", " ").replace("Z", "")


_COLUMNS = (
    ("Kind", "kind", None),
    ("At (UTC)", "at", None),
    ("Label", "label", None),
    ("Baseline (median)", "baseline_macs", 1),
    ("Min after", "min_macs_after", 1),
    ("Drop", "drop", 1),
    ("Recovery min", "recovery_minutes", 2),
    ("Req per min before", "requests_per_min_before", 1),
    ("Req per min after", "requests_per_min_after", 1),
    ("Stuck before", "stuck_before", 1),
    ("Stuck after", "stuck_after", 1),
    ("Stuck carried", "stuck_carried", 1),
    ("Stuck by chip", "stuck_by_chip", None),
)


def _table(events):
    head = "".join("<th>%s</th>" % _esc(c[0]) for c in _COLUMNS)
    rows = []
    for e in events:
        cells = []
        for title, key, digits in _COLUMNS:
            v = e.get(key)
            if key == "stuck_by_chip":
                text, cls = _chips(v), ' class="chips"'
            elif key == "at":
                text, cls = _stamp(v), ""
            elif digits is None:
                text, cls = ("-" if v is None else str(v)), ""
            else:
                text, cls = _num(v, digits), ""
            cells.append('<td%s data-label="%s">%s</td>' % (cls, _esc(title), _esc(text)))
        rows.append("<tr>%s</tr>" % "".join(cells))
    return (
        '<div class="tablewrap"><table class="ev"><thead><tr>%s</tr></thead>'
        "<tbody>%s</tbody></table></div>" % (head, "".join(rows))
    )


def _embed(data):
    text = json.dumps(data, separators=(",", ":"))
    # "<" cannot appear outside a JSON string, so escaping every one keeps
    # "</script" and "<!--" out of the payload without changing what it parses to.
    return text.replace("<", "\\u003c")


def _open_section(data):
    stuck_now = data.get("stuck_now") or {}
    span = data.get("span") or {}
    count = stuck_now.get("count")
    if count is None:
        asof = ("The last snapshot has no providers, so there is no stuck count."
                if stuck_now.get("at") else NO_SNAPSHOTS_LINE)
    elif stuck_now.get("at"):
        asof = "As of %s UTC, online or serving with runtime_verified false." % _stamp(stuck_now["at"])
    else:
        asof = ""
    if span.get("start") and span.get("end"):
        meta = "Recorded %s to %s UTC, %s snapshots." % (
            _stamp(span["start"]), _stamp(span["end"]), _num(span.get("snapshots", 0), 0),
        )
    else:
        meta = NO_SNAPSHOTS_LINE
    return (
        '<section class="world" id="s-open" data-bg="#09090a" aria-labelledby="name">'
        '<canvas class="cv" id="cv-open" aria-hidden="true"></canvas>'
        '<div class="inner">'
        '<h1 class="name" id="name">wilt</h1>'
        '<p class="lede">Every Darkbloom coordinator restart and provider release, and the Macs it leaves wilted.</p>'
        '<p class="hero" id="hero">%s</p>'
        '<p class="hero-label">Macs stuck right now</p>'
        '<p class="meta">%s</p>'
        '<p class="meta">%s</p>'
        "</div>"
        '<div class="cue" aria-hidden="true"><span>scroll</span><i></i></div>'
        "</section>"
    ) % (_esc(_num(count, 0)), _esc(asof), _esc(meta))


_FLEET_TMPL = """
<section class="world" id="s-fleet" data-bg="#101112" aria-labelledby="fleet-title">
<canvas class="cv" id="cv-fleet" aria-hidden="true"></canvas>
<div class="inner"><div class="copy">
<p class="eyebrow rv">The fleet</p>
<h2 id="fleet-title" class="rv">%s</h2>
<p class="sub rv" id="fleet-sub"></p>
<ul class="legend rv" id="legend"></ul>
</div></div>
</section>
"""

_EVENT_TMPL = """
<section class="tall" id="s-event" data-bg="#050506" aria-labelledby="ev-title">
<div class="sticky">
<canvas class="cv" id="cv-event" aria-hidden="true"></canvas>
<div class="inner"><div class="copy">
<p class="eyebrow">The event</p>
<h2 id="ev-title"></h2>
<p class="clockdate" id="ev-date"></p>
%s
<p class="note" id="ev-drop"></p>
<p class="note" id="ev-rec"></p>
</div></div>
%s
</div>
</section>
"""

_EVENT_LIVE = (
    '<div class="clock" id="ev-clock">-<small>UTC</small></div>\n'
    '<div class="counter"><b id="ev-macs">-</b><span>Macs online</span></div>'
)
_EVENT_HINT = '<p class="hint" id="ev-hint">Scroll to move through time</p>'


def _fleet_section(data):
    events = data.get("events") or []
    title = ""
    if events and events[0].get("chips_before") is None:
        title = FLEET_NO_BEFORE_LINE
    elif not events and not (data.get("timeline") or []):
        title = NO_SNAPSHOTS_LINE
    return _FLEET_TMPL % _esc(title)


AGED_OUT_LINE = ("The newest event's snapshot detail has aged out. "
                 "Its metrics are in the table below.")


def _event_section(events, aged=False):
    if aged:
        return _EVENT_TMPL % (
            '<p class="clock" id="ev-nowin" style="font-size:clamp(1.4rem,3.5vw,2.4rem)">%s</p>'
            % _esc(AGED_OUT_LINE),
            "",
        )
    if events and not events[0].get("window"):
        return _EVENT_TMPL % (
            '<p class="clock" id="ev-nowin" style="font-size:clamp(1.4rem,3.5vw,2.4rem)">%s</p>'
            % _esc(NO_WINDOW_LINE),
            "",
        )
    return _EVENT_TMPL % (_EVENT_LIVE, _EVENT_HINT)


_THROUGHPUT = """
<section class="world" id="s-thru" data-bg="#0d0d0e" aria-labelledby="thru-title">
<div class="inner">
<p class="eyebrow rv">Throughput</p>
<h2 id="thru-title" class="rv">Requests per minute</h2>
<p class="sub rv" id="thru-sub"></p>
<div class="chart" id="thru-wrap"><canvas id="cv-thru"></canvas><div class="tip" id="thru-tip"></div></div>
<details class="tv" id="thru-details"><summary>Table view</summary></details>
</div>
</section>
"""

_LEFT = """
<section class="world" id="s-left" data-bg="#141312" aria-labelledby="left-title">
<canvas class="cv" id="cv-left" aria-hidden="true"></canvas>
<div class="inner"><div class="copy">
<p class="eyebrow rv">Left behind</p>
<h2 id="left-title" class="rv"></h2>
<div class="counts rv">
<p id="left-before"></p>
<p id="left-after"></p>
<p id="left-carried"></p>
</div>
<p class="small rv" id="left-note"></p>
</div></div>
</section>
"""

_NOW_TMPL = """
<section class="world" id="s-now" data-bg="#0c0c0d" aria-labelledby="now-title">
<div class="inner">
<p class="eyebrow rv">Right now</p>
<h2 id="now-title" class="rv">%s</h2>
<p class="sub rv" id="now-sub">%s</p>
<div class="chart" id="now-wrap"><canvas id="cv-now"></canvas><div class="tip" id="now-tip"></div></div>
<details class="tv" id="now-details"><summary>Table view</summary></details>
%s
</div>
</section>
"""

_NOW_BARS = '<div class="bars rv" id="bars"><h3>Stuck now by chip</h3><div id="bars-list"></div></div>'


def _now_section(data):
    if not (data.get("timeline") or []):
        return _NOW_TMPL % (_esc(NO_SNAPSHOTS_LINE), "", "")
    return _NOW_TMPL % ("", "", _NOW_BARS)


def _none_section():
    return (
        '<section class="world" id="s-none" data-bg="#050506">'
        '<div class="inner"><p class="eyebrow">The events</p>'
        '<p class="none">%s</p></div></section>' % _esc(NO_EVENTS_LINE)
    )


def _table_section(events):
    intro = ""
    if events:
        first = (events[-1].get("at") or "")[:10]
        intro = '<p class="sub">%d events scored since %s</p>' % (len(events), _esc(first))
        body = intro + _table(events)
    else:
        body = '<p class="sub">%s</p>' % _esc(NO_EVENTS_LINE)
    return (
        '<section class="world" id="s-table" data-bg="#0f0f10" aria-labelledby="table-title">'
        '<div class="inner"><p class="eyebrow">Every event</p>'
        '<h2 id="table-title">Newest first</h2>%s</div></section>' % body
    )


def render_page(data):
    """data: {"timeline", "events", "stuck_now", "span"}. Returns one HTML
    string. The data is embedded verbatim as JSON in a
    <script type="application/json" id="wilt-data"> block."""
    events = data.get("events") or []
    all_events = data.get("all_events")
    if all_events is None:
        all_events = events
    aged = (data.get("all_events") is not None and bool(events)
            and all_events[0]["at"] > events[0]["at"])
    parts = [_open_section(data), _fleet_section(data)]
    if events:
        parts.extend([_event_section(events, aged), _THROUGHPUT, _LEFT])
    else:
        parts.append(_none_section())
    parts.extend([_now_section(data), _table_section(all_events)])

    span = data.get("span") or {}
    foot = "wilt. %s snapshots, all times UTC." % _num(span.get("snapshots", 0), 0)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>wilt</title>\n"
        "<script>document.documentElement.className='js';</script>\n"
        "<style>%s</style>\n</head>\n<body>\n"
        '<div class="bar" id="bar" aria-hidden="true"></div>\n'
        "<main>\n%s\n</main>\n"
        '<footer class="foot">%s</footer>\n'
        '<script type="application/json" id="wilt-data">%s</script>\n'
        "<script>%s</script>\n</body>\n</html>\n"
    ) % (_CSS, "\n".join(parts), _esc(foot), _embed(data), _JS)
