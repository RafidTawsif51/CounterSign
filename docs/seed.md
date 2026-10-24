# Seed data

`backend/seed/seed.py`. Run `cd backend && python seed/seed.py`, or call `seed_database(session)` (demo reset does). It wipes every table and rebuilds the same world: fixed random seed (`SEED`), fixed clock (`ANCHOR`, Thursday 2026-10-22 16:00 UTC), sequential ids. About 0.2 seconds. `seed_database(session, keep_attacks=True)` keeps the attacks table (leaderboard) and wipes the rest. Demo PDFs are written byte-identical, so the extraction cache keeps hitting.

Everything is fictional. Phones are `+1415555xxxx` (the 555-01xx fiction range) except Summit Concrete, which gets `DEMO_VENDOR_PHONE` when set. Routing numbers start with 99 (not a real range). Vendor domains are invented `.com` names; a few may exist in the real world, and nothing is ever sent to them.

## The world

| Item | Value |
|---|---|
| Company | Ridgeline Builders (`ridgelinebuilders.com`), CEO Dana Whitfield, AP clerk Maria, controller Dev |
| Vendors | 30, ids like `ven_summit`: 12 monthly suppliers, 12 progress-billing subcontractors, 6 equipment and site rentals |
| History | about 1,160 paid invoices, 50 weekly Thursday runs (`run_2025w44` ... `run_2026w42`), one payment per invoice, `nes_seed_NNNN` transfer ids |
| Seasonality | busier in spring and summer: more invoices per week and larger amounts (factor 0.55 in December, 1.4 in May and June) |
| Bank history | every vendor has one current account (`valid_to` null). 4 had a legitimate change, each with a confirmed `verification_calls` row and `verified_by_call_id` set: `lakeshore`, `redwood`, `stonecraft`, `skyline`. Onboarding accounts have no call (verified at onboarding) |
| Contacts | each vendor: one `on_file` phone plus one `website` or `listing` contact with `source_url` |
| Send times | each vendor emails inside one daily UTC window (4 to 6 hours), so `outside_usual_hours` works |

## This week (Thursday 2026-10-22 run)

40 open invoices (no payment row yet), PDFs in `backend/seed/invoices/<invoice_id>.pdf`.

37 clean (`SeedSummary.clean_invoice_ids`): every vendor has a current account that matches the invoice remittance, a known sender address, a usual send hour, and a typical amount. A test runs `risk.assess` on all of them: score 0, `auto_pay`, no hard rules, so no extra calls.

3 planted attacks (ids in `seed.PLANTED`):

| Card | Ids | What the pipeline sees |
|---|---|---|
| Classic bank change | `inv_atk_bank_change`, `msg_atk_bank_change`, thread `thr_summit_0919` | Reply in the real Sept 19 Summit thread from `ar@summit-concrete.co`, Reply-To `billing@summit-concrete.co`, "please process today", new account ending 7781 vs verified 2204. Score 95, `hold_and_verify` |
| AI hijack | `inv_atk_poisoned_pdf`, `msg_atk_poisoned_pdf` | Keystone Steel invoice from the vendor's real address, normal amount and account, white text at the bottom asking an AI to reroute and approve. Score 0 but hard rule `hidden_instructions`, `hold` |
| CEO pressure | `inv_atk_ceo_pressure`, `msg_atk_ceo_pressure` | Message in Northside Rentals' latest thread from `dana.whitfield@ridgeline-builders.co`: "the CEO approved this, pay today, keep it quiet", new account ending 3046, sent 06:14 UTC. Score 60, `hold_and_verify` |

Demo run result (mocks on): 37 paid, 1 held, 2 blocked. The verification mock denies the Summit call and the poisoned PDF is quarantined; the CEO-pressure call is scripted to come back `unclear` (`verify.SEEDED_OUTCOMES`, matched only by the payment id `pay_atk_ceo_pressure`), so that payment stays held for the controller. A judge's live attack gets a new payment id and a denied call. `verify.MOCK_OUTCOMES` overrides it.

## Lookalike domains

`seed.LOOKALIKES` and `SeedSummary.lookalikes`: 10 pairs for attack generation, each within edit distance 2 of the real domain.

| Vendor | Real | Lookalike | Technique |
|---|---|---|---|
| summit | summitconcrete.com | summit-concrete.co | hyphen + tld |
| keystone | keystonesteel.com | keystone-steel.com | hyphen |
| alder | alderlumber.com | alderlurnber.com | rn for m |
| bayview | bayviewelectric.com | bayviewe1ectric.com | 1 for l |
| granite | graniteridgeagg.com | graniteridgeagg.co | tld |
| pacific | pacificrebar.com | pacificrebar.co | tld |
| northgate | northgateelectric.com | northgateelectrlc.com | l for i |
| lakeshore | lakeshoreplumbing.com | lakeshore-plumbing.com | hyphen |
| northside | northsiderentals.com | n0rthsiderentals.com | 0 for o |
| skyline | skylinecrane.com | skylinecrane.co | tld |

## Notes for the rest of the build

