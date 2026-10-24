import type { Metadata } from 'next'
import { AttackConsole } from '@/components/attack/attack-console'
import { AppNav } from '@/components/site/app-nav'

export const metadata: Metadata = {
  title: 'Attack console · Countersign',
  description: 'Play the scammer: send a fraudulent email into a real invoice thread and watch Countersign catch it.',
}

export default function AttackPage() {
  return (
    <>
      <AppNav current="Attack console" />
      <AttackConsole />
    </>
  )
}
