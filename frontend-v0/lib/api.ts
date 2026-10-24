export const API_BASE = '/api'

/** Flip to false once the backend serves /api/payment-runs. */
const USE_MOCK = true

export const DEMO_RUN_ID = 'run_2026_10_29_thu'

// ---------- Types ----------

export interface Payment {
  id: string
  payee: string
  amount_usd: number
  invoice_number: string
  check_number: number
}

export interface PaymentRun {
  id: string
  company: string
  run_date: string
  funding_account_last4: string
  payments: Payment[]
}

export type RiskDecision = 'pay' | 'hold' | 'block'

export interface RunStartedData {
  run_id: string
  invoice_count: number
}
export interface RiskScoredData {
  payment_id: string
  score: number
  decision: RiskDecision
  top_signals: string[]
}
export interface PaymentPaidData {
  payment_id: string
  nessie_transfer_id: string
}
export interface PaymentHeldData {
  payment_id: string
  reasons: string[]
}
export interface PaymentBlockedData {
  payment_id: string
  reason: string
}
export interface RunCompletedData {
  run_id: string
  paid: number
  held: number
  blocked: number
  total_usd: number
}

/** Where the dialed number was found. Email-supplied numbers are never a valid source. */
export type ContactSourceKind = 'vendor_website' | 'vendor_master_file' | 'signed_contract'

export interface ContactSource {
  kind: ContactSourceKind
  phone: string
  /** e.g. the page the number was read from */
  detail?: string
}

export type CallSpeaker = 'countersign' | 'vendor'
export type CallOutcome = 'confirmed' | 'denied'

export interface CallStartedData {
  payment_id: string
  contact_source: ContactSource
}
export interface CallTranscriptData {
  payment_id: string
  speaker: CallSpeaker
  text: string
}
export interface CallOutcomeData {
  payment_id: string
  outcome: CallOutcome
}

export type RunEvent =
  | { type: 'run.started'; data: RunStartedData }
  | { type: 'risk.scored'; data: RiskScoredData }
  | { type: 'call.started'; data: CallStartedData }
  | { type: 'call.transcript'; data: CallTranscriptData }
  | { type: 'call.outcome'; data: CallOutcomeData }
  | { type: 'payment.paid'; data: PaymentPaidData }
  | { type: 'payment.held'; data: PaymentHeldData }
  | { type: 'payment.blocked'; data: PaymentBlockedData }
  | { type: 'run.completed'; data: RunCompletedData }

export type RunEventType = RunEvent['type']

export const RUN_EVENT_TYPES: RunEventType[] = [
  'run.started',
  'risk.scored',
  'call.started',
  'call.transcript',
  'call.outcome',
  'payment.paid',
  'payment.held',
  'payment.blocked',
  'run.completed',
]

// ---------- Public functions ----------

export async function getPaymentRun(runId: string): Promise<PaymentRun> {
  if (USE_MOCK) {
    await wait(250)
    return { ...MOCK_RUN, id: runId }
  }
  const res = await fetch(`${API_BASE}/payment-runs/${encodeURIComponent(runId)}`)
  if (!res.ok) throw new Error(`Couldn't load payment run (${res.status})`)
  return res.json()
}

