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
await page.goto(`${APP}/inbox`);
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

// The inbox: Keystone's poisoned invoice (thread "Invoice KEY-1080"), opened and its hidden text revealed
await page.goto(`${APP}/inbox`);
await sleep(2500);
mark("inbox");
await page.locator('ul[aria-label="Threads"] button', { hasText: "KEY-1080" }).first().click();
await sleep(2500);
mark("thread");
await page.getByRole("button", { name: /Preview/ }).first().click();
await sleep(3500);
mark("preview");
await page.getByRole("button", { name: "Reveal hidden content" }).click();
mark("revealed");
await sleep(1200);
// the hidden text sits low on the page: bring its outlined box into view, slowly
const box = page.getByText(/White text|Text colored like/).first();
await box.scrollIntoViewIfNeeded().catch((e) => log("scroll to finding", e.message));
mark("finding in view");
await sleep(6000);
mark("end");

await cdp.send("Page.stopScreencast");
fs.writeFileSync(path.join(OUT, "take.json"), JSON.stringify({ marks, frames }, null, 1));
await browser.close();
log("done", frames.length, "frames");
