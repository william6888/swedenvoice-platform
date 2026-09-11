# Vapi setup guide (deprecated)

This file is retained only so old links do not break.

Do not configure an assistant from historical snippets or screenshots. Use
[`VAPI_PRODUCTION_CONFIG.md`](VAPI_PRODUCTION_CONFIG.md) as the only source of
truth for:

- the tested model, Swedish transcriber and voice;
- the `draft_order` and `place_order` schemas;
- the confirmation rejection guard;
- the exact draft, readback, confirmation and commit contract.

For a new restaurant, run `scripts/onboard_pizzeria.py` so tenant-specific
tools, webhook authentication and the current safety configuration are copied
from the production template.
