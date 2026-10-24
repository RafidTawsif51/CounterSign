import { AuditEvidence } from '@/components/landing/audit-evidence'
import { Capabilities } from '@/components/landing/capabilities'
import { CommandCenter } from '@/components/landing/command-center'
import { PaymentsTicker } from '@/components/landing/payments-ticker'
import { RoiCalculator } from '@/components/landing/roi-calculator'
import { ClosingCta } from '@/components/landing/closing-cta'
import { Hero } from '@/components/landing/hero'
import { HowItWorks } from '@/components/landing/how-it-works'
import { Integrations } from '@/components/landing/integrations'
import { Security } from '@/components/landing/security'
import { StatStrip } from '@/components/landing/stat-strip'
import { Threats } from '@/components/landing/threats'
import { SiteFooter } from '@/components/site/site-footer'
import { SiteNav } from '@/components/site/site-nav'

export default function Page() {
  return (
    <>
      <SiteNav />
      <main>
        <Hero />
        <PaymentsTicker />
        <Integrations />
        <Capabilities />
        <CommandCenter />
        <StatStrip />
        <HowItWorks />
        <Threats />
        <RoiCalculator />
        <Security />
        <AuditEvidence />
        <ClosingCta />
      </main>
      <SiteFooter />
    </>
  )
}
