# Vapi production configuration

This is the current source of truth for Gislegrillen.

## Tone

Ordinary Swedish pizzeria cashier. Not a phrase list.
Usual ask: `vill du ha något mer?` Confirm: `är det bra så?`
Do not ask äta här / ta med. Do not speak tool-fillers.

## Stack

- Model: OpenAI `gpt-5.6-luna`, reasoning `none`, temperature `0.3`,
  max tokens `280`. Prompt cache key `gislegrillen-order-v16`.
- Voice: ElevenLabs Jonas, `eleven_flash_v2_5`, language `sv`, speed `1.0`,
  stability `0.75`, `optimizeStreamingLatency` `3`. Chunk min 30.
- firstMessage: `välkommen till gislegrillen, vad vill du beställa?`
- `endCall` tool is off. Goodbye is `place_order` request-complete:
  `din beställning är klar om tio minuter, en kvart, välkommen`
  with `endCallAfterSpokenEnabled: true`.
- Tool `request-start` / delayed: empty. Fake cashier lines
  (`då läser jag upp`, `just det`, `då slår jag in den`) are forbidden.
- Drinks: stor cola/fanta/sprite = `2 liter`. Only stor pepsi max = `1.5 liter`.

## Required order tools

`draft_order`, `place_order`, `transfer_to_staff`. No `endCall` tool.
`async: false`.
