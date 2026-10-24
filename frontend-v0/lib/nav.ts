export const NAV_ITEMS = [
  { label: 'Product', href: '/#product' },
  { label: 'How it works', href: '/#how-it-works' },
  { label: 'Security', href: '/#security' },
  { label: 'Live demo', href: '/run' },
  { label: 'Leaderboard', href: '/leaderboard' },
] as const

export type NavLabel = (typeof NAV_ITEMS)[number]['label']

export const APP_NAV_ITEMS = [
  { label: 'Payment run', href: '/run' },
  { label: 'Attack console', href: '/attack' },
  { label: 'Leaderboard', href: '/leaderboard' },
] as const

export type AppNavLabel = (typeof APP_NAV_ITEMS)[number]['label']
