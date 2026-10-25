// Renders every caption, sponsor label and title card in the timeline as a 1920x1080 PNG (transparent where it overlays footage),
// in IBM Plex, so the video's type matches the app. Usage: node overlays.mjs <timeline.json> <outDir>
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";

const [, , TL, OUT] = process.argv;
const FONTS = "/Users/apple/Desktop/all projects/Countersign/frontend/node_modules/@fontsource";
const tl = JSON.parse(fs.readFileSync(TL, "utf8"));
fs.mkdirSync(OUT, { recursive: true });
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
const url = (p) => "file://" + encodeURI(p);

const css = `
@font-face{font-family:Plex;font-weight:400;src:url("${url(FONTS + "/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2")}")}
@font-face{font-family:Plex;font-weight:600;src:url("${url(FONTS + "/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2")}")}
@font-face{font-family:PlexMono;font-weight:400;src:url("${url(FONTS + "/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2")}")}
html,body{margin:0;width:1920px;height:1080px;background:transparent;font-family:Plex,sans-serif;-webkit-font-smoothing:antialiased}
.cap{position:absolute;left:50%;bottom:64px;transform:translateX(-50%);max-width:1500px;background:#16181D;color:#F7F6F2;border-radius:8px;padding:18px 28px;text-align:center}
.cap .who{font-size:22px;color:#9BA1AB;margin-bottom:6px}
.cap .t{font-size:34px;line-height:1.3;font-weight:400}
.cap.top{top:64px;bottom:auto}
.lab.bottom{top:auto;bottom:48px}
.lab{position:absolute;left:40px;top:40px;background:#1F3A5F;color:#fff;border-radius:6px;padding:10px 16px;font-size:24px;font-weight:600}
.card{position:absolute;inset:0;background:#F7F6F2;color:#16181D;padding:0 160px;display:flex;flex-direction:column;justify-content:center}
.big{font-family:PlexMono;font-size:180px;line-height:1}
.mid{font-size:52px;font-weight:600;margin-top:28px;max-width:1300px;line-height:1.2}
.src{font-size:26px;color:#5B5F68;margin-top:28px}
.row{display:flex;align-items:center;gap:28px}
.name{font-size:96px;font-weight:600}
.line{font-size:40px;margin-top:24px}
.small{font-size:30px;color:#5B5F68;margin-top:14px}
.mono{font-family:PlexMono}
`;
const mark = `<svg viewBox="0 0 24 24" width="120" height="120"><rect x="1" y="1" width="22" height="22" rx="5.5" fill="#1F3A5F"/><path d="M5.5 15.2c1.4-1.6 2.3-.2 3.2.9 1.6-3.1 3.6-6.3 6.3-8.6 1.1-.9 2.6-.6 2.4.7-.2 1.4-2 2.4-3.4 2.1" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M5.5 19h13" stroke="#fff" stroke-opacity=".45" stroke-width="1.4" stroke-linecap="round"/></svg>`;
const CARDS = {
  stat: `<div class="card"><div class="big">74%</div><div class="mid">of organizations were hit by business email compromise in 2025.</div><div class="src">Source: 2026 AFP Payments Fraud and Control Survey</div></div>`,
  end: `<div class="card"><div class="row">${mark}<div class="name">Countersign</div></div><div class="line">AI accounts payable that never pays a scammer.</div><div class="small mono">github.com/aayushswami123/Countersign</div><div class="small">Built at Cal Hacks 13.0. Narration and call voice by Cartesia.</div></div>`,
};

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
const shot = async (html, file, opaque = false) => {
  await page.setContent(`<!doctype html><html><head><style>${css}</style></head><body>${html}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(OUT, file), omitBackground: !opaque });
};
const index = {};
for (const seg of tl.segments) {
  if (seg.card) { await shot(CARDS[seg.card], `card_${seg.id}.png`, true); index[`card_${seg.id}`] = 1; }
  (seg.captions || []).forEach((c, i) => {
    index[`cap_${seg.id}_${i}`] = `<div class="cap${c.pos === "top" ? " top" : ""}">${c.who ? `<div class="who">${esc(c.who)}</div>` : ""}<div class="t">${esc(c.text)}</div></div>`;
  });
  (seg.labels || []).forEach((l, i) => { index[`lab_${seg.id}_${i}`] = `<div class="lab${l.pos === "bottom" ? " bottom" : ""}">${esc(l.text)}</div>`; });
}
for (const [k, html] of Object.entries(index)) if (typeof html === "string") await shot(html, `${k}.png`);
await browser.close();
console.log("rendered", Object.keys(index).length, "images into", OUT);
