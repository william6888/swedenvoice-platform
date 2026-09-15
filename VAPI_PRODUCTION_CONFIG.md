# Vapi production configuration

This is the current source of truth for Gislegrillen.

## Tone

Ordinary Swedish pizzeria cashier. Not a phrase list.
Usual ask: `vill du ha något mer?` Confirm: `är det bra så?`
Do not ask äta här / ta med. Do not speak tool-fillers.

## Stack

- Model: OpenAI `gpt-5.6-luna`, reasoning `none`, temperature `0.3`,
  max tokens `280`. Prompt cache key `gislegrillen-order-v18`.
- Voice: ElevenLabs Jonas, `eleven_flash_v2_5`, language `sv`, speed `1.0`,
  stability `0.75`, `optimizeStreamingLatency` `3`. Chunk min 30.
- firstMessage: `välkommen till gislegrillen, vad vill du beställa?`
- `endCall` tool is off. `endCallMessage` is empty so goodbye is not spoken
  twice. Hangup is only `place_order` request-complete with
  `endCallAfterSpokenEnabled: true`.
- Shared conversation rules live in `voice_conversation_rules.md`.
  Restaurant menu and branding are appended by `build_system_prompt()`.

## Flow

Take order → `draft_order` → read back → confirm → `place_order` →
spoken goodbye only after a successful function-tool `result` → hang up.

Interrupted readback or a correction: new `draft_order`, new yes, then save.

These are **function tools**. A handled failure is HTTP **200** with:

`{"results":[{"toolCallId":"<id>","error":"Order was not saved: <reason>."}]}`

Do not return HTTP 422 for a handled save/validate failure. Menu match,
drink brand+size, draft-token, and per-call duplicate place_order are
enforced in `main.py`. If a save exception happens, look up a completed
order for that call before retrying.

## Tool wait

One brief request-start. Delayed message only if the HTTP call is still
open after 5 seconds. Function tools do not accept `timeoutSeconds` or
`backoffPlan`.

`draft_order` / `place_order`:

- request-start: `okej,` (`blocking: false`)
- request-response-delayed: 5000 ms, `det tar en sekund till,`
- `draft_order` request-complete: **system** (read the `readback`)
- `place_order` request-complete: **one** spoken goodbye, then hang up
- request-failed: **system**, speak the `error` string. Do not transfer.

Do not add a second `place_order` request-complete. `place_order` has no
rejectionPlan.

## Interruption and pronunciation

`acknowledgementPhrases` **suppress** barge-in (mm, okej, ja, jaha, va,
hallå, mhm). `numWords` is 2. Chunk replacements:

- `Gislegrillen` / `gislegrillen` → `yislegrillen`
- `Ciao-Ciao` / `ciao-ciao` → `tjao-tjao`
- `33cl` → `trettiotre`, `50cl` → `femtio`, `1.5 liter` → `en och en halv liter`

Stor cola/fanta/sprite = `2 liter`. Only stor pepsi max = `1.5 liter`.
Unsupported brand+size pairs are rejected by the backend.

## Required order tools

`draft_order`, `place_order`, `transfer_to_staff`. No `endCall` tool.
`async: false`. Canonical message payloads are in
`scripts/onboard_pizzeria.py`.
