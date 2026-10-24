// Inbox helpers: header checks a reader can verify by eye, safe text for message bodies, and which threads the run
// caught an attack in. Message text is untrusted: everything here treats it as data.

import { diffDomains, domainOf, type DiffPart } from "@/lib/domain-diff";
import type { InboxMessage, PaymentDetail } from "@/lib/types";

/** Ridgeline's own domain. Maria replies from it; a near miss of it (the "CEO" email) is a lookalike too. */
export const COMPANY_DOMAIN = "ridgelinebuilders.com";

export interface HeaderFlag {
  field: "from" | "reply_to";
  reason: string;
  /** For a lookalike: the address's domain and the real one, split into matching and differing runs. */
  diff?: { fake: DiffPart[]; real: DiffPart[]; realDomain: string };
}

/** `summit-concrete.co` and `summitconcrete.com` both reduce to `summitconcrete`. */
function core(domain: string) {
  const parts = domain.split(".");
  return (parts.length > 1 ? parts.slice(0, -1) : parts).join("").replace(/-/g, "");
}

function distance(a: string, b: string) {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++) d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}

/** The known domain this one imitates: same name once hyphens and the TLD are ignored, or within 2 edits. */
export function lookalikeOf(domain: string, known: string[]): string | null {
  const d = domain.toLowerCase();
  if (known.includes(d)) return null;
  return known.find((k) => core(k) === core(d) || distance(k, d) <= 2) ?? null;
}

/** Flags on one message's headers, against the thread vendor's known domain and Ridgeline's own. */
export function headerFlags(msg: Pick<InboxMessage, "from_addr" | "reply_to">, vendorDomain: string | null): HeaderFlag[] {
  const known = [vendorDomain, COMPANY_DOMAIN].filter(Boolean) as string[];
  const flags: HeaderFlag[] = [];
  const check = (field: HeaderFlag["field"], address: string) => {
    const domain = domainOf(address);
    const real = lookalikeOf(domain, known);
    if (!real) return;
    const { fake, real: realParts } = diffDomains(real, domain);
    flags.push({ field, reason: `lookalike of ${real}`, diff: { fake, real: realParts, realDomain: real } });
  };
  check("from", msg.from_addr);
  if (msg.reply_to && msg.reply_to.toLowerCase() !== msg.from_addr.toLowerCase()) {
    const other = domainOf(msg.reply_to) !== domainOf(msg.from_addr);
    flags.push({ field: "reply_to", reason: other ? "replies go to a different domain" : "Reply-To differs from sender" });
    check("reply_to", msg.reply_to);
  }
  return flags;
}

/** The visible text of a body. HTML is parsed in an inert document and only its text is kept: nothing renders or runs. */
export function bodyText(msg: Pick<InboxMessage, "body" | "is_html">): string {
  if (!msg.is_html) return msg.body;
  const doc = new DOMParser().parseFromString(msg.body, "text/html");
  doc.querySelectorAll("script, style").forEach((n) => n.remove());
  return (doc.body.textContent ?? "").replace(/\n{3,}/g, "\n\n").trim();
}

export interface Detection {
  paymentId: string;
  messageId: string | null;
  status: PaymentDetail["payment"]["status"];
  /** Short, evidence-first. */
  reason: string;
}

/** What the run caught on this payment, or null if nothing did. Built from the payment record, never the seed's is_attack. */
export function detectionFor(d: PaymentDetail): Detection | null {
  const call = d.calls.at(-1);
  const reason = d.findings.length
    ? "Hidden instructions in the invoice"
    : call?.outcome === "denied"
      ? "Vendor denied the bank change on the call"
      : call?.outcome === "unclear"
        ? "New bank account, call did not confirm"
        : d.risk?.hard_rules_fired.includes("destination_changed")
          ? "New bank account, verifying by phone"
          : null;
  if (!reason || (d.payment.status !== "held" && d.payment.status !== "blocked")) return null;
  return { paymentId: d.payment.id, messageId: d.message?.id ?? null, status: d.payment.status, reason };
}
