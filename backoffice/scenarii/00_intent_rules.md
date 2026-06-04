# Intent management

**Golden rule:** only one active intent per session per turn (`scenario_state.active` non-null).

Before opening a new scenario while another is active:
1. **Normal closure** — exit criteria met → `scenario_state: null`, persist ticket/feedback/action if needed, then start new scenario at `step: 1` with empty `collected`.
2. **Explicit abandon** — user cancels → `scenario_state: null` with short confirmation in `reply`.
3. **Intent change** — do not switch silently; ask whether to continue the current scenario or switch.
4. **Incidental FAQ** during a scenario — answer briefly without clearing state unless the FAQ becomes the main topic.

On exit or abandon: set `scenario_state` to `null`. Increment `step` only when the same scenario continues.
