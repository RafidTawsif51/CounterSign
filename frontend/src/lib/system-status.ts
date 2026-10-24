// What is real, sandboxed and simulated: the documented list (CLAUDE.md "Real vs simulated"), shown on /status when
// GET /api/system/status fails (and by the offline demo). GET /api/health's mock flags say which of these run on a mock right now.

import type { SystemComponentStatus } from "@/lib/types";

export const DOCUMENTED_STATUS: SystemComponentStatus[] = [
  {
    name: "Claude extraction",
    mode: "real",
    detail: "Claude reads every invoice into a fixed schema. Document text is data, never instructions.",
    mock_flags: ["claude"],
  },
  {
    name: "Risk engine",
    mode: "real",
    detail: "Hard rules and weighted signals against 12 months of each vendor's history.",
    mock_flags: ["risk"],
  },
  {
    name: "Injection defense",
    mode: "real",
    detail: "Scans every PDF and email for hidden text and for instructions aimed at an AI.",
    mock_flags: ["injection"],
  },
  {
    name: "Verification call",
    mode: "real",
    detail: "A real phone call with a Cartesia voice. It calls team phones only: numbers outside the allow list are refused in code.",
    mock_flags: ["twilio", "cartesia"],
  },
  {
    name: "Attacks",
    mode: "real",
    detail: "Sent this weekend by judges, the attack console and the bounty inbox, through the same pipeline as every invoice.",
  },
  {
    name: "Company and vendor history",
    mode: "simulated",
    detail: "Ridgeline Builders, its 30 vendors and 12 months of invoices are fictional, generated from realistic patterns.",
  },
  {
    name: "Payments",
    mode: "sandboxed",
    detail: "Capital One Nessie sandbox. Transfers move sandbox money, never real money.",
    mock_flags: ["nessie"],
  },
  {
    name: "Identity check",
    mode: "sandboxed",
    detail: "CRS sandbox with the provided test identities, checked before money goes to a new destination.",
    mock_flags: ["crs"],
  },
];

export const MODE_LABEL: Record<SystemComponentStatus["mode"], string> = {
  real: "Real",
  sandboxed: "Sandbox",
  simulated: "Simulated",
  mock: "Mock",
  degraded: "Degraded",
};
