# Countersign launch video: credits and sources

`countersign-launch.mp4` (1:41.5, 1080p H.264, AAC) and `countersign-30s.mp4` (29.7 s). Built at Cal Hacks 13.0.

## What is real in the video

- Every shot is a screen recording of the running app at 1920x1080, made on Oct 25, 2026 with every service live (no mock flags), except the two title cards.
- The phone call is a real call placed by Twilio to a teammate's phone, who played Summit Concrete. The agent's voice is Cartesia. The audio is the room microphone with the phone on speaker; the caption says a teammate played the vendor.
- Nothing in the video is a replay. Account and routing numbers printed on the invoice PDF are fictional seed data and are blurred anyway.

## Sponsors and services on screen

| Sponsor | What it does in the video |
|---|---|
| Anthropic (Claude) | Reads the invoices, flags instructions aimed at an AI, judges the vendor's answer, and writes the Ask answer (claude-haiku-5-5, shown on screen) |
| Cartesia | The narration (voice "Zander", model sonic-3.6) and the agent's voice on the real call |
| Twilio | Places the verification call and hears the vendor's answer |
| Apify | The Vendor Contact Verifier Actor finds Summit's number on Summit's own website |
| CRS | Checks the vendor and the request (sandbox test identities); the lookalike request fails |
| Capital One Nessie | Pays the 37 clean invoices in the sandbox |

## Tools

- Recording: Playwright (playwright-core 1.56.1) driving Google Chrome, frames from Chrome's screencast; ffmpeg (avfoundation) for the microphone.
- Edit: ffmpeg 9.0.2 (concat, overlay, boxblur, loudnorm, amix). Captions, labels and cards rendered in Chrome in IBM Plex Sans and Mono (Fontsource).
- Checking: faster-whisper (base.en) to confirm what was said on the call and in the final soundtrack.
- No music.

Scripts: `timeline.json` (the cut), `build.py` (the edit), `tools/` (recording and overlay scripts).

## Numbers and their sources

| Number | Source |
|---|---|
| $18,613.56 ("eighteen thousand dollar scam") | The real call in this video (payment pay_e492c86e3243) and docs/audit-report.md |
| 74% of organizations hit by business email compromise in 2025 | 2026 AFP Payments Fraud and Control Survey |
| 40 invoices, 37 paid, 3 stopped, under seven seconds | The weekly run recorded for this video: 40 of 40 processed in 6.6 s (37 paid, 1 held, 2 blocked); docs/audit-report.md measured 6.9 s |
| Nine of nine poisoned documents caught | docs/audit-report.md |
| 200 red-team attacks, 186 caught, $0 lost; a plain AI agent lost $471,512 | demo/redteam-results.json, docs/redteam.md (on screen: $471,511.80) |
