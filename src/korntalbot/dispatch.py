from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .discord_client import Webhook
from .ical import fetch_events
from .models import CalendarEvent
from .render import attendance_key, availability_payload, dashboard_payload, event_notification_payload, friday_reminder_payload, next_event_payload


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
        if any(word in summary for word in ("whoop", "race", "rennen")) or any(word in categories for word in ("race", "rennen")):
            return False
        size = re.search(r'\b3\s*[-–—−.]\s*5\b|\b[35]\s*(?:zoll|inch|["″])', summary)
        sko = "sko" in event.location.casefold() or "sporthalle korntal" in event.location.casefold()
        category_size = "3 zoll" in categories or "5 zoll" in categories
        training = "training" in summary or "fliegen" in summary or event.cancelled
        return sko and training and (bool(size) or category_size)
    if feed_key == "whooprace":
        return "race" in summary or "rennen" in summary or "race" in categories or "rennen" in categories
    return False


FEEDS = (
    Feed("training-whoop", "Training Whoop", "KORNTAL_WHOOP_WEBHOOK_URL", "whoop.json", "Friday Tiny Whoop / Training Whoop at Aula-Halle Korntal.", lambda event: _matches("training-whoop", event)),
    Feed("training-3-5-zoll", "Training 3–5 Zoll", "KORNTAL_3_5_WEBHOOK_URL", "3-5-zoll.json", "Training for 3–5 inch drones at Sporthalle Korntal (SKO).", lambda event: _matches("training-3-5-zoll", event)),
    Feed("whooprace", "Whooprace", "KORNTAL_RACE_WEBHOOK_URL", "whooprace.json", "Whooprace and race events published by TSV Korntal FPV.", lambda event: _matches("whooprace", event)),
)


def sync_feed(feed: Feed, webhook_url: str, state_dir: Path, now: datetime | None = None,
              *, source_events: list[CalendarEvent] | None = None) -> dict[str, object]:
    events = sorted([event for event in (fetch_events() if source_events is None else source_events) if feed.matcher(event)],
                    key=lambda event: (event.start, event.identity))
    local_now = (now or datetime.now(ZoneInfo("Europe/Berlin"))).astimezone(ZoneInfo("Europe/Berlin"))
    upcoming = [event for event in events if (event.end or event.start) > local_now]
    webhook = Webhook(webhook_url, state_dir / feed.state_file)
    dashboard_changed = webhook.sync_message("dashboard", dashboard_payload(upcoming, feed.label, feed.channel_description))
    if feed.key == "training-3-5-zoll":
        return _sync_sko(feed, webhook, upcoming, events, local_now, dashboard_changed)
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


def _sync_sko(feed: Feed, webhook: Webhook, upcoming: list[CalendarEvent], events: list[CalendarEvent],
              now: datetime, dashboard_changed: bool) -> dict[str, object]:
    state = webhook._state()
    known = state.setdefault("events", {})
    # On first import, group dates to avoid one message for every winter appointment.
    notifications: dict[str, list[CalendarEvent]] = {"new": [], "updated": [], "cancelled": []}
    for event in events:
        previous = known.get(event.identity)
        if previous is None and event not in upcoming:
            continue
        if previous is None or previous["fingerprint"] != event.fingerprint:
            kind = "cancelled" if event.cancelled else "updated" if previous else "new"
            notifications[kind].append(event)
    announced = 0
    for kind, pending in notifications.items():
        for offset in range(0, len(pending), 6):
            batch = pending[offset:offset + 6]
            message_id = webhook.publish_new(event_notification_payload(batch, feed.label, kind))
            for event in batch:
                known[event.identity] = {"fingerprint": event.fingerprint, "messageId": message_id}
            webhook._save(state)
            announced += len(batch)

    availability_updated = 0
    reminders_sent = 0
    monday = now.date() - timedelta(days=now.weekday())
    for event in events:
        slot = f"availability:{event.identity}"
        record = webhook._state().get(slot)
        in_week = monday <= event.event_date < monday + timedelta(days=7)
        due = now < event.start and in_week and not event.cancelled
        if due:
            key = attendance_key(event)
            changed = bool(record and record.get("nativePoll") and record.get("eventKey") != key)
            availability_updated += webhook.sync_poll(slot, availability_payload(event, feed.label, now, rescheduled=changed), key)
            if now.weekday() >= 4 and event.event_date.weekday() in {5, 6}:
                current = webhook._state()
                poll_url = webhook.message_url(current[slot]["messageId"])
                dashboard_url = webhook.message_url(current["dashboard"]["messageId"])
                reminder_slot = f"friday:{event.identity}:{key}"
                reminders_sent += webhook.sync_message(reminder_slot, friday_reminder_payload(
                    event, feed.label, poll_url, dashboard_url, upcoming))
    return {"feed": feed.key, "events": len(upcoming), "dashboardUpdated": dashboard_changed,
            "eventsAnnounced": announced, "availabilityUpdated": availability_updated, "fridayRemindersUpdated": reminders_sent}
