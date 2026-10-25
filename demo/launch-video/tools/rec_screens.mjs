// The non-call footage: system status, the weekly run filling the board, the poisoned invoice revealed, the red-team page.
// No phone call happens here (the weekly run's planted attacks use scripted calls). Usage: node rec_screens.mjs <outDir>
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";

const OUT = process.argv[2];
const APP = process.env.APP || "http://localhost:5173";
fs.mkdirSync(path.join(OUT, "frames"), { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(new Date().toISOString().slice(11, 23), ...a);
process.on("unhandledRejection", (e) => { console.error(e); process.exit(1); });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await context.addInitScript(() => { try { sessionStorage.setItem("countersign-presenting", "1"); } catch {} });
const page = await context.newPage();
await page.goto(`${APP}/status`);
await sleep(2500);

const cdp = await context.newCDPSession(page);
const frames = [];
let n = 0;
cdp.on("Page.screencastFrame", async (f) => {
  const name = `f${String(n++).padStart(6, "0")}.jpg`;
  fs.writeFileSync(path.join(OUT, "frames", name), Buffer.from(f.data, "base64"));
  frames.push({ name, t: f.metadata.timestamp });
  await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080 });
const marks = [];
const mark = (label) => { marks.push({ label, t: Date.now() / 1000 }); log("MARK", label); };

// 1. System status: hold, then scroll once through the list
mark("status");
await sleep(3000);
await page.mouse.wheel(0, 500);
await sleep(3000);

// 2. The weekly run: the board fills
await page.goto(`${APP}/`);
await sleep(2000);
mark("board before run");
await page.getByRole("button", { name: "Start payment run" }).first().click();
mark("run started");
for (let i = 0; i < 60; i++) {
  const txt = await page.locator("header, main").first().innerText().catch(() => "");
  if (/40 of 40 processed/.test(await page.innerText("body"))) break;
  await sleep(500);
}
mark("run done");
await sleep(4000);

// 3. The inbox: Keystone's poisoned invoice, hidden text revealed
await page.goto(`${APP}/inbox`);
await sleep(2000);
mark("inbox");
const keystone = page.getByText("Keystone Steel Supply").first();
await keystone.click().catch((e) => log("keystone click", e.message));
await sleep(2000);
const reveal = page.getByRole("button", { name: /Reveal hidden content/i }).first();
await reveal.scrollIntoViewIfNeeded().catch(() => {});
await sleep(1000);
mark("reveal");
await reveal.click().catch((e) => log("reveal click", e.message));
await sleep(5000);

// 4. The red-team page
await page.goto(`${APP}/red-team`);
await sleep(2000);
mark("red team");
await sleep(4000);
await page.mouse.wheel(0, 600);
await sleep(3000);
mark("end");

await cdp.send("Page.stopScreencast");
fs.writeFileSync(path.join(OUT, "take.json"), JSON.stringify({ marks, frames }, null, 1));
await browser.close();
log("done", frames.length, "frames");
