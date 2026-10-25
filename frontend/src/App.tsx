import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/shared/app-shell";
import { AttackConsole } from "@/pages/AttackConsole";
import { Board } from "@/pages/Board";
import { DesignCheck } from "@/pages/DesignCheck";
import { Inbox } from "@/pages/Inbox";
import { Leaderboard } from "@/pages/Leaderboard";
import { NotFound } from "@/pages/NotFound";
import { PaymentDetail } from "@/pages/PaymentDetail";
import { RedTeam } from "@/pages/RedTeam";
import { SystemStatus } from "@/pages/SystemStatus";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Board />}>
            <Route path="payments/:paymentId" element={<PaymentDetail />} />
          </Route>
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/attack" element={<AttackConsole />} />
          <Route path="/red-team" element={<RedTeam />} />
          <Route path="/status" element={<SystemStatus />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        {/* Full screen, no shell: second display. */}
        <Route path="/leaderboard" element={<Leaderboard />} />
        {/* A developer page: the design tokens rendered. Not in the product build. */}
        {import.meta.env.DEV && <Route path="/design-check" element={<DesignCheck />} />}
      </Routes>
    </BrowserRouter>
  );
}
