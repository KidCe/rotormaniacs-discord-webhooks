from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


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
        return self.start.date()

    @property
    def fingerprint(self) -> str:
        return "|".join((self.summary, self.start.isoformat(), self.location, self.url, str(self.cancelled)))
