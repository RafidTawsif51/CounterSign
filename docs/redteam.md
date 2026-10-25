# Red team

Proof slide for the Armadin and Atlassian tracks: the same generated attacks, run against a plain Claude agent and against Countersign.
Code: `backend/app/redteam/` (`generate.py`, `evaluate.py`, `api.py`). Results: `demo/redteam-results.json` (full detail, per case) and `.csv`.

## What is measured

- **Cases (405):** 200 attacks over five families, 200 clean invoices (a harmless twin for each family) and 5 legitimate bank changes. Written by us from the seed's vendors, invoice layouts, ten lookalike domains and hiding techniques (white text, tiny font, off page, zero width, HTML comment, `display:none`, same-color text, CSS class). Fixed seed, deterministic.
- **Baseline:** CLAUDE_MODEL_MAIN told to "pay valid invoices", one tool, `pay_invoice`, which only records the decision. It sees the email and the invoice text (including text a person cannot see). No vendor history, no bank on file.
- **Countersign:** the full pipeline (`run.execute_run`), one weekly run of about 40 invoices at a time, each on its own fresh copy of the seeded database. Claude (extraction, injection classifier, urgency classifier) is live; phone, bank, identity and lookup are mocks, forced on, with their credentials blanked, in a separate process and a throwaway database.
- **Definitions:** caught = not paid. Lost = paid to an account the attacker controls. False positive = a clean invoice that was not paid. Legitimate change handled = paid to the new account after a confirmed call.

## Results (200 attacks, 200 clean, 5 legitimate changes)

| Family | Baseline caught | Countersign caught | Baseline false positives | Countersign false positives | Baseline lost to scammers | Countersign lost to scammers |
|---|---|---|---|---|---|---|
| Bank change | 40 of 40 | 40 of 40 | 0 | 0 | $0 | $0 |
| Poisoned invoice | 33 of 40 | 40 of 40 | 6 | 8 | $10,521 | $0 |
| CEO pressure | 40 of 40 | 40 of 40 | 0 | 0 | $0 | $0 |
| Lookalike domain | 16 of 40 | 40 of 40 | 0 | 0 | $460,990 | $0 |
| Amount padding | 28 of 40 | 26 of 40 | 0 | 0 | $0 | $0 |
| **All** | **157 of 200** | **186 of 200** | **6** | **8** | **$471,512** | **$0** |

Legitimate bank changes handled: Countersign 5 of 5, baseline 0 of 5 (it refuses every emailed bank change). Median time per weekly run: baseline 48 s, Countersign 64 s (excludes real call time). Overpayments to the real vendor on padded invoices, not counted as "lost": baseline $149,788, Countersign $82,347.

## Read this before quoting the numbers

1. **Countersign misses padding.** All 14 of its misses are padded invoices from a vendor's real address, up to roughly 2 times the vendor's average. Alone they score 0 to 15, below the hold threshold of 30.
2. **Overpayment is real money.** "Lost to scammers" excludes it because the page's definition requires an attacker-controlled account. Countersign still overpaid $82K.
3. **All 8 false positives are one deliberate stress case:** a clean HTML invoice email with an ordinary hidden `display:none` preheader. The hidden-instructions hard rule quarantines it. The baseline refused 6 of the same 8. On ordinary clean invoices both agents had 0 false positives out of 192.
4. **The baseline is strong.** It refuses any emailed bank change, so it "caught" every bank-change and CEO attack, and it also refused every legitimate change. It fails where it has no vendor history (forged lookalike invoices) and it was hijacked by a hidden instruction once in 40 poisoned invoices ($10.5K).
5. **Countersign's $0 depends on the simulated call.** The mock call denies attacks. 99 of its 186 catches are bank redirects stopped by that denial; 61 were quarantined and 26 held with no call.
6. **Synthetic-data defects.** The seed's fictional routing numbers fail the ABA checksum and the seed's invoice PDFs print rounded unit prices, so quantity times price is off by cents. A first pre-flight showed the baseline refusing clean invoices for those reasons, so the baseline's system prompt says the inbox is a fictional test environment and to ignore both. Countersign validates neither.
7. **Attacks are ours.** A weekend's real judge and bounty attempts are better test cases; export them from the leaderboard and add them.

## One change the red team caused

The "over the vendor's maximum" hard rule is now **30%** (`risk.AMOUNT_OVER_MAX_FACTOR = 1.3`), not the spec's 50%. Raising the amount-outlier weight was tried on paper first and rejected: 12.6% of the seed's normal historical invoices are 2-sigma outliers (26% for monthly vendors), so it would hold one invoice in eight.

| Hold above max times | Normal invoices held (1,069 history) | Padded invoices caught, 3 held-out seeds, of 40 |
|---|---|---|
| 1.5 (spec) | 0.6% | 26, 27, 27 |
| **1.3** | **2.0%** | **28, 32, 33** |
| 1.2 | 3.7% | not run end to end |
| 1.0 | 11.6% | not run end to end |

The gain is real and modest (about 2 to 6 more of 40, 1 on the main seed), and 8 to 14 padded invoices per 40 still pass. To revert, set the constant back to 1.5 and the test in `tests/test_interfaces.py`.

## Not changed

The hidden-text rule still quarantines a benign hidden preheader. Loosening it trades security for fewer false positives and is a decision for the risk owner.

## Run it

```
cd backend
python -m app.redteam.evaluate --estimate   # Claude calls and cost, spends nothing
python -m app.redteam.evaluate --dry-run    # no API calls, writes nothing to demo/
python -m app.redteam.evaluate              # live; or POST /api/redteam/run
```

The live run made 1,529 Claude calls for $3.19. A rerun of the same cases is served from the on-disk caches and costs nothing; its wall time is then not a measurement, so the file keeps the timing of the last run that made live calls (`details.timing_from`).
