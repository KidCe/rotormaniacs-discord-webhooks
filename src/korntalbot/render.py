from __future__ import annotations

from datetime import datetime
from math import ceil
from zoneinfo import ZoneInfo

from .models import CalendarEvent


def _timestamp(value: datetime) -> str:
    return f"<t:{int(value.timestamp())}:F>"


def _event_value(event: CalendarEvent, *, include_link: bool = True) -> str:
    status = "\n❌ **CANCELLED ON THE CALENDAR WEBSITE**" if event.cancelled else ""
    location = event.location or "Location not specified"
    link = f"\n[Open calendar entry]({event.url})" if include_link and event.url else ""
    end = f" – <t:{int(event.end.timestamp())}:t>" if event.end else ""
    return f"{_timestamp(event.start)}{end}\n**{event.summary}**{status}\n📍 {location}{link}"


def event_notification_payload(events: list[CalendarEvent], label: str, kind: str) -> dict[str, object]:
    return {
        "username": "TSV Korntal FPV Kalender",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": f"📅 {label} — {kind.upper()} TRAINING DATES",
            "description": (
                "This training is cancelled. Please disregard its earlier attendance polls."
                if kind == "cancelled" else
                "Training details have changed. Check the dates below; polls for an earlier time no longer apply."
                if kind == "updated" else "Published training dates at Sporthalle Korntal (SKO)."
            ),
            "color": 0xE74C3C if kind == "cancelled" else 0x2E8B57,
            "fields": [{"name": f"{index}. Training", "value": _event_value(event), "inline": False}
                       for index, event in enumerate(events, 1)],
            "footer": {"text": "Automatic update · Source: fpvkorntal.de calendar"},
        }],
    }


def attendance_key(event: CalendarEvent) -> str:
    return "|".join((event.start.isoformat(), event.end.isoformat() if event.end else "", event.location))


def availability_payload(event: CalendarEvent, label: str, now: datetime, *, rescheduled: bool = False) -> dict[str, object]:
    start = event.start.astimezone(ZoneInfo("Europe/Berlin"))
    hours = max(1, min(32 * 24, ceil((event.start.timestamp() - now.timestamp()) / 3600)))
    title = f"📅 {'UPDATED DATE' if rescheduled else 'THIS WEEK'} — {label} AT SKO"
    content = (
        "The training time has changed. Please vote again in this new poll.\n"
        if rescheduled else "This week there is another training at Sporthalle Korntal (SKO).\n"
    ) + "Who will join us and fly? Select your answer in the poll below."
    return {
        "username": "TSV Korntal FPV Kalender",
        "allowed_mentions": {"parse": []},
        "content": content,
        "embeds": [{
            "title": title, "description": _event_value(event),
            "color": 0x3498DB,
            "footer": {"text": "Attendance poll · One answer per person · Times: Europe/Berlin"},
        }],
        "poll": {
            "question": {"text": f"Will you fly at SKO on {start.strftime('%a %d %b %Y, %H:%M')}?"},
            "answers": [
                {"poll_media": {"text": "I will attend", "emoji": {"name": "✅"}}},
                {"poll_media": {"text": "I will not attend", "emoji": {"name": "❌"}}},
                {"poll_media": {"text": "Not sure yet", "emoji": {"name": "🤔"}}},
            ],
            "duration": hours, "allow_multiselect": False, "layout_type": 1,
        },
    }


def friday_reminder_payload(event: CalendarEvent, label: str, poll_url: str, dashboard_url: str,
                            upcoming: list[CalendarEvent]) -> dict[str, object]:
    following = [candidate for candidate in upcoming if candidate.start > event.start and not candidate.cancelled][:3]
    return {
        "username": "TSV Korntal FPV Kalender",
        "allowed_mentions": {"parse": []},
        "content": f"Training at SKO this weekend! Please confirm whether you will join us.\n{poll_url}",
        "embeds": [{
            "title": f"📅 THIS WEEKEND — {label}",
            "description": _event_value(event) + f"\n\n[Vote in the attendance poll]({poll_url})"
                           + f" · [Full schedule]({dashboard_url})",
            "color": 0xE67E22,
            "fields": [{"name": "Following training dates", "value": "\n".join(_timestamp(e.start) for e in following),
                        "inline": False}] if following else [],
            "footer": {"text": "Weekend reminder · Use the existing poll so all votes stay together"},
        }],
    }


def dashboard_payload(events: list[CalendarEvent], label: str, channel_description: str) -> dict[str, object]:
    visible = events[:6]
    fields = [{"name": f"{index}. {_timestamp(event.start)}", "value": _event_value(event), "inline": False} for index, event in enumerate(visible, 1)]
    description = channel_description
    if not visible:
        description += "\n\nNo upcoming events are currently published."
    return {
        "username": "TSV Korntal FPV Kalender",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": f"{label} — Upcoming schedule", "description": description,
            "color": 0x2E8B57 if visible else 0x718096, "fields": fields,
            "footer": {"text": "Automatic update · Source: fpvkorntal.de calendar"},
        }],
    }


def next_event_payload(event: CalendarEvent, label: str) -> dict[str, object]:
    return {
        "username": "TSV Korntal FPV Kalender", "allowed_mentions": {"parse": []},
        "content": "✅ Interesse / Teilnahme   ❌ kein Interesse / keine Teilnahme\nBitte direkt auf diese Nachricht reagieren.",
        "embeds": [{
            "title": f"📅 Next {label} appointment", "description": _event_value(event),
            "color": 0xE67E22 if not event.cancelled else 0xE74C3C,
            "footer": {"text": "React with ✅ or ❌ to show interest"},
        }],
    }
