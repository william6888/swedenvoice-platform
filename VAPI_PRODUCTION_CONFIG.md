# Vapi production configuration

This is the current source of truth for Gislegrillen.

## Recommended stack

- Model: OpenAI `gpt-5.6-luna`, reasoning effort `none`, temperature `0`, max
  tokens `400`. Prompt cache key `gislegrillen-order-v2`.
- Transcriber: Soniox `stt-rt-v5`, Swedish only, strict language hint, menu
  vocabulary, max endpoint delay `800 ms`.
- Voice: ElevenLabs Jonas (`e6OiUVixGLmvtdn2GJYE`) with
  `eleven_flash_v2_5`, speed `1.0`, stability `0.5`.
- Maximum call duration: `300` seconds.
- Railway: `REQUIRE_DRAFT_TOKEN=true`.
- `place_order` and `draft_order` must have `async=false`.
- Do not attach a confirmation `rejectionPlan` to `place_order`. A rejected
  tool call returns the opaque string `Tool call rejected based on configured
  rejection plan`, which previously made the assistant transfer to staff
  instead of reading the order back.
- Every tool must define `request-start` with empty `content` and no
  conditions, plus `request-response-delayed` with empty `content`. An empty
  `messages` array makes Vapi speak translated fillers such as
  "Vänta en sekund." A start-message whose conditions never match also falls
  back to those fillers.
- `transfer_to_staff` may reject unless the latest customer utterance asks for
  a human, staff, or allergy help.

The English Deepgram fallback must not be used for Swedish calls. A fallback
must also be explicitly configured for Swedish.

## Conversation contract

Take the order the way a cashier would:

1. Repeat the food you heard and ask "Något mer?"
2. Drinks are bought in store. Keep the food.
3. Ask "Äta här eller ta med?" once.
4. Call `draft_order`.
5. Read `readback` exactly and ask "Stämmer det?" Never skip this, even if the
   customer said okay or hello while the draft ran.
6. After a clear yes/okay to that readback, call `place_order` with the same
   payload.
7. On success say "Tack, välkommen." and end the call.
8. "Hallå", silence or "varför?" is not a reason to transfer.

## Required order tools

Both tools use the restaurant-specific authenticated webhook:

`https://<backend>/vapi/webhook?rest_id=<restaurant_id>`

Header: `X-Webhook-Secret: <WEBHOOK_SHARED_SECRET>`.

Use the same parameter schema for `draft_order` and `place_order`:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "items": {
      "type": "array",
      "minItems": 1,
      "maxItems": 30,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "name": {"type": "string"},
          "quantity": {"type": "integer", "minimum": 1, "maximum": 20},
          "special_requests": {"type": "string"}
        },
        "required": ["name", "quantity", "special_requests"]
      }
    },
    "service_mode": {
      "type": "string",
      "enum": ["ta_med", "äta_här"]
    }
  },
  "required": ["items", "service_mode"]
}
```

The LLM must never send menu IDs. The backend resolves names to canonical menu
items and rejects ambiguity. Successful `place_order` tool results omit price.

## Required regression cases

- Kebabrulle + kebabtallrik + kebabpizza with mild sauce on the pizza: recap,
  ask if anything else, takeaway, readback, confirm, thank, hang up. No wait
  filler. No staff transfer.
- Family size retained on the correct pizza.
- Drink rejected without dropping food from the same utterance.
- Ambiguous modifier asks which item.
- Correction causes a new draft and a new confirmation.
- `place_order` failure never produces a success message or ends the call.
- "Hallå" after a pause continues the order instead of transferring.
- Human request and serious allergy transfer to staff.
