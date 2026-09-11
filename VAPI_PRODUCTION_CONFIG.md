# Vapi production configuration

This is the current source of truth for Gislegrillen. `VAPI_SETUP_GUIDE.md`
contains older setup examples and must not be used for production values.

## Recommended stack

- Model: OpenAI `gpt-5.6-luna`, reasoning effort `none`, temperature `0`, max
  tokens `250`. In the September 2026 eval set it passed all five critical
  flows and had a median chat response time of `1.35 s`.
- Transcriber: Soniox `stt-rt-v5`, Swedish only, strict language hint, menu
  vocabulary, max endpoint delay `800 ms`.
- Voice: ElevenLabs Jonas (`e6OiUVixGLmvtdn2GJYE`) with
  `eleven_flash_v2_5`, speed `1.0`, stability `0.5`.
- Maximum call duration: `300` seconds.
- Railway: `REQUIRE_DRAFT_TOKEN=true`.
- `place_order` and `draft_order` must have `async=false`.

The English Deepgram fallback must not be used for Swedish calls. A fallback
must also be explicitly configured for Swedish.

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
items and rejects ambiguity.

## Transaction contract

1. Collect the complete order and service mode.
2. Call `draft_order`.
3. Read the returned `readback` and ask for explicit confirmation.
4. Any correction returns to step 2.
5. After explicit confirmation, call synchronous `place_order` with exactly the
   same payload.
6. End the call only when `place_order` returns `success: true`.

In strict mode, a payload that differs from the latest draft is rejected. The
customer-facing end-call message may therefore safely say:

`Beställningen är mottagen. Välkommen.`

Never promise a pickup time.

## Required regression cases

- Simple order.
- Multiple items and quantities.
- Family size retained on the correct pizza.
- Drink rejected without dropping food from the same utterance.
- Ambiguous modifier asks which item.
- Unnamed family pizza asks for the pizza name.
- Correction causes a new draft and a new confirmation.
- Menu no-match and ambiguous suggestions.
- `place_order` failure never produces a success message or ends the call.
- Human request and serious allergy transfer to staff.

Run text evals first, then a small voice simulation set. Voice simulations must
not point at a production order endpoint unless the tool result is mocked.
