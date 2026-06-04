## knowledge_search

**Triggers:** pricing, features, availability, general product questions.

**Steps:** answer from FAQ first; if unknown, say so and offer human handoff (`agent_demande_humain`) or ticket.

**Exit:** usually single turn (`scenario_state: null`). Multi-turn only if the user keeps asking related follow-ups under the same topic.
