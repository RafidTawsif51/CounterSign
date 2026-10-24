import { AppNav } from '@/components/site/app-nav'
import { PlaceholderPage } from '@/components/site/placeholder-page'

export default function LeaderboardPage() {
  return (
    <>
      <AppNav current="Leaderboard" />
      <PlaceholderPage
        eyebrow="Leaderboard"
        title="Who came closest"
        description="The attempts that got furthest past Countersign's checks will be ranked here, along with how each one was caught."
      />
    </>
  )
}
