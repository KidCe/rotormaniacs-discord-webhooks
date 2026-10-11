from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    uid: str
    summary: str
    start: datetime
    end: datetime | None
    location: str
    url: str
    categories: tuple[str, ...]
    cancelled: bool = False

    @property
    def event_date(self) -> date:
        return self.start.astimezone(ZoneInfo("Europe/Berlin")).date()

    @property
    def identity(self) -> str:
        # The Events Calendar embeds mutable start/end timestamps in its UID.
        match = re.fullmatch(r"(\d+)-\d+-\d+@fpvkorntal\.de", self.uid)
        return f"fpvkorntal:{match.group(1)}" if match else self.uid

    @property
    def fingerprint(self) -> str:
        return "|".join((self.summary, self.start.isoformat(), self.end.isoformat() if self.end else "", self.location, self.url, str(self.cancelled)))
