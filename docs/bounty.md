# Rob Countersign bounty inbox

Source: `backend/app/services/bounty.py`. Provider: Postmark inbound email.

## Setup

1. In Postmark, set the inbound webhook URL of the inbound stream to `https://anything:<BOUNTY_WEBHOOK_SECRET>@<backend host>/api/bounty/inbound`. Postmark does not sign inbound mail; it sends the URL's credentials as HTTP Basic auth, and the password is the secret. (`x-webhook-secret: <secret>` also works, for a forwarder or curl.)
2. Set `BOUNTY_WEBHOOK_SECRET` (the inbox is closed with a 503 while it is blank). Set `BOUNTY_MODERATOR_TOKEN` to protect the queue and moderation routes with the header `x-moderator-token`; blank leaves them open (local dev only).
3. Do not advertise the address until the organizers have said yes (#ask-directors).

## `POST /api/bounty/inbound`

| Rule | Behavior |
|---|---|
| No or wrong secret | 401, nothing read, nothing stored |
| Rate limit | 5 accepted per sender per hour, else 429 with `Retry-After`. `+tags` and Gmail dots count as the same sender |
| Size | request at most 8 MB (413); email text at most 50 KB (413) |
| Attachments | PDF only, judged by content type and the `%PDF-` bytes (415); each at most 5 MB, at most 3 (413). One bad file rejects the email |
| Redelivery | Postmark retries; a `MessageID` already accepted answers `200 {"duplicate": true}` and creates nothing |

An accepted email becomes a message in a **new thread** (the sender never joins a vendor's thread), an invoice, an `attacks` row (`source: bounty_email`, `moderation_status: pending`) and a mini-run through the same extraction, injection scan, risk assessment, verification call and payment steps as every other invoice. A vendor named in the email is only a hint and is stored as `vendor_claim: {verified: false}`. Money can only go to the vendor's verified account (Nessie sandbox), a changed account triggers a call to a number from `ALLOWED_CALL_NUMBERS`, and nothing in the email can change either.

Response: `{attack_id, message_id, invoice_id, run_id, queued, ...}`.

## Leaderboard and moderation

- Until a moderator approves it, the row on `GET /api/attacks/leaderboard` has only the masked handle, the card, the result and the time. Outcome, reasons, amounts and the attack text appear after approval. The sender's address is never shown in full.
- `GET /api/bounty/queue?status=pending|approved|hidden|all` lists submissions oldest first, with the attack text for the moderator (untrusted: render as text).
- `POST /api/bounty/{attack_id}/moderate` with `{action: "approve" | "hide", moderator}`. Audited as a human action; emits `attack.logged` with the new `moderation_status`.
