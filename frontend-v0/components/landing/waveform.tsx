'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { cn } from '@/lib/utils'

const BARS = Array.from({ length: 36 }, (_, i) => {
  const wave = Math.abs(Math.sin(i * 0.55) * 0.6 + Math.sin(i * 1.7) * 0.4)
  return Math.round(22 + wave * 78)
})

export function Waveform({ active = true, className }: { active?: boolean; className?: string }) {
  const reduceMotion = useReducedMotion() ?? false
  const animate = active && !reduceMotion

  return (
    <div aria-hidden="true" className={cn('flex h-7 items-center gap-[3px]', className)}>
      {BARS.map((height, i) => (
        <motion.span
          key={i}
          className="w-[2px] shrink-0 rounded-full bg-current"
          style={{ height: `${height}%`, originY: 0.5 }}
          animate={animate ? { scaleY: [1, 0.35, 1] } : undefined}
          transition={animate ? { duration: 1.4, repeat: Infinity, delay: i * 0.045, ease: 'easeInOut' } : undefined}
        />
      ))}
    </div>
  )
}
