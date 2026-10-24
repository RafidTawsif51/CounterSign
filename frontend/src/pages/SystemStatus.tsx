import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/shared/page-header";
import { api } from "@/lib/api";
import type { ComponentMode } from "@/lib/types";

const MODE: Record<ComponentMode, { label: string; variant: "accent" | "neutral" }> = {
  real: { label: "Real", variant: "accent" },
  simulated: { label: "Simulated", variant: "neutral" },
  mock: { label: "Mock", variant: "neutral" },
  degraded: { label: "Degraded", variant: "neutral" },
  down: { label: "Down", variant: "neutral" },
};

export function SystemStatus() {
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["system-status"], queryFn: api.systemStatus });

  return (
    <>
      <PageHeader
        title="System status"
        description="What is real, what is simulated, and what is running on mocks right now."
      />
      <div className="mx-auto max-w-[1120px] px-4 py-6 sm:px-6">
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <p className="text-sm">System status did not load: {error.message}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Component</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((c) => (
                <TableRow key={c.name}>
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell>
                    <Badge variant={MODE[c.mode].variant}>{MODE[c.mode].label}</Badge>
                  </TableCell>
                  <TableCell className="text-ink-muted">{c.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </>
  );
}
