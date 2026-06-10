## customer_service_order_handling

**Triggers:** I ordered, tried to order, checkout failed, payment declined, order not confirmed, missing confirmation email, duplicate charge, cannot complete purchase, cart error, wrong amount charged at checkout.

**Collection (in order):**
1. What went wrong (short description).
2. Order reference if any (order number, email used, date — optional; proceed if unknown).
3. Contact email for follow-up if not already known.

**Steps:**
1. One field per turn when information is missing; if the user gives everything at once, skip redundant questions.
2. Summarize the issue for the user, then fill `ticket` with `{summary, scenario, session_id}` including key details from `collected` (problem, order_ref, email).
3. Explain that the service team will follow up; offer `human_escalation` only if the user insists or the case is urgent.

**Exit:** ticket sent and user informed → `scenario_state: null`.
