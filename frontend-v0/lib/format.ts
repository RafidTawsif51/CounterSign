const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const usdWhole = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

export function formatUsd(amount: number) {
  return usd.format(amount)
}

export function formatUsdWhole(amount: number) {
  return usdWhole.format(amount)
}

export function formatRunDate(isoDate: string) {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

const ONES = [
  'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
  'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen',
]
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']

function underOneThousand(n: number) {
  const parts: string[] = []
  const hundreds = Math.floor(n / 100)
  const rest = n % 100
  if (hundreds) parts.push(`${ONES[hundreds]} hundred`)
  if (rest) {
    if (rest < 20) parts.push(ONES[rest])
    else parts.push(TENS[Math.floor(rest / 10)] + (rest % 10 ? `-${ONES[rest % 10]}` : ''))
  }
  return parts.join(' ')
}

/** Writes an amount the way it appears on a check: "Twelve thousand four hundred eighty and 50/100". */
export function amountInWords(amount: number) {
  const totalCents = Math.round(amount * 100)
  const cents = totalCents % 100
  let remaining = Math.floor(totalCents / 100)
  const parts: string[] = []

  for (const [value, name] of [
    [1_000_000, 'million'],
    [1_000, 'thousand'],
  ] as const) {
    if (remaining >= value) {
      parts.push(`${underOneThousand(Math.floor(remaining / value))} ${name}`)
      remaining %= value
    }
  }
  if (remaining || parts.length === 0) {
    parts.push(remaining ? underOneThousand(remaining) : 'zero')
  }

  const words = parts.join(' ')
  return `${words.charAt(0).toUpperCase()}${words.slice(1)} and ${String(cents).padStart(2, '0')}/100`
}

export function lowerFirst(text: string) {
  return text.charAt(0).toLowerCase() + text.slice(1)
}
