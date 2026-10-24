import { EmptyState } from "@/components/shared/empty-state";

// Runs full screen on a second display, always dark. No app navigation.
export function Leaderboard() {
  return (
    <div data-theme="dark" className="min-h-screen bg-paper text-ink">
      <div className="border-b border-rule px-6 py-6">
        <h1 className="text-xl font-semibold">Rob Countersign</h1>
        <p className="mt-1 text-ink-muted">Every attempt to send money to the wrong account, and whether it was caught.</p>
      </div>
      <EmptyState title="No attacks logged yet">Attempts from the attack console and the bounty inbox appear here live.</EmptyState>
    </div>
  );
}
