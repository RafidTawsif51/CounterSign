import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/shared/app-shell";
import { About } from "@/pages/About";
import { AttackConsole } from "@/pages/AttackConsole";
import { CallView } from "@/pages/CallView";
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
          {/* The project page for judges and sponsors, inside the app like every other page (DESIGN.md, Project page). */}
          <Route path="/about" element={<About />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        {/* Full screen, no shell: the verification call as a phone-sized live view, beside the board or in the video. */}
        <Route path="/call" element={<CallView />} />
        {/* Full screen, no shell: second display. */}
        <Route path="/leaderboard" element={<Leaderboard />} />
        {/* A developer page: the design tokens rendered. Not in the product build. */}
        {import.meta.env.DEV && <Route path="/design-check" element={<DesignCheck />} />}
      </Routes>
    </BrowserRouter>
  );
}
