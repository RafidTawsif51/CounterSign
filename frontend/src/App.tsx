import { BrowserRouter, Route, Routes } from "react-router-dom";
import { DesignCheck } from "@/pages/DesignCheck";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Hidden: not linked from any navigation. */}
        <Route path="/design-check" element={<DesignCheck />} />
        <Route path="*" element={<NotBuilt />} />
      </Routes>
    </BrowserRouter>
  );
}

function NotBuilt() {
  return (
    <main className="px-6 py-8">
      <h1 className="text-lg font-semibold">Countersign</h1>
      <p className="mt-1 text-ink-muted">The payment board is not built yet.</p>
    </main>
  );
}
