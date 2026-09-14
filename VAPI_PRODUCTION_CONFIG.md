# Vapi production configuration

This is the current source of truth for Gislegrillen.

## Tone

Ordinary Swedish pizzeria cashier. Not a phrase list.
Usual ask: `vill du ha något mer?` Confirm: `är det bra så?`
Do not ask äta här / ta med. Do not speak tool-fillers.

## Stack

- Model: OpenAI `gpt-5.6-luna`, reasoning `none`, temperature `0.3`,
  max tokens `280`. Prompt cache key `gislegrillen-order-v17`.
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
spoken goodbye only after HTTP 2xx → hang up.

Backend returns **422** when save/validate fails so Vapi runs
`request-failed`, not request-complete. Menu match, prices (none spoken),
draft-token, and per-call duplicate place_order are enforced in `main.py`.

## Tool wait (Vapi reliability)

One brief request-start. Delayed message only if the HTTP call is still
open after 5 seconds. Function tools (`draft_order` / `place_order`) do
not accept `timeoutSeconds` or `backoffPlan` in the Vapi API; those
fields are for API Request tools. Duplicate saves are blocked in the
backend (draft-token + per-call idempotency). Failed saves return HTTP
**422** so Vapi runs request-failed instead of goodbye.

`draft_order` / `place_order`:

- request-start: `okej,` (`blocking: false`)
- request-response-delayed: 5000 ms, `det tar en sekund till,`
- `draft_order` request-complete: **system** (read the `readback`)
- `place_order` request-complete: **one** spoken goodbye, then hang up
- request-failed: **system** (do not promise the order is saved)

Do not add a second `place_order` request-complete. Empty start/delayed
content is not allowed: Vapi may play a default filler, and the model
then talks over it.

## Interruption and pronunciation

`stopSpeakingPlan.acknowledgementPhrases` must not include `va`, `hallå`,
or `hej` — those cut off the goodbye. Chunk replacements:

- `Gislegrillen` / `gislegrillen` → `yislegrillen` (one word, not Gissle / Gisle-grillen)
- `Ciao-Ciao` / `ciao-ciao` → `tjao-tjao`
- `33cl` → `trettiotre`, `50cl` → `femtio`, `1.5 liter` → `en och en halv liter`

Stor cola/fanta/sprite = `2 liter`. Only stor pepsi max = `1.5 liter`.

## Required order tools

`draft_order`, `place_order`, `transfer_to_staff`. No `endCall` tool.
`async: false`. Canonical message payloads are in
`scripts/onboard_pizzeria.py`.
