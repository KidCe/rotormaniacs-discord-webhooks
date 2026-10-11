from __future__ import annotations

import os
import sys
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from korntalbot.dispatch import FEEDS, sync_feed  # noqa: E402
from korntalbot.ical import fetch_events  # noqa: E402
from korntalbot.discord_client import Webhook, WebhookError  # noqa: E402
from korntalbot.render import availability_payload  # noqa: E402


def _env_file() -> dict[str, str]:
    path = PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the TSV Korntal calendar to Discord.")
    parser.add_argument("command", choices=["sync", "verify-poll"])
    parser.add_argument("--dry-run", action="store_true", help="Read the live calendar without posting or saving state.")
    parser.add_argument("--feed", choices=[feed.key for feed in FEEDS], help="Sync or preview one channel only.")
    args = parser.parse_args()
    values = _env_file()
    state_dir = PROJECT_ROOT / "data" / "korntal"
    source_events = fetch_events()
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    if args.command == "verify-poll":
        if args.dry_run:
            parser.error("verify-poll is a live API check; use sync --dry-run for a read-only preview")
        feed = FEEDS[1]
        webhook_url = os.environ.get(feed.webhook_env, values.get(feed.webhook_env, ""))
        if not webhook_url:
            raise WebhookError(f"{feed.webhook_env} is not configured.")
        event = next(event for event in source_events if feed.matcher(event) and event.start > now and not event.cancelled)
        Webhook(webhook_url, state_dir / feed.state_file).verify_poll(availability_payload(event, feed.label, now))
        print("Verified native webhook poll: ✅ / ❌ / 🤔, single choice. Temporary test message removed.")
        return 0
    failed = False
    for feed in FEEDS:
        if args.feed and feed.key != args.feed:
            continue
        if args.dry_run:
            upcoming = [event for event in source_events if feed.matcher(event) and (event.end or event.start) > now]
            print(json.dumps({"feed": feed.key, "events": len(upcoming), "appointments": [
                {"id": event.identity, "title": event.summary, "start": event.start.isoformat(),
                 "end": event.end.isoformat() if event.end else None, "cancelled": event.cancelled}
                for event in upcoming]}, ensure_ascii=False, indent=2))
            continue
        webhook_url = os.environ.get(feed.webhook_env, values.get(feed.webhook_env, ""))
        if not webhook_url:
            print(f"ERROR: {feed.key}: {feed.webhook_env} is not configured.", file=sys.stderr)
            failed = True
            continue
        try:
            print(sync_feed(feed, webhook_url, state_dir, now, source_events=source_events))
        except Exception as exc:
            # Do not let a failed feed suppress other channels or leak webhook credentials.
            detail = str(exc) if isinstance(exc, WebhookError) else type(exc).__name__
            print(f"ERROR: {feed.key}: synchronization failed ({detail}).", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
