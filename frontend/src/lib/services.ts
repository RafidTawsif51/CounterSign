// Which services are real right now, so the screen never says a sponsor did something it did not.
//
// A stored record knows best (a call's own `simulated`, a payment's `transfer_mode`, the CRS result's `source`) and is
// used first. For things the stream shows before a record exists, the server's MOCK_* flags (GET /api/health) decide.
// The offline demo runs on built-in data, so there everything is simulated.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { isMock, isReplay } from "@/lib/data-mode";
import { recordedSimulated } from "@/lib/replay";

/** true = that service is simulated. `known` is false until the server has answered. */
export interface ServiceModes {
  known: boolean;
  twilio: boolean;
  cartesia: boolean;
  apify: boolean;
  crs: boolean;
  nessie: boolean;
  claude: boolean;
}

const ALL_SIMULATED: ServiceModes = { known: true, twilio: true, cartesia: true, apify: true, crs: true, nessie: true, claude: true };
const UNKNOWN: ServiceModes = { known: false, twilio: false, cartesia: false, apify: false, crs: false, nessie: false, claude: false };

export function useServiceModes(): ServiceModes {
  const { data } = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15_000, staleTime: 10_000, retry: false });
  if (isReplay())
    return { known: true, twilio: recordedSimulated("twilio"), cartesia: recordedSimulated("cartesia"), apify: recordedSimulated("apify"), crs: recordedSimulated("crs"), nessie: recordedSimulated("nessie"), claude: recordedSimulated("claude") };
  if (isMock()) return ALL_SIMULATED;
  if (!data) return UNKNOWN;
  const m = data.mocks;
  return { known: true, twilio: !!m.twilio, cartesia: !!m.cartesia, apify: !!m.apify, crs: !!m.crs, nessie: !!m.nessie, claude: !!m.claude };
}

/** The seeded run's planted attacks always take scripted call outcomes, even with live calls on (verify.SEEDED_CALLS). */
export const SEEDED_CALL_PAYMENTS = ["pay_atk_bank_change", "pay_atk_ceo_pressure"];

/** Was this call scripted? Its own record first; until there is one, the settings and the seeded-attack rule. */
export function callSimulated(call: { paymentId: string; simulated?: boolean | null }, modes: ServiceModes): boolean {
  if (call.simulated != null) return call.simulated;
  return modes.twilio || modes.cartesia || SEEDED_CALL_PAYMENTS.includes(call.paymentId);
}
