from __future__ import annotations

from datetime import datetime

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
            "description": "Published training dates at Sporthalle Korntal (SKO).",
            "color": 0xE74C3C if kind == "cancelled" else 0x2E8B57,
            "fields": [{"name": f"{index}. Training", "value": _event_value(event), "inline": False}
                       for index, event in enumerate(events, 1)],
            "footer": {"text": "Automatic update · Source: fpvkorntal.de calendar"},
        }],
    }


def availability_payload(event: CalendarEvent, label: str, *, rescheduled: bool = False) -> dict[str, object]:
    if event.cancelled:
        title = f"❌ CANCELLED — {label}"
        content = "This training has been cancelled. The attendance request is no longer active."
    else:
        title = f"📅 {'RESCHEDULED' if rescheduled else 'THIS WEEK'} — {label} AT SKO"
        content = (
            "Training at Sporthalle Korntal (SKO) has been rescheduled.\n"
            if rescheduled else "This week there is another training at Sporthalle Korntal (SKO).\n"
        ) + "Who will join us and fly?\n✅ I will attend   ❌ I will not attend\nPlease react directly to this message."
    return {
        "username": "TSV Korntal FPV Kalender",
        "allowed_mentions": {"parse": []},
        "content": content,
        "embeds": [{
            "title": title, "description": _event_value(event),
            "color": 0xE74C3C if event.cancelled else 0x3498DB,
            "footer": {"text": "Manual attendance poll · React with ✅ or ❌"},
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
