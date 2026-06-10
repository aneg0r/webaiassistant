## feedback_page

**Triggers:** rate this page, feedback on the site, review, stars, « Donnez votre avis » widget.

**Widget flow (fixed UI, same data as chat exit):**
1. Scope — product (`reference.scope`: `product`), site web (`site`, `page`: `/`), or this page (`page`, current URL path).
2. Experience — notation 1–5 (required), optional `remarques` comment.

**Collection (chat):** same fields via `collected` when the user types instead of using the widget.

**Exit:** fill `feedback` object `{ reference: { scope, page }, notation, remarques, ancien_texte: "", nouveau_texte: "" }` and `scenario_state: null`. Widget may POST `/agent/feedback-page` instead of the LLM when the form is used.
