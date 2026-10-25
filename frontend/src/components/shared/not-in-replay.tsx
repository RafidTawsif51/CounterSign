import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { leaveReplay } from "@/lib/replay";

/** A screen that needs the live server, opened during a replay. Says so, instead of failing request by request. */
export function NotInReplay({ title, what }: { title: string; what: string }) {
  return (
    <>
      <PageHeader title={title} description="This screen is not part of the replay." />
      <div className="max-w-[1120px] space-y-4 px-4 py-6 sm:px-6">
        <p className="max-w-[60ch] text-base">{what}</p>
        <Button variant="primary" onClick={leaveReplay}>
          Exit replay
        </Button>
      </div>
    </>
  );
}
