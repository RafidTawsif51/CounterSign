import { Link } from "react-router-dom";
import { EmptyState } from "@/components/shared/empty-state";

export function NotFound() {
  return (
    <EmptyState title="This page does not exist">
      <Link to="/" className="text-accent underline-offset-4 hover:underline">
        Go to the payment run
      </Link>
    </EmptyState>
  );
}
