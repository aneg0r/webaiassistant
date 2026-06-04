## feedback_agent

**Triggers:** the conversation is ending — user says goodbye, bye, au revoir, see you, thanks that's all, no more questions, or similar closing phrases. Run only when no other scenario is active, or after the current scenario has closed (`scenario_state: null`).

**Steps:**
1. Acknowledge the goodbye briefly.
2. Ask **in the user's language** (same language as the rest of the reply), e.g. *"May I ask you how was this conversation?"* — put **only the question** in `reply` (no pipe-separated options in the text). Set `buttons` to four items with translated `label` and `value` exactly: `bad`, `neutral`, `good`, `no_answer`.
3. Map the user's reply to `collected.rating`: `bad`, `neutral`, `good`, or `no_answer` (synonyms and typos allowed; treat refusal or skip as `no_answer`).

**Exit:** `action` `{"type": "feedback_agent", "payload": {"rating": "bad"|"neutral"|"good"|"no_answer"}}` and `scenario_state: null`.
