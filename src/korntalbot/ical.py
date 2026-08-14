from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import CalendarEvent


ICAL_URL = "https://fpvkorntal.de/kalender/?ical=1"


def _unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


def _property(line: str, name: str) -> str:
    if not line.startswith(name):
        return ""
    _, _, value = line.partition(":")
    return _unescape(value)


def _datetime(line: str) -> datetime:
    params, separator, value = line.partition(":")
    if not separator:
        value = line
        params = ""
    zone = "Europe/Berlin"
    zone_match = re.search(r"TZID=([^;:]+)", params)
    if zone_match:
        zone = zone_match.group(1)
    if len(value) == 8:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=ZoneInfo(zone))
    parsed = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return parsed.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Berlin"))
    return parsed.replace(tzinfo=ZoneInfo(zone))


def parse_ical(payload: str) -> list[CalendarEvent]:
    lines: list[str] = []
    for raw in payload.replace("\r\n", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    events: list[CalendarEvent] = []
    current: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if current.get("UID") and current.get("DTSTART") and current.get("SUMMARY"):
                summary = current["SUMMARY"]
                events.append(CalendarEvent(
                    uid=current["UID"], summary=summary, start=_datetime(current["DTSTART"]),
                    end=_datetime(current["DTEND"]) if current.get("DTEND") else None,
                    location=current.get("LOCATION", ""), url=current.get("URL", ""),
                    categories=tuple(part.strip() for part in current.get("CATEGORIES", "").split(",") if part.strip()),
                    cancelled="abgesagt" in summary.casefold() or "cancel" in current.get("STATUS", "").casefold(),
                ))
            current = None
        elif current is not None:
            for name in ("UID", "SUMMARY", "DTSTART", "DTEND", "LOCATION", "URL", "CATEGORIES", "STATUS"):
                value = _property(line, name)
                if value:
                    current[name] = value
                    break
    return sorted(events, key=lambda event: (event.start, event.summary.casefold()))


def fetch_events(url: str = ICAL_URL) -> list[CalendarEvent]:
    request = Request(url, headers={"User-Agent": "TSV-Korntal-Calendar-Webhook/1.0", "Accept": "text/calendar"})
    with urlopen(request, timeout=30) as response:
        return parse_ical(response.read().decode("utf-8-sig"))
