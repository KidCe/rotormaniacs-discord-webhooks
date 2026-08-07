from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True, slots=True)
class Match:
    match_date: date
    kick_off: time | None
    home_team: str
    away_team: str
    competition: str
    match_type: str
    match_number: str
    venue: str
    url: str
    status: str = ""

    @property
    def identity(self) -> str:
        return self.match_number or self.url


@dataclass(frozen=True, slots=True)
class SourceResult:
    matches: tuple[Match, ...]
    source_match_count: int
    fetched_at: datetime
    source_url: str

