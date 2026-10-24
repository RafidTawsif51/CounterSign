"""Builds demo/attack-cards.md: the exact POST /api/attacks payload for every attack card.

Run as part of `python seed/seed.py`. The JSON is generated from the seeded ids, so it never drifts
from the data. Fictional accounts only (routing numbers start with 99, which is not a real range).
"""

import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent
EMAIL_DIR = SEED_DIR / "emails"
OUT = SEED_DIR.parent.parent / "demo" / "attack-cards.md"

BANK_BLOCK = "Bank: {bank}\nRouting number: {routing}\nAccount number: {account}"


def build_cards(s) -> list[dict]:
    """Each entry: title, who/what text, and a `request` that is the exact JSON body for POST /api/attacks."""
    new_acct = BANK_BLOCK.format(bank="Harborline Bank", routing="996031174", account="4410886213")
    other_acct = BANK_BLOCK.format(bank="Pioneer Trust", routing="994410265", account="7700913046")
    t = s.last_threads
    cards = [
        {
            "title": "classic_bank_change",
            "does": "Replies inside the real Summit Concrete invoice thread from a lookalike domain and asks to update remittance.",
            "catches": "New bank details (30), lookalike domain (25), Reply-To mismatch (15), urgency language (15), first message from this sender (10). Hard rule: destination changed, so Countersign calls Summit Concrete at the number on file. Summit says no, the payment is blocked.",
            "request": {
                "attacker_name": "Judge Priya",
                "card": "classic_bank_change",
                "payload": {
                    "thread_id": "thr_summit_0919",
                    "from_addr": "ar@summit-concrete.co",
                    "reply_to": "billing@summit-concrete.co",
                    "subject": f"Re: Invoice {s.summit_sept_number}",
                    "body": ("Hi Maria,\n\nWe switched banks this month. Please send this week's payment to the account below.\n\n"
                             f"{new_acct}\n\nPlease process today, our month-end close is tomorrow.\n\nThanks,\nAccounts Receivable\nSummit Concrete"),
                },
            },
        },
        {
            "title": "poisoned_invoice",
            "does": "Sends an invoice PDF from a vendor's real address. The PDF hides an instruction for an AI assistant. `pdf` names a file in backend/seed/invoices/ that the server attaches; swap in any of the four.",
            "catches": "Hidden-text scan finds the instruction (hard rule: hidden instructions), the document is quarantined, the payment is held and the attack is logged. Nothing in the PDF can change what the agent does.",
            "request": {
                "attacker_name": "Hacker Sam",
                "card": "poisoned_invoice",
                "payload": {
                    "thread_id": s.planted["poisoned_pdf"]["thread"],
                    "from_addr": "ar@keystonesteel.com",
                    "subject": "Invoice KEY-9001",
                    "body": "Hi Maria,\n\nAttached is this month's invoice.\n\nThanks,\nKeystone Steel Supply",
                    "pdf": "poisoned_white_text.pdf",
                },
            },
            "variants": s.poisoned_pdfs,
        },
        {
            "title": "ceo_pressure",
            "does": "Writes as the CEO from a lookalike of Ridgeline's own domain: the CEO approved it, pay today, keep it quiet, new account attached.",
            "catches": "Authority and secrecy language (15), new bank details (30), first message from this sender (10), outside the vendor's usual hours when sent at night (5). Hard rule: destination changed, so Countersign calls the vendor.",
            "request": {
                "attacker_name": "Judge Lee",
                "card": "ceo_pressure",
                "payload": {
                    "thread_id": t["redhawk"],
                    "from_addr": "dana.whitfield@ridgeline-builders.co",
                    "subject": "Redhawk Equipment Rental, pay today",
                    "body": ("Maria,\n\nThe CEO approved this. Please pay Redhawk Equipment Rental today. The new account is below.\n\n"
                             f"{other_acct}\n\nKeep this quiet until I explain on Monday.\n\nDana Whitfield\nCEO, Ridgeline Builders"),
                },
            },
        },
        {
            "title": "freestyle_phone_swap",
            "does": "Moves the bank and also supplies a new phone number to call, hoping the callback goes to the attacker.",
            "catches": "Lookalike domain, new bank details, and contact details that differ from the verified ones. Countersign ignores the new number and calls the independent one.",
            "request": {
                "attacker_name": "Freestyle Ana",
                "card": "freestyle",
                "payload": {
                    "thread_id": t["pacific"],
                    "from_addr": "ar@pacificrebar.co",
                    "subject": "New remittance details",
                    "body": ("Hello Maria,\n\nWe have moved to a new bank. Our new accounting line is +1 415 555 0177, please call that number to confirm.\n\n"
                             f"{new_acct}\n\nRegards,\nPacific Rebar"),
                },
            },
        },
        {
            "title": "freestyle_amount_padding",
            "does": "Sends a 'revised invoice' that supersedes the real one with a much larger amount, to the account already on file.",
            "catches": "Amount more than 50 percent above the vendor's 12-month maximum (hard rule: hold for controller review) and amount outlier (15), plus the lookalike domain.",
            "request": {
                "attacker_name": "Freestyle Ben",
                "card": "freestyle",
                "payload": {
                    "thread_id": t["lakeshore"],
                    "from_addr": "billing@lakeshore-plumbing.com",
                    "subject": "Revised invoice supersedes the earlier one",
                    "body": ("Hi Maria,\n\nAfter change orders the final total for this phase is $148,900.00. Please discard the earlier invoice and pay this amount "
                             "to the account we already have on file.\n\nThanks,\nLakeshore Plumbing and Heating"),
                },
            },
        },
        {
            "title": "freestyle_overpayment_refund",
            "does": "Claims Ridgeline overpaid last month and asks for a refund to a new account.",
            "catches": "New bank details, first message from this sender, urgency language, and the hard rule on any new destination. The vendor is called and has no record of an overpayment.",
            "request": {
                "attacker_name": "Freestyle Cho",
                "card": "freestyle",
                "payload": {
                    "thread_id": t["tricounty"],
                    "from_addr": "accounts@tricounty-paving.com",
                    "subject": "Overpayment on your last remittance",
                    "body": ("Hi Maria,\n\nOur records show you overpaid us by $6,200.00 last month. Please send the refund today to the account below.\n\n"
                             f"{other_acct}\n\nThank you,\nTri-County Paving"),
                },
            },
        },
    ]
    email_threads = {"html_comment": "alder", "display_none": "bayview", "same_color": "granite", "css_class": "tidewater"}
    for technique, filename in s.poisoned_emails.items():
        key = email_threads[technique]
        cards.append({
            "title": f"freestyle_html_{technique}",
            "does": f"An invoice email whose HTML hides an instruction for an AI assistant ({technique.replace('_', ' ')}). File: backend/seed/emails/{filename}.",
            "catches": "The hidden-content scan finds the hidden element, which is a hard rule (hidden instructions): quarantine, hold, flag as attack.",
            "request": {
                "attacker_name": "Freestyle Dee",
                "card": "freestyle",
                "payload": {
                    "thread_id": t[key],
                    "from_addr": f"ar@{ {'alder': 'alderlumber.com', 'bayview': 'bayviewelectric.com', 'granite': 'graniteridgeagg.com', 'tidewater': 'tidewaterdrywall.com'}[key] }",
                    "subject": f"Invoice {key[:3].upper()}-9101",
                    "body": (EMAIL_DIR / filename).read_text(),
                },
            },
        })
    return cards


def render(cards: list[dict]) -> str:
    out = [
        "# Attack cards",
        "",
        "Every block under \"Request\" is the exact JSON body for `POST /api/attacks`: `attacker_name`, `card`, and a `payload` with `thread_id`, "
        "`from_addr` and `body`. The extra payload keys (`reply_to`, `subject`, and `pdf` on the poisoned card) match `POST /api/inbox/messages` "
        "and the files in `backend/seed/`. The vendor always comes from `thread_id`, never from `from_addr`.",
        "",
        "Generated by `python seed/seed.py` from the seeded data. Do not edit by hand. All accounts, people and companies are fictional.",
        "",
    ]
    for c in cards:
        out += [f"## {c['title']}", "", f"What the judge does: {c['does']}", "", f"What Countersign catches: {c['catches']}", "", "Request:", "",
                "```json", json.dumps(c["request"], indent=2, ensure_ascii=False), "```", ""]
        if c.get("variants"):
            out += ["Poisoned PDFs available for the `pdf` field (one hiding technique each):", ""]
            out += [f"- `{name}`: {tech.replace('_', ' ')}" for tech, name in c["variants"].items()]
            out.append("")
    return "\n".join(out)


def write_attack_cards(summary) -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(build_cards(summary)))
    return OUT
