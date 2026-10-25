import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { answerAdminKey, useAdminKeyPrompt } from "@/lib/admin-key";

/** Asks for the admin key when Reset demo, Present or the red-team run needs it. Mounted once in the app shell. */
export function AdminKeyDialog() {
  const prompt = useAdminKeyPrompt();
  const [key, setKey] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const value = key;
    setKey("");
    answerAdminKey(value);
  }

  function cancel() {
    setKey("");
    answerAdminKey(null);
  }

  return (
    <Dialog open={prompt !== null} onOpenChange={(open) => !open && cancel()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Admin key</DialogTitle>
            <DialogDescription>
              {prompt?.retry
                ? "The server did not accept that key. Enter ADMIN_KEY again."
                : "Resetting the demo needs the admin key (ADMIN_KEY on the server). It is kept in this tab only and is asked for once."}
            </DialogDescription>
          </DialogHeader>
          <div className="my-4">
            <label htmlFor="admin-key" className="mb-1 block text-sm font-medium">
              Admin key
            </label>
            <Input id="admin-key" type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" autoFocus className="touch-target" />
          </div>
          <DialogFooter>
            <Button size="sm" type="button" onClick={cancel}>
              Cancel
            </Button>
            <Button size="sm" type="submit" variant="primary" disabled={!key.trim()}>
              Continue
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
