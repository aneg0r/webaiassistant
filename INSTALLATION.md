# Installation & configuration



Technical guide to run and deploy this RapidAgent instance. For product overview, see [README.md](README.md).



## Quick start



Run these commands from the `webaiassistant/` directory:



```bash

python -m venv .venv

.venv\Scripts\activate   # Windows

pip install -r requirements.txt

copy .env.example .env     # set GEMINI_API_KEY

uvicorn app.main:app --reload --port 7750

```



- Demo: http://127.0.0.1:7750/

- Full chat: http://127.0.0.1:7750/chat.htm
- Minimal embed demo: http://127.0.0.1:7750/example.htm

- Admin: http://127.0.0.1:7750/backoffice/
- Config editor: http://127.0.0.1:7750/admin/configuration.htm



## Choose your perimeter



Edit `backoffice/perimeter.json` directly.



- `product_type`: `physical` or `service`

- `features.*`: enable/disable scenarios (`newsletter`, `survey`, `feedback_page`, etc.)



Only matching files under `backoffice/scenarii/` are injected into the prompt.



Optional env overrides: `FEATURE_INSTALLATION=false`, `FEATURE_NEWSLETTER=true`, …



Override paths: `BACKOFFICE_DIR`, `VAR_DIR`, `PERIMETER_FILE` (see `.env.example`).



## Embed the widgets



One CSS/JS bundle for chat and page feedback (`feedback_page` scenario):



```html

<link rel="stylesheet" href="https://your-host/static/widget/chat-widget.css" />

<div id="ixfeedback-widget-root"></div>

<!-- chat HTML: see static/index.htm #ixchat-widget-root -->

<script>

  window.CHAT_API_URL = "https://your-host/agent/prompt";

  window.CHAT_WELCOME_TEXT = "Hello!";

  window.FEEDBACK_PAGE_API_URL = "https://your-host/agent/feedback-page";

</script>

<script src="https://your-host/static/agent.js"></script>

<script src="https://your-host/static/widget/chat-widget.js"></script>

```



Omit `#ixfeedback-widget-root` if you only need the chat. The feedback tab mounts automatically when the element is present.



## API (client)



| Method | Path | Role |

|--------|------|------|

| POST | `/agent/prompt` | Send message `{ prompt, sessionId, messages? }` |

| POST | `/agent/feedback-page` | Widget feedback `{ scope, notation, remarques?, page?, sessionId? }` |

| GET | `/agent/prompt?sessionId=` | Poll transcript (5s in widget) |



## API (admin, authenticated)



| Method | Path |

|--------|------|

| GET | `/backoffice/sessions/list` |

| GET | `/backoffice/sessions/file?file=` | Raw transcript JSON |

| POST | `/backoffice/sessions/archive` `{ "file": "…json" }` |

| GET | `/backoffice/records/list?source=` `actions` \| `feedback` \| `surveys` \| `feedback_agent` |

| GET | `/backoffice/records/file?source=&file=` |

| POST | `/backoffice/human` |

| POST | `/backoffice/human-in-charge` |

| GET | `/backoffice/faq` |

| PUT | `/backoffice/faq` `{ "entries": [{ "question", "answer" }] }` |

| GET | `/backoffice/wiki` |

| PUT | `/backoffice/wiki` `{ "content": "…" }` |

| GET | `/backoffice/scenarii/list` |

| GET | `/backoffice/scenarii/file?file=` |

| PUT | `/backoffice/scenarii/file?file=` `{ "content": "…" }` |

| GET | `/backoffice/scenarii/examples/list` |

| GET | `/backoffice/scenarii/examples/file?file=` |

| POST | `/backoffice/scenarii/examples/copy?file=` `&overwrite=true` optional |



## Admin security (nginx Basic + `.env` token)



Three layers work together:



1. **nginx** — HTTP Basic on `/backoffice/`, `/admin/`, and `/backoffice/*` (recommended). The browser sends `Authorization: Basic` on every request (`credentials: "same-origin"` in the admin UI).

2. **Application Basic** — `ADMIN_USER` and `ADMIN_PASSWORD` in `.env` (same credentials as nginx, or used without nginx).

3. **Application token** — `ADMIN_TOKEN` in `.env`. The admin pages load [`static/admin/admin-auth.js`](static/admin/admin-auth.js), which stores the token in `sessionStorage` and sends header `X-Admin-Token` on API calls (so nginx Basic in `Authorization` is not overwritten). Bearer `Authorization` is also accepted for scripts/API clients.



| `.env` | API `/backoffice/*` | HTML `/backoffice/`, `/admin/configuration.htm` |

|--------|----------------------|-----------------------------------------------------|

| All empty | Open (dev only) | Open |

| `ADMIN_TOKEN` only | Bearer required | Bearer or Basic |

| `ADMIN_USER` + `ADMIN_PASSWORD` only | Basic required | Bearer or Basic |

| **Token + Basic both set** | **Bearer and Basic required** | Bearer **or** Basic (nginx Basic is enough to open the page; token still required for API) |



Runtime data under `var/` is **not** served as static files. Do not expose `/var/` or `/backoffice/scenarii/` publicly except what you intentionally mount.



Also restrict admin URLs by IP in nginx, for example:



```nginx

location ~ ^/(backoffice/|admin/) {

    auth_basic "Admin";

    auth_basic_user_file /etc/nginx/.htpasswd;

    allow 203.0.113.10;

    deny all;

    proxy_pass http://127.0.0.1:7750;

    proxy_set_header Authorization $http_authorization;

}

```



## Editing content



| File | Purpose |

|------|---------|

| `backoffice/faq.json` | Short Q/A |

| `backoffice/faq.json.example` | FAQ template (auto-copied to `faq.json` on first startup if missing) |

| `backoffice/scenarii/*.md` | Local scenario playbooks (gitignored) |

| `backoffice/scenarii.example/*.md` | Scenario templates (full copy to `scenarii/` only on first install when `scenarii/` does not exist) |

| `backoffice/perimeter.json` | Enabled features |

| `backoffice/wiki.md` | Optional long doc (`INJECT_WIKI_IN_PROMPT=true`) |

| `backoffice/wiki.md.example` | Wiki template (auto-copied to `wiki.md` on first startup if missing) |



Public read-only mount: `/backoffice/faq.json` (config files only; no runtime data).



## Tests



```bash

pytest tests/ -q

```



`tests/test_scenarios.py` covers each scenario playbook (`off_topic`, `knowledge_search`, `technical_support`, `customer_service_returns`, `customer_service_order_handling`, `callback_request`, `issue_reporting`, `newsletter`, `survey`, `feedback_page`, `feedback_agent`, `human_escalation`): markdown structure, perimeter gating, JSON parsing, and side-effects where applicable.



Optional live bench (server running + API key):



```bash

python tests/chat_speed.py

```



## Layout



```

app/           Python package (agent, routes, llm)

backoffice/    perimeter, FAQ, scenarii (versioned config)

var/           runtime: sessions, records, session index (gitignored)

static/        widget, chat.htm, admin/agent_admin.htm, admin/configuration.htm

tests/

```



Legacy `chat/` and `data/` paths are read as fallback if present (one-release migration).



Legacy API paths `/api/agent/prompt` and `/apitm/*` remain as compatibility aliases.


