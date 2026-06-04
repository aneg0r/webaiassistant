## customer_service_returns

**Triggers:** return, refund, exchange, warranty, SAV.

**Collection (in order):**
1. Under warranty? (yes/no)
2. Reason for return.

**Steps:**
1. Collect both fields in `collected`.
2. If eligible: fill `ticket` with `{sous_garantie, motif, session_id}` and explain timelines (5–7 business days).
3. If not eligible: explain policy; offer human handoff if needed.

**Exit:** ticket sent and user informed → `scenario_state: null`.
