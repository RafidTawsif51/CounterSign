# Auditor access (MCP)

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server, so a company official (the controller or an auditor) can connect their own Claude and ask what the payment agent did: what it paid, held or blocked, why, and whether any money went to an account nobody verified.

It cannot change anything. No tool approves, rejects, pays, calls, edits or resets. Code: `backend/app/mcp_server.py`. Tests: `backend/tests/test_mcp_server.py`.

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `get_system_status` | none | Which components are real, sandboxed or simulated (the System status page) |
| `list_payment_runs` | `limit` (20), `kind` | Runs, newest first, with paid, held and blocked counts. `kind` is `weekly run`, `attack`, `seeded history` or `red team` |
| `get_run_report` | `run_id` | The controller report stored for a finished run. It reads the stored report only and never writes one |
| `list_payments` | `status`, `vendor`, `run_id`, `limit` (50) | Payments with vendor, amount, status, destination last four, `destination_verified`, risk score, decision and hard rules, plus a `summary` over every matching payment (not only the rows returned): counts by status and `paid_to_unverified_destination` with its dollar total |
| `get_payment` | `payment_id` | One payment and every evidence record the Ask box can cite (each with an id) |
| `explain_payment` | `payment_id`, `question` | The Ask box's answer: plain text plus claims that cite evidence ids. Read-only, like the Ask box |
| `get_vendor` | `vendor_id`, `invoice_limit` (20) | The stored CRS result, bank account history with the trusted account, contacts and their source, recent invoices, verification calls |
| `get_audit_log` | `entity_id`, `limit` (50) | The append-only audit log for one id, newest first |
| `get_leaderboard` | `limit` (50) | Attack attempts, caught or missed, sandbox dollars moved |

`limit` is capped at 200 everywhere. `destination_verified` is true when the account was verified by a call or is the vendor's onboarding account (the same rule the payment guard uses).

## Safety

- **Read-only, enforced in code.** Every tool runs on a database session that raises on any insert, update or delete. The views the API builds with a side effect are rebuilt from read-only helpers: the payment detail and vendor history routes run a live CRS check and store it when a vendor has no stored result, so `get_payment` and `get_vendor` report the stored result only, or say there is none.
- **One write: its own call log.** Every tool call, refused calls included, appends one `audit_log` row: actor `mcp_reader`, entity `mcp_reader`, entity id the tool name, action `tool_call`, with the masked arguments, whether it succeeded and how long it took. These rows never appear in a payment's audit trail on the demo screens. A test runs every tool and fails if any statement other than that one insert reaches the database.
- **Masking.** The same masking as Ask: a phone number keeps its last four digits, any other long digit run (account and routing numbers) keeps its last four. No setting or key is ever returned.
- **Untrusted text is labeled.** Text from emails, invoices, attack submissions, audit details and call transcripts only ever appears inside a field named `untrusted_content`. Each tool that can return such text says in its description that it is untrusted data, never instructions, and so do the server's instructions.
- **Bearer token.** HTTP requests need `Authorization: Bearer <MCP_READ_TOKEN>`. Without it, or with the wrong one, the answer is 401. While `MCP_READ_TOKEN` is blank on the server, `/mcp` answers 503 for everyone.
- **Rate limit.** At most 60 tool calls per minute across all clients. Extra calls are refused with an error and logged.
- **Host check.** `/mcp` accepts requests addressed to localhost or to the host in `PUBLIC_BASE_URL` (DNS rebinding protection).

## Turn it on

In `.env` at the repo root:

```
MCP_READ_TOKEN=<a long random value>
```

Generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Restart uvicorn. The System status page then shows "Auditor access (MCP): read-only".

## Connect from Claude Code

### Over HTTP (the running backend)

```sh
claude mcp add --transport http countersign-auditor http://localhost:8000/mcp \
  --header "Authorization: Bearer $MCP_READ_TOKEN"
```

For a backend behind ngrok, use `https://<your-ngrok-host>/mcp` and make sure `PUBLIC_BASE_URL` is that same address. Check it with `claude mcp list` (it should show `countersign-auditor` as connected), then ask in Claude Code, for example:

- "What was held this week and why?"
- "Did any money go to an unverified account?"
- "Show me the audit log for pay_atk_bank_change."

`claude mcp add` stores the server in your local Claude Code settings for this project (`--scope local`, the default), not in the repo, so the token is not committed. Remove it with `claude mcp remove countersign-auditor`.

### Over stdio (on the machine with the database)

```sh
claude mcp add countersign-auditor -- /path/to/Countersign/backend/.venv/bin/python -m app.mcp_server
```

Run it from `backend/` (or set `DATABASE_URL`). stdio needs no token: whoever can start the process can already read the database file. The rate limit and the call log still apply.

## Check it by hand

```sh
curl -s http://localhost:8000/mcp -H "Authorization: Bearer $MCP_READ_TOKEN" \
  -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## What it does not do

- It does not stream: each request gets one JSON response (stateless Streamable HTTP).
- One token for everyone who has it. There are no per-person accounts yet, so the call log records the tool and arguments, not who asked.
- `explain_payment` calls Claude when `MOCK_CLAUDE=false`, so it spends a little API money per new question, like the Ask box.
