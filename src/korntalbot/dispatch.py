from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .discord_client import Webhook
from .ical import fetch_events
from .models import CalendarEvent
from .render import dashboard_payload, next_event_payload


@dataclass(frozen=True, slots=True)
class Feed:
    key: str
    label: str
    webhook_env: str
    state_file: str
    channel_description: str
    matcher: Callable[[CalendarEvent], bool]


def _matches(feed_key: str, event: CalendarEvent) -> bool:
    summary = event.summary.casefold()
    categories = " ".join(event.categories).casefold()
    if feed_key == "training-whoop":
        return "whoop" in summary and "race" not in summary and "whooprace" not in summary
    if feed_key == "training-3-5-zoll":
        return "3-5" in summary or "3.5" in summary or "5 zoll" in summary
    if feed_key == "whooprace":
        return "race" in summary or "rennen" in summary or "race" in categories or "rennen" in categories
    return False


FEEDS = (
    Feed("training-whoop", "Training Whoop", "KORNTAL_WHOOP_WEBHOOK_URL", "whoop.json", "Friday Tiny Whoop / Training Whoop at Aula-Halle Korntal.", lambda event: _matches("training-whoop", event)),
    Feed("training-3-5-zoll", "Training 3–5 Zoll", "KORNTAL_3_5_WEBHOOK_URL", "3-5-zoll.json", "Training for 3–5 inch drones at Sporthalle Korntal (SKO).", lambda event: _matches("training-3-5-zoll", event)),
    Feed("whooprace", "Whooprace", "KORNTAL_RACE_WEBHOOK_URL", "whooprace.json", "Whooprace and race events published by TSV Korntal FPV.", lambda event: _matches("whooprace", event)),
)


def sync_feed(feed: Feed, webhook_url: str, state_dir: Path, now: datetime | None = None) -> dict[str, object]:
    events = [event for event in fetch_events() if feed.matcher(event)]
    today = (now or datetime.now(ZoneInfo("Europe/Berlin"))).date()
    upcoming = [event for event in events if event.event_date >= today]
    webhook = Webhook(webhook_url, state_dir / feed.state_file)
    dashboard_changed = webhook.sync_message("dashboard", dashboard_payload(upcoming, feed.label, feed.channel_description))
    state = webhook._state()
    next_record = state.get("next", {})
    next_event = upcoming[0] if upcoming else None
    next_key = f"{next_event.uid}|{next_event.fingerprint}" if next_event else "none"
    old_key = str(next_record.get("eventKey", "")) if isinstance(next_record, dict) else ""
    next_changed = False
    if next_event is None:
        if isinstance(next_record, dict) and next_record.get("messageId"):
            webhook.delete_message(str(next_record["messageId"]))
            state.pop("next", None)
            webhook._save(state)
            next_changed = True
    elif next_key != old_key:
        next_changed = webhook.replace_message("next", next_event_payload(next_event, feed.label))
        state = webhook._state()
        state["next"]["eventKey"] = next_key
        webhook._save(state)
    return {"feed": feed.key, "events": len(upcoming[:6]), "dashboardUpdated": dashboard_changed, "nextMessageReplaced": next_changed}
