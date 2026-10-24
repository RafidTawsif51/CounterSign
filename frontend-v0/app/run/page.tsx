import { PaymentRunScreen } from '@/components/countersign/payment-run-screen'
import { AppNav } from '@/components/site/app-nav'
import { DEMO_RUN_ID } from '@/lib/api'

export default async function RunPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const params = await searchParams
  const runId = typeof params.run === 'string' && params.run ? params.run : DEMO_RUN_ID

  return (
    <>
      <AppNav current="Payment run" />
      <PaymentRunScreen key={runId} runId={runId} autoStart={params.autostart === '1'} />
    </>
  )
}
