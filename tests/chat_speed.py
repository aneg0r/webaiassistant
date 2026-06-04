"""Optional latency benchmark for POST /agent/prompt (requires running server + API key)."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

try:
    import httpx
except ImportError:
    print("Install httpx to run chat_speed.py", file=sys.stderr)
    sys.exit(1)

BASE = os.environ.get("CHAT_SPEED_BASE", "http://127.0.0.1:7750")
URL = f"{BASE.rstrip('/')}/agent/prompt"


def main() -> None:
    sid = str(uuid.uuid4())
    payload = {"prompt": "What is the warranty?", "sessionId": sid, "messages": []}
    t0 = time.perf_counter()
    with httpx.Client(timeout=60.0) as client:
        r = client.post(URL, json=payload)
    elapsed = time.perf_counter() - t0
    print(json.dumps({"status": r.status_code, "elapsed_s": round(elapsed, 3)}, indent=2))
    if r.is_success:
        print(r.json().get("reply", "")[:200])


if __name__ == "__main__":
    main()
