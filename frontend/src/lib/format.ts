// Display formatting for AP data. Render money, accounts and scores inside a `.figure` element (Plex Mono, tabular).

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const EMPTY = "–";
const MASK = "••••";
const NBSP = " ";

/** `$48,250.00`. Always two decimals. */
export function formatUSD(amount: number | null | undefined): string {
  if (amount == null || !Number.isFinite(amount)) return EMPTY;
  return usd.format(amount);
}

/**
 * `•••• 7781`. Only ever the last four digits, whatever is passed in (last4, a full number, or a formatted string).
 * Never add a way to show more: the call agent and the UI share this rule.
 */
export function formatAccount(account: string | null | undefined): string {
  const digits = (account ?? "").replace(/\D/g, "");
  if (digits.length < 4) return MASK;
  return `${MASK}${NBSP}${digits.slice(-4)}`;
}

const rtf = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });
const shortDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const shortDateYear = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

/** `just now`, `4 minutes ago`, `yesterday`, then `Oct 22` (with year if not this year). */
export function formatRelativeTime(value: string | Date | null | undefined, now: Date = new Date()): string {
  if (value == null) return EMPTY;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;

  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86_400) return rtf.format(Math.round(seconds / 3600), "hour");
  if (abs < 7 * 86_400) return rtf.format(Math.round(seconds / 86_400), "day");
  return (date.getFullYear() === now.getFullYear() ? shortDate : shortDateYear).format(date);
}

/** Risk score 0 to 100 as `85`, or `85 / 100` with `outOf`. Clamped and rounded. */
export function formatScore(score: number | null | undefined, opts: { outOf?: boolean } = {}): string {
  if (score == null || !Number.isFinite(score)) return EMPTY;
  const n = Math.round(Math.min(100, Math.max(0, score)));
  return opts.outOf ? `${n} / 100` : String(n);
}

/** `+14155550100` as `+1 415 555 0100`. Other formats pass through unchanged. */
export function formatPhone(phone: string | null | undefined): string {
  if (!phone) return EMPTY;
  const m = phone.match(/^\+1(\d{3})(\d{3})(\d{4})$/);
  return m ? `+1 ${m[1]} ${m[2]} ${m[3]}` : phone;
}

const clock = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
const dayYear = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

/** `16:04:12`, local time. For audit trails and transcripts. */
export function formatClock(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? EMPTY : clock.format(d);
}

/** `Mar 12, 2026`. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const d = new Date(value.length === 10 ? `${value}T12:00:00Z` : value);
  return Number.isNaN(d.getTime()) ? EMPTY : dayYear.format(d);
}

/**
 * `+14155550142` as `(415) •••-0142`. For screens others can see (the call panel on a demo laptop): the area code says
 * where, the last four say which, the rest stays masked.
 */
export function formatPhoneMasked(phone: string | null | undefined): string {
  if (!phone) return EMPTY;
  const m = phone.match(/^\+1(\d{3})\d{3}(\d{4})$/);
  if (m) return `(${m[1]})${NBSP}${MASK.slice(0, 3)}-${m[2]}`;
  // Already masked by the API (`+1***0142`): only the last four are known.
  const masked = phone.match(/^\+\d\*+(\d{4})$/);
  return masked ? `(${MASK.slice(0, 3)})${NBSP}${MASK.slice(0, 3)}-${masked[1]}` : formatAccount(phone);
}

const monthYear = new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric" });

/** `Feb 2025`. */
export function formatMonthYear(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? EMPTY : monthYear.format(d);
}

/** Seconds as `0:07` or `1:00`. For call timers. */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
