## survey

**Triggers:** survey, poll, vote, satisfaction quick question.

**Collection:** present options from operator config in `buttons` (`label` shown, `value` stored in `collected.choice`); question text only in `reply` (no `|` list in reply). User picks one (`collected.choice`).

**Exit:** `action` `{"type": "survey", "payload": {"choice": "...", "survey_id": "default"}}` and `scenario_state: null`.
