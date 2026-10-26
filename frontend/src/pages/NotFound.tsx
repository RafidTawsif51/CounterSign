import { Link, useLocation } from "react-router-dom";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";

export function NotFound() {
  const { pathname } = useLocation();
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState title={`Nothing lives at ${pathname}.`}>
        Every screen is listed in the sidebar.{" "}
        <Link to="/app" className="text-accent underline-offset-4 hover:underline">
          Go to the payment run
        </Link>
      </EmptyState>
    </>
  );
}
