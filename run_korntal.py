from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from korntalbot.dispatch import FEEDS, sync_feed  # noqa: E402


def _env_file() -> dict[str, str]:
    path = PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


if len(sys.argv) < 2 or sys.argv[1] != "sync":
    raise SystemExit("Usage: python run_korntal.py sync")

values = _env_file()
state_dir = PROJECT_ROOT / "data" / "korntal"
for feed in FEEDS:
    webhook_url = os.environ.get(feed.webhook_env, values.get(feed.webhook_env, ""))
    if not webhook_url:
        print(f"Skipped {feed.key}: {feed.webhook_env} is not configured.")
        continue
    print(sync_feed(feed, webhook_url, state_dir))