- Invoice rows for this week already carry `number`, `amount_usd`, `due_date`, `remittance_json` and `pdf_path`; `extracted_json` is null. The mock extractor reproduces the same values from the PDFs (tested), so the payment run can extract or skip.
- `tests/helpers.py::build_context` shows how to build a `RiskContext` from these rows.
- Full routing and account numbers exist only inside the generated PDFs. The database holds the hash and last 4.

## Generated documents

`python seed/seed.py` writes 134 PDFs to `backend/seed/invoices/` (gitignored, byte-identical every run), 3 HTML emails to `backend/seed/emails/`, and `demo/attack-cards.md`.

| Files | What |
|---|---|
| `inv_NNNN.pdf`, `inv_atk_*.pdf` | This week's 40 open invoices |
| `inv_NNNN.pdf` (90) | Historical samples: each vendor's last three paid invoices, in that vendor's layout. They have `invoices.pdf_path` set; the extraction tests and layout fingerprints use them |
| `poisoned_white_text.pdf`, `poisoned_tiny_font.pdf`, `poisoned_off_page.pdf`, `poisoned_zero_width.pdf` | Four poisoned invoices on Alder, Bayview, Granite and Tidewater layouts, one hiding technique each. The hidden text tells an AI assistant to update remittance to a new account and approve |
| `emails/poisoned_html_comment.html`, `poisoned_display_none.html`, `poisoned_same_color.html` | Three poisoned HTML emails |

Layouts: `seed/invoice_pdf.py::layout_for(vendor_key)` gives each vendor its own fonts, logo style, label wording, table column order and footer. Forged invoices (bank change, CEO pressure) use a layout no vendor uses; the planted poisoned invoice copies Keystone's real layout. `app/services/layout.py::fingerprint(pdf)` hashes the structure (ignores amounts, hidden text and zero-width characters), and `layout_changed(pdf, past_fingerprints)` feeds `RiskContext.layout_changed`.

Zero-width technique: the instruction is encoded as zero-width characters (U+200B = 0, U+200C = 1, U+200D = byte boundary) spliced into the footer sentence. The scanner decodes them. A language model will probably not read bit-encoded text, so this variant tests detection more than a realistic attack.

Attack cards: `demo/attack-cards.md` holds the exact `POST /api/attacks` JSON for `classic_bank_change`, `poisoned_invoice`, `ceo_pressure`, three freestyle cards and the three poisoned HTML emails. Extra payload keys beyond the spec example: `reply_to`, `subject`, and `pdf` (the name of a file in `backend/seed/invoices/` that the server attaches). The `/api/attacks` handler must support them.

## Threads and past decisions (`seed/history.py`)

Both use their own random streams (seed + 11, seed + 13), so this week's 40 invoices, their messages and PDFs are byte-for-byte what they were (a test pins the digest).

- Threads: one thread per historical invoice, with replies. 774 threads have 2 messages (Maria confirms the payment with the Nessie transfer id), 222 have 3 (Maria acknowledges first), 163 have 4: 81 late-payment questions (the vendor asks, Maria answers, then the paid confirmation), 78 corrected invoices (the first email shows a wrong total, the vendor corrects it) and the 4 bank-change threads (vendor, Maria says she will call, "Confirmed by phone", paid). This week's 37 clean threads and the Keystone thread are single messages. Maria writes from `maria@ridgelinebuilders.com`; the vendor of a reply comes from the thread.
- Past decisions: all 1,159 past payments have a risk assessment (`model_version` `seed-history-1`, evidence ids `evd_hNNNNn`) and audit rows (risk_assessed, paid). A signal appears only when it is true in the data (an amount over 2 standard deviations).
- Five holds cleared by the controller: Greenfield, Clearline, Brightcoat, Evergreen and Ironwood were onboarded inside the window, so their first payment fired `new_vendor` and went to controller review. Audit chain: risk_assessed, held, approved (actor human, "Dev (controller)"), paid. Vendors onboarded before the window have earlier payments that are not part of the seed.
- The four legitimate bank changes (Lakeshore, Redwood, Stonecraft, Skyline): assessment `hold_and_verify` with `bank_details_changed`, then audit rows held, identity_check, verification_call (the confirmed call id), bank_account_verified, paid. `/ask` can follow `vendor_bank_accounts.verified_by_call_id` to the call and its transcript.

## Edge cases (`seed/edge_cases.py`)

Not part of `seed_database`. `edge_cases.add_edge_cases(session)` adds four open invoices, each built to fire exactly one hard rule:

| Case | Rule | Ids |
|---|---|---|
| New vendor, 12 days old, first payment | `new_vendor` | `ven_edge_newleaf`, `inv_edge_newleaf` |
| Invoice 1.6x the vendor's 12-month maximum (Alder Lumber) | `amount_over_max` | `inv_edge_overmax` |
| Email with a phone number not on file (Cascade Hardware) | `contacts_differ` | `inv_edge_contacts` |
| True one-off rental: old vendor, one invoice, never paid | `new_vendor` (first payment) | `ven_edge_quickhaul`, `inv_edge_oneoff` |

Run through the payment run together with the seeded week, all four are held and the original 40 still end 37 paid, 1 held, 2 blocked. The two new vendors have PDFs; the two on existing vendors do not, because the seed keeps only hashes and last 4 of account numbers.
