# Judge Q&A notes

Short, true answers for questions judges are likely to ask. Add to this file as new questions come up; keep every answer to what the system actually does.

## Does the verification call record the vendor?

No. The call is **transcribed**, not recorded. The call opens with: "This is an automated assistant calling for Ridgeline Builders accounts payable. This call is being transcribed." The transcript is stored with the call (`verification_calls.transcript`) and shown on the payment.

Why: our Twilio account is a free trial, and a trial account cannot record calls. California needs all-party consent, so the call says only what is true.

If we move to a paid Twilio account: set `CALL_RECORDING_ENABLED=true`. `place_call` then asks Twilio to record, and the call says "This call is being recorded and transcribed." The flag is the only thing that changes the wording, so the line and the behavior cannot disagree. Storing the recording link (`verification_calls.recording_url`) is not built yet.

## What does the call refuse to do?

It reads out only the last four digits of an account, accepts no new contact details, never confirms a change for the vendor, and hangs up after 60 seconds. It only dials numbers on `ALLOWED_CALL_NUMBERS`.
