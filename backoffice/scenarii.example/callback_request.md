## callback_request

**Triggers:** call me back, contact me, phone call, reach me.

**Collection:** email (required), phone (optional), subject/question (optional — ask after phone; if user declines or does not provide, leave null and proceed to exit).

**Steps:** one field per turn if not provided together.

**Exit:** when all required fields collected, set `action` to `{"type": "callback_request", "payload": {"email": "...", "phone": "...", "question": "..."}}` and `scenario_state: null`.
