## human_escalation

**Triggers:** speak to a human, real person, operator, support agent.

**Steps:** acknowledge request; set `handoff_signal` to `human_requires_human` or `agent_demande_humain`; fill `ticket` with summary.

**Exit:** after handoff message → `scenario_state: null`.
