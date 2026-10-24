'use client'

import { motion, useReducedMotion } from 'framer-motion'

export function VoidStamp() {
  const reduceMotion = useReducedMotion() ?? false

  return (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 flex items-center justify-end pr-4">
      <motion.span
        initial={reduceMotion ? false : { opacity: 0, scale: 2.6, rotate: -22 }}
        animate={{ opacity: 0.92, scale: 1, rotate: -9 }}
        transition={{ type: 'spring', stiffness: 520, damping: 22, mass: 0.9 }}
        className="rounded-md border-4 border-double border-void bg-card/80 px-2.5 py-0.5 text-lg font-black uppercase leading-none tracking-[0.3em] text-void"
      >
        Void
      </motion.span>
    </span>
  )
}