export async function startPaymentRun(runId: string): Promise<void> {
  if (USE_MOCK) return
  const res = await fetch(`${API_BASE}/payment-runs/${encodeURIComponent(runId)}/start`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Couldn't start payment run (${res.status})`)
}

/**
 * Streams run events. Returns an unsubscribe function.
 * Backend contract: GET {API_BASE}/payment-runs/{id}/events as Server-Sent Events,
 * where each SSE `event:` name is a RunEventType and `data:` is its JSON payload.
 */
export function subscribeToRun(runId: string, onEvent: (event: RunEvent) => void): () => void {
  if (USE_MOCK) return replayMockRun(runId, onEvent)

  const source = new EventSource(`${API_BASE}/payment-runs/${encodeURIComponent(runId)}/events`)
  for (const type of RUN_EVENT_TYPES) {
    source.addEventListener(type, (message) => {
      const data = JSON.parse((message as MessageEvent<string>).data)
      onEvent({ type, data } as RunEvent)
      if (type === 'run.completed') source.close()
    })
  }
  return () => source.close()
}

// ---------- Inbox & attacks ----------

export type AttackCardId = 'bank_change' | 'poisoned_invoice' | 'ceo_pressure' | 'freestyle'

export interface InboxAttachment {
  filename: string
  size_kb: number
}

export interface InboxMessage {
  id: string
  from_name: string
  from_addr: string
  to_name: string
  to_addr: string
  sent_at: string
  body: string
  attachments: InboxAttachment[]
}

export interface InboxThread {
  id: string
  subject: string
  vendor: string
  labels: string[]
  messages: InboxMessage[]
}

export interface AttackRequest {
  attacker_name: string
  card: AttackCardId
  payload: { thread_id: string; from_addr: string; body: string }
}

export interface AttackResponse {
  attack_id: string
  message_id: string
  run_id: string
}

export const SUMMIT_THREAD_ID = 'thr_summit_inv_20534'

export async function getInboxThreads(): Promise<InboxThread[]> {
  if (USE_MOCK) {
    await wait(300)
    return MOCK_THREADS
  }
  const res = await fetch(`${API_BASE}/inbox/threads`)
  if (!res.ok) throw new Error(`Couldn't load the inbox (${res.status})`)
  return res.json()
}

export async function sendAttack(request: AttackRequest): Promise<AttackResponse> {
  if (USE_MOCK) {
    await wait(700)
    const suffix = Math.random().toString(36).slice(2, 8)
    const response: AttackResponse = {
      attack_id: `atk_${suffix}`,
      message_id: `msg_${suffix}`,
      run_id: `run_atk_${suffix}`,
    }
    mockAttackCardByRun.set(response.run_id, request.card)
    return response
  }
  const res = await fetch(`${API_BASE}/attacks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error(`Couldn't send the attack (${res.status})`)
  return res.json()
}

// ---------- Payment detail, ask, review ----------

export interface RiskSignal {
  name: string
  /** 0 to 30 points toward the 100-point risk score. */
  weight: number
  detail: string
  evidence_id: string
}

export interface RiskAssessment {
  payment_id: string
  /** 0 to 100 */
  score: number
  decision: RiskDecision
  hard_rules_fired: string[]
  signals: RiskSignal[]
}

export interface VendorHistoryPoint {
  /** YYYY-MM */
  month: string
  amount_usd: number
  invoice_number: string
  is_current: boolean
}

export interface VendorHistory {
  vendor_since: string
  average_usd: number
  points: VendorHistoryPoint[]
}

export type BankVerificationMethod = 'phone_callback' | 'signed_form' | 'micro_deposit' | 'unverified'

export interface BankAccount {
  id: string
  bank_name: string
  last4: string
  status: 'active' | 'retired' | 'requested'
  added_at: string
  retired_at?: string
  /** How a requested change reached Ridgeline. */
  requested_via?: string
  verification: { method: BankVerificationMethod; verified_at?: string; detail: string }
}

export interface CallRecord {
  id: string
  started_at: string
  contact_source: ContactSource
  outcome: CallOutcome
  transcript: Array<{ speaker: CallSpeaker; text: string }>
}

export interface PaymentDetail {
  risk_assessment: RiskAssessment
  vendor_history: VendorHistory
  bank_accounts: BankAccount[]
  calls: CallRecord[]
}

export interface AskResponse {
  answer: string
  evidence: string[]
}

export type ReviewDecision = 'approved' | 'rejected'

export interface ReviewResponse {
  payment_id: string
  decision: ReviewDecision
  reviewed_at: string
}

/** `runId` only steers the mock, so attack runs explain their own attack. The real API keys on payment id. */
export async function getPaymentDetail(paymentId: string, runId?: string): Promise<PaymentDetail> {
  if (USE_MOCK) {
    await wait(350)
    return mockPaymentDetail(paymentId, runId)
  }
  const res = await fetch(`${API_BASE}/payments/${encodeURIComponent(paymentId)}`)
  if (!res.ok) throw new Error(`Couldn't load payment details (${res.status})`)
  return res.json()
}

export async function askAboutPayment(paymentId: string, question: string, runId?: string): Promise<AskResponse> {
  if (USE_MOCK) {
    await wait(1100)
    return mockAnswer(mockPaymentDetail(paymentId, runId), paymentId)
  }
  const res = await fetch(`${API_BASE}/payments/${encodeURIComponent(paymentId)}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) throw new Error(`Couldn't get an answer (${res.status})`)
  return res.json()
}

export async function reviewPayment(
  paymentId: string,
  decision: ReviewDecision,
  reason: string,
): Promise<ReviewResponse> {
  if (USE_MOCK) {
    await wait(600)
    return { payment_id: paymentId, decision, reviewed_at: new Date().toISOString() }
  }
  const action = decision === 'approved' ? 'approve' : 'reject'
  const res = await fetch(`${API_BASE}/payments/${encodeURIComponent(paymentId)}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!res.ok) throw new Error(`Couldn't ${action} the payment (${res.status})`)
  return res.json()
}

// ---------- Mock data ----------

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

const VENDORS: Array<[payee: string, amount: number]> = [
  ['Granite Peak Lumber', 18_432.6],
  ['Ironclad Steel Fabricators', 42_915.0],
  ['Blue Ridge Electrical', 9_870.25],
  ['Cascade Plumbing Supply', 6_214.8],
  ['Pioneer Roofing Co.', 23_560.0],
  ['Redline Equipment Rental', 4_380.0],
  ['Northfield Drywall', 12_480.5],
  ['Harbor Glass & Glazing', 15_725.4],
  ['Keystone HVAC', 31_200.0],
  ['Timberline Excavating', 27_845.75],
  ['Atlas Rebar', 8_912.3],
  ['Meridian Survey Group', 3_450.0],
  ['ClearPath Waste Hauling', 1_985.0],
  ['Copperline Wire & Cable', 7_628.15],
  ['Evergreen Landscaping', 5_340.0],
  ['Stonebridge Masonry', 19_904.9],
  ['Apex Crane Services', 38_600.0],
  ['Westgate Insulation', 6_775.2],
  ['Baylor Paint & Coatings', 4_118.65],
  ['Frontier Fasteners', 1_264.4],
  ['Silverleaf Flooring', 11_382.0],
  ['Hillcrest Safety Supply', 2_847.9],
  ['Quarry Road Aggregates', 14_206.35],
  ['Benchmark Engineering', 9_500.0],
  ['Lakeside Portable Toilets', 865.0],
  ['True North Windows & Doors', 21_490.8],
  ['Oakmont Cabinetry', 16_318.0],
  ['Brightwater Fire Protection', 8_046.5],
  ['Riverbend Asphalt', 25_730.0],
  ['Pinecrest Scaffolding', 5_912.0],
  ['Cornerstone Permits', 1_420.0],
  ['Fieldstone Tile', 7_083.45],
  ['Highland Fuel Co.', 3_967.12],
  ['Ridgeview Fencing', 4_650.0],
  ['Union Hardware Supply', 2_309.77],
  ['Mesa Concrete Pumping', 6_480.0],
  ['Sterling Elevator', 17_250.0],
  ['Crestline Waterproofing', 9_118.6],
  ['Lone Pine Drafting', 2_150.0],
  ['Summit Concrete', 48_720.0],
]

const MOCK_PAYMENTS: Payment[] = VENDORS.map(([payee, amount], index) => ({
  id: `pay_${String(index + 1).padStart(3, '0')}`,
  payee,
  amount_usd: amount,
  invoice_number: `INV-${20417 + index * 3}`,
  check_number: 1041 + index,
}))

const MOCK_RUN: PaymentRun = {
  id: DEMO_RUN_ID,
  company: 'Ridgeline Builders',
  run_date: '2026-10-29',
  funding_account_last4: '6150',
  payments: MOCK_PAYMENTS,
}

const HELD: Record<string, { score: number; reasons: string[]; signals: string[] }> = {
  'Northfield Drywall': {
    score: 0.64,
    reasons: ['New bank details'],
    signals: [
      'Remit-to account changed 2 days ago',
      'Change requested by phone, not yet confirmed',
      'Payee and amount otherwise match history',
    ],
  },
  'Apex Crane Services': {
    score: 0.58,
    reasons: ['Amount 3x usual'],
    signals: [
      'Invoice is 3.1x the 12-month average',
      'No matching purchase order',
      'Bank details unchanged since 2024',
    ],
  },
}

const BLOCKED: Record<string, { score: number; reason: string; signals: string[] }> = {
  'Summit Concrete': {
    score: 0.97,
    reason: 'Lookalike sender domain',
    signals: [
      'Bank change emailed from summit-concrete.co, not summitconcrete.com',
      'Sender domain registered 3 days ago',
      'Asked for urgent same-day payment',
    ],
  },
}

const VERIFICATION_CALLS: Record<
  string,
  { source: ContactSource; outcome: CallOutcome; lines: Array<[CallSpeaker, string]> }
> = {
  'Summit Concrete': {
    source: { kind: 'vendor_website', phone: '(303) 555-0100', detail: 'summitconcrete.com/contact' },
    outcome: 'denied',
    lines: [
      ['vendor', 'Summit Concrete, accounts receivable. This is Marisol.'],
      ['countersign', "Hi Marisol, this is Countersign calling for Ridgeline Builders' accounts payable team."],
      [
        'countersign',
        "Before we send invoice 20534 for $48,720, I'm confirming a request to pay a new bank account ending in 7781. Did Summit Concrete ask for that change?",
      ],
      ['vendor', "No, we haven't changed banks. Please keep paying the account on file."],
      ['countersign', "Understood. I'm blocking this payment and flagging the request as fraud. Thanks for confirming."],
      ['vendor', 'Thank you for checking with us.'],
    ],
  },
}

const mockAttackCardByRun = new Map<string, AttackCardId>()

const ATTACK_OUTCOMES: Record<AttackCardId, { score: number; reason: string; signals: string[] }> = {
  bank_change: BLOCKED['Summit Concrete'],
  poisoned_invoice: {
    score: 0.99,
    reason: 'Hidden instructions in invoice',
    signals: [
      'Invoice PDF contains 3 hidden instructions: white text, 1pt text, off-page text',
      'Instructions were read as data and ignored, not followed',
      'Remit-to account in the hidden text differs from the vendor record',
    ],
  },
  ceo_pressure: {
    score: 0.94,
    reason: 'Unverified executive request',
    signals: [
      'Sent from ridgeline-builders.co, not your domain ridgelinebuilders.com',
      'Asks to skip the verification call',
      'Urgency and secrecy language typical of CEO fraud',
    ],
  },
  freestyle: {
    score: 0.91,
    reason: 'Reply failed verification',
    signals: [
      'Reply came from a sender not on the vendor record',
      'Requested changes conflict with 12 months of payment history',
      'Verification call to the number on file did not confirm',
    ],
  },
}

const MOCK_THREADS: InboxThread[] = [
  {
    id: SUMMIT_THREAD_ID,
    subject: 'Invoice INV-20534 · Lot 14 foundation pour',
    vendor: 'Summit Concrete',
    labels: ['Inbox', 'Vendors', 'Thursday run'],
    messages: [
      {
        id: 'msg_summit_1',
        from_name: 'Marisol Vega',
        from_addr: 'mvega@summitconcrete.com',
        to_name: 'Ridgeline AP',
        to_addr: 'ap@ridgelinebuilders.com',
        sent_at: '2026-10-20T09:14:00-06:00',
        body: `Hi Ridgeline AP team,

Please find attached invoice INV-20534 for the Lot 14 foundation pour completed Oct 16 to 17. Total due is $48,720.00, net 10.

Payment can go to the account on file. Let me know if you need the delivery tickets.

Thanks,
Marisol Vega
Accounts Receivable, Summit Concrete
(303) 555-0148`,
        attachments: [
          { filename: 'INV-20534.pdf', size_kb: 82 },
          { filename: 'Delivery-tickets-Lot14.pdf', size_kb: 214 },
        ],
      },
      {
        id: 'msg_summit_2',
        from_name: 'Priya Shah',
        from_addr: 'priya.shah@ridgelinebuilders.com',
        to_name: 'Marisol Vega',
        to_addr: 'mvega@summitconcrete.com',
        sent_at: '2026-10-21T14:02:00-06:00',
        body: `Hi Marisol,

Got it, thanks. INV-20534 is approved and queued for our Thursday payment run on Oct 29.

Priya Shah
Accounts Payable, Ridgeline Builders`,
        attachments: [],
      },
      {
        id: 'msg_summit_3',
        from_name: 'Marisol Vega',
        from_addr: 'mvega@summitconcrete.com',
        to_name: 'Priya Shah',
        to_addr: 'priya.shah@ridgelinebuilders.com',
        sent_at: '2026-10-21T14:40:00-06:00',
        body: `Perfect, thank you Priya. Appreciate the quick turnaround.

Marisol`,
        attachments: [],
      },
    ],
  },
  {
    id: 'thr_granite_statement_oct',
    subject: 'October statement · Granite Peak Lumber',
    vendor: 'Granite Peak Lumber',
    labels: ['Inbox', 'Vendors'],
    messages: [
      {
        id: 'msg_granite_1',
        from_name: 'Granite Peak Billing',
        from_addr: 'billing@granitepeaklumber.com',
        to_name: 'Ridgeline AP',
        to_addr: 'ap@ridgelinebuilders.com',
        sent_at: '2026-10-19T08:30:00-06:00',
        body: 'Your October statement is attached. Balance due: $18,432.60.',
        attachments: [{ filename: 'Statement-Oct-2026.pdf', size_kb: 64 }],
      },
    ],
  },
]

const CLEAN_SIGNALS = [
  ['Known payee since 2021', 'Bank details unchanged', 'Amount within usual range'],
  ['Matches approved purchase order', 'Bank details unchanged', 'Invoice sent from verified domain'],
  ['Recurring monthly vendor', 'Amount within usual range', 'No recent account changes'],
]

function replayMockRun(runId: string, onEvent: (event: RunEvent) => void) {
  const schedule: Array<{ at: number; event: RunEvent }> = []
  const payments = MOCK_RUN.payments
  let paid = 0
  let held = 0
  let blocked = 0
  let totalUsd = 0
  const attackCard = mockAttackCardByRun.get(runId)

  schedule.push({ at: 400, event: { type: 'run.started', data: { run_id: runId, invoice_count: payments.length } } })

  payments.forEach((payment, index) => {
    const isLast = index === payments.length - 1
    const at = 900 + index * 330 + (isLast ? 900 : 0)
    const outcomeAt = at + (isLast ? 600 : 180)
    const heldInfo = HELD[payment.payee]
    const blockedInfo =
      attackCard && payment.payee === 'Summit Concrete' ? ATTACK_OUTCOMES[attackCard] : BLOCKED[payment.payee]

    if (blockedInfo) {
      blocked++
      schedule.push({
        at,
        event: {
          type: 'risk.scored',
          data: { payment_id: payment.id, score: blockedInfo.score, decision: 'block', top_signals: blockedInfo.signals },
        },
      })
      const call = VERIFICATION_CALLS[payment.payee]
      const blockedAt = call ? scheduleCall(schedule, payment.id, call, at + 1100) + 2800 : outcomeAt
      schedule.push({
        at: blockedAt,
        event: { type: 'payment.blocked', data: { payment_id: payment.id, reason: blockedInfo.reason } },
      })
    } else if (heldInfo) {
      held++
      schedule.push({
        at,
        event: {
          type: 'risk.scored',
          data: { payment_id: payment.id, score: heldInfo.score, decision: 'hold', top_signals: heldInfo.signals },
        },
      })
      schedule.push({
        at: outcomeAt,
        event: { type: 'payment.held', data: { payment_id: payment.id, reasons: heldInfo.reasons } },
      })
    } else {
      paid++
      totalUsd += payment.amount_usd
      schedule.push({
        at,
        event: {
          type: 'risk.scored',
          data: {
            payment_id: payment.id,
            score: Number((0.02 + ((index * 37) % 11) / 100).toFixed(2)),
            decision: 'pay',
            top_signals: CLEAN_SIGNALS[index % CLEAN_SIGNALS.length],
          },
        },
      })
      schedule.push({
        at: outcomeAt,
        event: {
          type: 'payment.paid',
          data: { payment_id: payment.id, nessie_transfer_id: `nes_${(0x5f3a2b + index * 7919).toString(16)}` },
        },
      })
    }
  })

  const lastAt = Math.max(...schedule.map((entry) => entry.at))
  schedule.push({
    at: lastAt + 700,
    event: {
      type: 'run.completed',
      data: { run_id: runId, paid, held, blocked, total_usd: Math.round(totalUsd * 100) / 100 },
    },
  })

  const timers = schedule.map(({ at, event }) => setTimeout(() => onEvent(event), at))
  return () => timers.forEach(clearTimeout)
}

/** Pushes call.started, paced call.transcript lines, and call.outcome. Returns the outcome time. */
function scheduleCall(
  schedule: Array<{ at: number; event: RunEvent }>,
  paymentId: string,
  call: (typeof VERIFICATION_CALLS)[string],
  startAt: number,
) {
  schedule.push({ at: startAt, event: { type: 'call.started', data: { payment_id: paymentId, contact_source: call.source } } })

  let at = startAt + 2600 // ringing
  for (const [speaker, text] of call.lines) {
    schedule.push({ at, event: { type: 'call.transcript', data: { payment_id: paymentId, speaker, text } } })
    at += Math.min(4200, 900 + text.length * 24)
  }

  schedule.push({ at, event: { type: 'call.outcome', data: { payment_id: paymentId, outcome: call.outcome } } })
  return at
}

// ---------- Mock payment detail ----------

const HISTORY_MONTHS = Array.from({ length: 12 }, (_, i) => {
  const date = new Date(2025, 10 + i, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
})

function pseudoRandom(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

function signal(name: string, weight: number, detail: string, evidence_id: string): RiskSignal {
  return { name, weight, detail, evidence_id }
}

const SUMMIT_SIGNALS: Record<AttackCardId, { score: number; signals: RiskSignal[]; requestedVia: string }> = {
  bank_change: {
    score: 85,
    requestedVia: 'Email from billing@summit-concrete.co',
    signals: [
      signal('bank_account_changed', 30, 'New bank account ending 7781; last verified account ending 2204, confirmed by phone on Mar 12', 'ev_bank_7781'),
      signal('lookalike_sender_domain', 25, 'Sent from summit-concrete.co, not summitconcrete.com', 'ev_sender_domain'),
      signal('urgency_language', 15, 'Asked to process today', 'ev_urgency'),
      signal('reply_to_mismatch', 15, 'Reply-To differs from sender', 'ev_reply_to'),
    ],
  },
  poisoned_invoice: {
    score: 95,
    requestedVia: 'Hidden text inside INV-20534.pdf',
    signals: [
      signal('hidden_instructions', 30, 'Invoice PDF contains 3 hidden instructions: white text, 1pt text, and off-page text', 'ev_pdf_hidden_text'),
      signal('bank_account_changed', 30, 'Hidden text names account ending 7781; last verified account ending 2204, confirmed by phone on Mar 12', 'ev_bank_7781'),
      signal('prompt_injection', 25, 'The hidden text addresses the AI directly and tells it to skip verification', 'ev_injection'),
      signal('urgency_language', 10, 'Asked to process today', 'ev_urgency'),
    ],
  },
  ceo_pressure: {
    score: 95,
    requestedVia: 'Email from ceo@ridgeline-builders.co',
    signals: [
      signal('lookalike_executive_domain', 30, 'Sent from ridgeline-builders.co, not your domain ridgelinebuilders.com', 'ev_sender_domain'),
      signal('skip_verification', 30, 'Asks AP to skip the verification call', 'ev_skip_call'),
      signal('secrecy_language', 20, 'Asks to keep the change between the two of you', 'ev_secrecy'),
      signal('urgency_language', 15, 'Asked to process today', 'ev_urgency'),
    ],
  },
  freestyle: {
    score: 90,
    requestedVia: 'Reply in the Summit Concrete thread',
    signals: [
      signal('unknown_sender', 30, 'Reply came from an address that is not on the vendor record', 'ev_sender_unknown'),
      signal('history_conflict', 25, 'The requested change conflicts with 12 months of payment history', 'ev_history'),
      signal('call_not_confirmed', 20, 'The vendor, called at the number on file, did not confirm the request', 'ev_call'),
      signal('reply_to_mismatch', 15, 'Reply-To differs from sender', 'ev_reply_to'),
    ],
  },
}

const HELD_DETAIL: Record<string, { signals: RiskSignal[]; accounts: BankAccount[]; historyRatio?: number }> = {
  'Northfield Drywall': {
    signals: [
      signal('bank_account_changed', 30, 'Remit-to account changed 2 days ago, to an account ending 5512', 'ev_bank_5512'),
      signal('change_unconfirmed', 20, 'The change was requested by phone and has not been confirmed by a callback', 'ev_change_request'),
      signal('change_near_payment', 10, 'Changed within 7 days of a scheduled payment', 'ev_change_timing'),
      signal('history_match', 4, 'Payee and amount otherwise match 12 months of history', 'ev_history'),
    ],
    accounts: [
      {
        id: 'ba_northfield_5512',
        bank_name: 'Unverified bank',
        last4: '5512',
        status: 'requested',
        added_at: '2026-10-27',
        requested_via: 'Phone call to Ridgeline AP',
        verification: { method: 'unverified', detail: 'Not verified. No payment has gone to this account.' },
      },
      {
        id: 'ba_northfield_3390',
        bank_name: 'Alpine Bank',
        last4: '3390',
        status: 'active',
        added_at: '2022-06-14',
        verification: { method: 'signed_form', verified_at: '2022-06-14', detail: 'Signed vendor setup form, on file' },
      },
    ],
  },
  'Apex Crane Services': {
    historyRatio: 3.1,
    signals: [
      signal('amount_outlier', 30, 'Invoice is 3.1x the 12-month average of $12,452', 'ev_amount_history'),
      signal('no_purchase_order', 20, 'No matching purchase order', 'ev_po_lookup'),
      signal('known_vendor', 5, 'Known vendor since 2022, paid 11 times without issue', 'ev_history'),
      signal('bank_unchanged', 3, 'Bank details unchanged since 2024', 'ev_bank_8845'),
    ],
    accounts: [
      {
        id: 'ba_apex_8845',
        bank_name: 'FirstBank',
        last4: '8845',
        status: 'active',
        added_at: '2024-02-05',
        verification: { method: 'micro_deposit', verified_at: '2024-02-07', detail: 'Two micro-deposits confirmed by the vendor' },
      },
      {
        id: 'ba_apex_1206',
        bank_name: 'Wells Fargo',
        last4: '1206',
        status: 'retired',
        added_at: '2022-03-21',
        retired_at: '2024-02-05',
        verification: { method: 'signed_form', verified_at: '2022-03-21', detail: 'Signed vendor setup form, on file' },
      },
    ],
  },
}

const CLEAN_SIGNAL_DETAIL: Record<string, [name: string, detail: string, evidence: string]> = {
  'Known payee since 2021': ['known_vendor', 'Known payee since 2021, paid every month without issue', 'ev_history'],
  'Bank details unchanged': ['bank_unchanged', 'Bank details unchanged since they were verified', 'ev_bank_on_file'],
  'Amount within usual range': ['amount_in_range', 'Amount is within the usual range for this vendor', 'ev_amount_history'],
  'Matches approved purchase order': ['po_match', 'Matches an approved purchase order', 'ev_po_lookup'],
  'Invoice sent from verified domain': ['verified_domain', 'Invoice was sent from the vendor’s verified domain', 'ev_sender_domain'],
  'Recurring monthly vendor': ['recurring_vendor', 'Recurring monthly vendor with a steady billing pattern', 'ev_history'],
  'No recent account changes': ['no_recent_changes', 'No account changes in the last 12 months', 'ev_bank_on_file'],
}

function decisionForScore(score: number): RiskDecision {
  if (score >= 70) return 'block'
  if (score >= 40) return 'hold'
  return 'pay'
}

function buildHistory(payment: Payment, index: number, ratio: number): VendorHistory {
  const base = payment.amount_usd / ratio
  const points = HISTORY_MONTHS.map((month, i) => {
    const isCurrent = i === HISTORY_MONTHS.length - 1
    const amount = isCurrent ? payment.amount_usd : Math.round(base * (0.8 + pseudoRandom(index * 31 + i) * 0.4) * 100) / 100
    const number = Number(payment.invoice_number.slice(4))
    return {
      month,
      amount_usd: amount,
      invoice_number: isCurrent ? payment.invoice_number : `INV-${number - (11 - i) * 120 - 7}`,
      is_current: isCurrent,
    }
  })
  const prior = points.slice(0, -1)
  return {
    vendor_since: String(2019 + (index % 4)),
    average_usd: Math.round((prior.reduce((sum, p) => sum + p.amount_usd, 0) / prior.length) * 100) / 100,
    points,
  }
}

function mockPaymentDetail(paymentId: string, runId?: string): PaymentDetail {
  const index = MOCK_PAYMENTS.findIndex((p) => p.id === paymentId)
  const payment = MOCK_PAYMENTS[index]
  if (!payment) throw new Error('Payment not found')

  if (payment.payee === 'Summit Concrete') {
    const card = (runId && mockAttackCardByRun.get(runId)) || 'bank_change'
    const scenario = SUMMIT_SIGNALS[card]
    const call = VERIFICATION_CALLS['Summit Concrete']
    return {
      risk_assessment: {
        payment_id: paymentId,
        score: scenario.score,
        decision: 'block',
        hard_rules_fired: [
          'New bank details must be confirmed by phone at an independently sourced number before payment',
          ...(card === 'poisoned_invoice' ? ['Instructions found inside documents are treated as data, never followed'] : []),
        ],
        signals: scenario.signals,
      },
      vendor_history: buildHistory(payment, index, 1.32),
      bank_accounts: [
        {
          id: 'ba_summit_7781',
          bank_name: 'Unknown bank, routing 102000117',
          last4: '7781',
          status: 'requested',
          added_at: '2026-10-28',
          requested_via: scenario.requestedVia,
          verification: { method: 'unverified', detail: 'Not verified. No payment has gone to this account.' },
        },
        {
          id: 'ba_summit_2204',
          bank_name: 'Colorado Business Bank',
          last4: '2204',
          status: 'active',
          added_at: '2026-03-12',
          verification: {
            method: 'phone_callback',
            verified_at: '2026-03-12',
            detail: 'Confirmed by phone with Marisol Vega at (303) 555-0100',
          },
        },
        {
          id: 'ba_summit_0937',
          bank_name: 'First Western Trust',
          last4: '0937',
          status: 'retired',
          added_at: '2021-04-08',
          retired_at: '2026-03-12',
          verification: { method: 'signed_form', verified_at: '2021-04-08', detail: 'Signed vendor setup form, on file' },
        },
      ],
      calls: [
        {
          id: 'call_summit_20534',
          started_at: '2026-10-29T10:42:00-06:00',
          contact_source: call.source,
          outcome: call.outcome,
          transcript: call.lines.map(([speaker, text]) => ({ speaker, text })),
        },
      ],
    }
  }

  const held = HELD_DETAIL[payment.payee]
  if (held) {
    const score = held.signals.reduce((sum, s) => sum + s.weight, 0)
    return {
      risk_assessment: { payment_id: paymentId, score, decision: decisionForScore(score), hard_rules_fired: [], signals: held.signals },
      vendor_history: buildHistory(payment, index, held.historyRatio ?? 1),
      bank_accounts: held.accounts,
      calls: [],
    }
  }

  const score = Math.round((0.02 + ((index * 37) % 11) / 100) * 100)
  const weights = [Math.ceil(score / 2), Math.floor(score / 3), 0]
  weights[2] = score - weights[0] - weights[1]
  const signals = CLEAN_SIGNALS[index % CLEAN_SIGNALS.length].map((label, i) => {
    const [name, detail, evidence] = CLEAN_SIGNAL_DETAIL[label]
    return signal(name, weights[i], detail, evidence)
  })
  const last4 = String(1000 + ((index * 7919) % 9000)).slice(-4)
  return {
    risk_assessment: { payment_id: paymentId, score, decision: 'pay', hard_rules_fired: [], signals },
    vendor_history: buildHistory(payment, index, 1),
    bank_accounts: [
      {
        id: `ba_${paymentId}`,
        bank_name: ['US Bank', 'Chase', 'FirstBank', 'Alpine Bank'][index % 4],
        last4,
        status: 'active',
        added_at: `${2019 + (index % 4)}-0${(index % 8) + 1}-15`,
        verification:
          index % 2
            ? { method: 'phone_callback', verified_at: `${2019 + (index % 4)}-0${(index % 8) + 1}-16`, detail: 'Confirmed by phone at the number in the vendor master file' }
            : { method: 'signed_form', verified_at: `${2019 + (index % 4)}-0${(index % 8) + 1}-15`, detail: 'Signed vendor setup form, on file' },
      },
    ],
    calls: [],
  }
}

function mockAnswer(detail: PaymentDetail, paymentId: string): AskResponse {
  const { decision, signals } = detail.risk_assessment
  const payee = MOCK_PAYMENTS.find((p) => p.id === paymentId)?.payee

  if (payee === 'Summit Concrete' && signals[0]?.evidence_id === 'ev_bank_7781') {
    return {
      answer:
        'I blocked this payment because the only request to pay a new account, ending 7781, came by email from summit-concrete.co, a lookalike of the real domain summitconcrete.com. The email pushed for same-day payment and set a Reply-To that differs from the sender. Summit Concrete’s last verified account ends in 2204 and was confirmed by phone on Mar 12, so I called the number on their website. They denied making the change.',
      evidence: ['ev_bank_7781', 'ev_sender_domain', 'ev_urgency', 'ev_reply_to'],
    }
  }

  const top = [...signals].sort((a, b) => b.weight - a.weight).slice(0, decision === 'pay' ? 3 : 2)
  const verb = decision === 'block' ? 'blocked' : decision === 'hold' ? 'held' : 'released'
  const reasons = top.map((s) => lowerFirst(s.detail))
  const joined = reasons.length > 1 ? `${reasons.slice(0, -1).join('; ')}; and ${reasons.at(-1)}` : reasons[0]
  const closing =
    decision === 'pay'
      ? 'Nothing about it differed from this vendor’s history, so no call was needed.'
      : 'A person on your team needs to approve or reject it before any money moves.'
  return {
    answer: `I ${verb} this payment because ${joined}. ${closing}`,
    evidence: top.map((s) => s.evidence_id),
  }
}

function lowerFirst(text: string) {
  return text.charAt(0).toLowerCase() + text.slice(1)
}
