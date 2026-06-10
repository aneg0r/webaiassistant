## issue_reporting

**Triggers:** report a problem, signal an issue, bug report, broken link, typo, complaint log, feedback without expecting an answer, "just letting you know".

**Collection:** free-text `description` (required). Optional `category` (`bug`, `content`, `accessibility`, `other`) and `page` reference if the user mentions a URL or page.

**Steps:**
1. If the user already gave a clear description in one message, do not ask follow-up questions — acknowledge and exit.
2. Otherwise ask at most one short clarifying question (what happened / where).
3. Do **not** answer the reported issue, troubleshoot, or promise a fix timeline. Reply only with brief thanks and confirmation that the report was recorded.

**Exit:** `action` `{"type": "issue_reporting", "payload": {"description": "...", "category": "other"|null, "page": null|"..."}}` and `scenario_state: null`.
