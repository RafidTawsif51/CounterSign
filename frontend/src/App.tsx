import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/shared/app-shell";
import { LANDING_ONLY } from "@/lib/landing";
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
  // The landing-only build (deploy/landing) is the project page alone, full screen, at every path.
  if (LANDING_ONLY) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<About />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    );
  }
  return (
    <BrowserRouter>
      <Routes>
        {/* Every visitor lands on the project page first: full screen, no shell, as in the landing-only build. */}
        <Route path="/" element={<About />} />
        <Route element={<AppShell />}>
          <Route path="/app" element={<Board />}>
            <Route path="payments/:paymentId" element={<PaymentDetail />} />
          </Route>
          <Route path="/app/inbox" element={<Inbox />} />
          <Route path="/app/attack" element={<AttackConsole />} />
          <Route path="/app/red-team" element={<RedTeam />} />
          <Route path="/app/status" element={<SystemStatus />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        {/* Full screen, no shell: the verification call as a phone-sized live view, beside the board or in the video. */}
        <Route path="/app/call" element={<CallView />} />
        {/* Full screen, no shell: second display. */}
        <Route path="/app/leaderboard" element={<Leaderboard />} />
        {/* Paths from before the app moved under /app, so old links and bookmarks still work. */}
        {LEGACY_PATHS.map((path) => (
          <Route key={path} path={path} element={<LegacyRedirect />} />
        ))}
        <Route path="/about" element={<AboutRedirect />} />
        {/* A developer page: the design tokens rendered. Not in the product build. */}
        {import.meta.env.DEV && <Route path="/design-check" element={<DesignCheck />} />}
      </Routes>
    </BrowserRouter>
  );
}

const LEGACY_PATHS = ["/inbox", "/attack", "/red-team", "/status", "/call", "/leaderboard", "/payments/:paymentId"];

/** The same screen under /app, with the query (?tv=1, ?payment=...) and hash kept. */
function LegacyRedirect() {
  const { pathname, search, hash } = useLocation();
  return <Navigate to={`/app${pathname}${search}${hash}`} replace />;
}

function AboutRedirect() {
  const { hash } = useLocation();
  return <Navigate to={{ pathname: "/", hash }} replace />;
}
