import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { API_URL } from "@/lib/api-url";
import { callSimulated, useServiceModes } from "@/lib/services";
import { useDataMode } from "@/lib/data-mode";
import { startReplay, useRecording } from "@/lib/replay";
import type { CallView } from "@/lib/calls";
import { useQueryClient } from "@tanstack/react-query";

// When a live call does not connect: a calm message and the ways on. It shows only for a real call (a scripted one cannot
// fail this way) that is still going near the 60 second limit, or ended with nobody answering.

/** Seconds into a call after which it is worth offering another way. */
export const TROUBLE_AFTER_S = 45;

const KEY = "countersign-vendor-phone-key";
const readKey = () => {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
};

export function useCallTrouble(call: CallView, elapsed: number): boolean {
  const modes = useServiceModes();
  const mode = useDataMode();
  if (mode !== "live" || callSimulated(call, modes)) return false;
  const stuck = call.phase !== "ended" && call.phase !== "queued" && elapsed >= TROUBLE_AFTER_S;
  return stuck || call.outcome === "no_answer";
}

export function CallTrouble({ call, vendorId }: { call: CallView; vendorId: string | null }) {
  const recording = useRecording();
  const queryClient = useQueryClient();
  const [calling, setCalling] = useState(false);
  const [asking, setAsking] = useState(false);
  const [key, setKey] = useState(readKey);
  const ending = call.phase === "ended";

  async function again() {
    setCalling(true);
    try {
      await api.startCall(call.paymentId);
      toast.success("Calling the vendor again", { description: "At an independent number, not the one in the email." });
      void queryClient.invalidateQueries({ queryKey: ["payment", call.paymentId] });
    } catch (err) {
      toast.error("Call not started", { description: errorMessage(err) });
    } finally {
      setCalling(false);
    }
  }

  function openSoftphone() {
    if (!vendorId) return;
    if (!key.trim()) return setAsking(true);
    try {
      sessionStorage.setItem(KEY, key.trim());
    } catch {
      // Not kept; it is asked for again next time.
    }
    window.open(`${API_URL}/api/voice/vendor-phone/${encodeURIComponent(vendorId)}?k=${encodeURIComponent(key.trim())}`, "countersign-softphone", "popup,width=420,height=720");
    setAsking(false);
  }

  return (
    <div role="status" className="rounded-md border border-rule-strong bg-sunken px-4 py-3 text-sm">
      <p className="font-medium">{ending ? "Nobody answered." : `The call has not connected after ${TROUBLE_AFTER_S} seconds.`}</p>
      <p className="mt-0.5 text-ink-muted">
        Nothing is lost: the payment stays held, and only the controller can release it, and only to the last verified account. Choose how to go on.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" onClick={() => void again()} disabled={calling}>
          Try the call again
        </Button>
        {vendorId && (
          <Button size="sm" onClick={openSoftphone}>
            Use browser softphone
          </Button>
        )}
        {recording && (
          <Button size="sm" onClick={() => void startReplay()}>
            Show recorded replay
          </Button>
        )}
      </div>
      {asking && (
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            openSoftphone();
          }}
        >
          <label htmlFor="softphone-key" className="text-ink-muted">
            Vendor phone key (VENDOR_PHONE_KEY on the server)
          </label>
          <Input id="softphone-key" type="password" value={key} onChange={(e) => setKey(e.target.value)} className="h-7 w-48" autoComplete="off" />
          <Button size="sm" type="submit" variant="primary" disabled={!key.trim()}>
            Open softphone
          </Button>
        </form>
      )}
      {vendorId && <p className="mt-2 text-xs text-ink-muted">The softphone is a page where the vendor answers in a browser. Keep it open and try the call again: if the phone network cannot place the call, it rings there.</p>}
    </div>
  );
}
