from __future__ import annotations

import io
import logging
import re
import time as time_module
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag
from fontTools.agl import toUnicode
from fontTools.ttLib import TTFont

from .config import Config
from .models import Match, SourceResult


LOGGER = logging.getLogger(__name__)
USER_AGENT = "SV07-Eich-Pitch-Bot/1.0 (private community schedule; low-frequency access)"
CANCELLED_TERMS = (
    "absetzung",
    "abgesagt",
    "annullierung",
    "annuliert",
    "ausfall",
    "nichtantritt",
    "spielfrei",
)


class SourceError(RuntimeError):
    pass


def _clean(value: str) -> str:
    value = unescape(value).replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", value).strip()


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", _clean(value)).casefold()


class FussballFontDecoder:
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self._maps: dict[str, dict[int, str]] = {}

    def decode(self, font_id: str, encoded: str) -> str:
        mapping = self._maps.get(font_id)
        if mapping is None:
            mapping = self._load_mapping(font_id)
            self._maps[font_id] = mapping

        decoded: list[str] = []
        for character in encoded:
            codepoint = ord(character)
            if codepoint in mapping:
                decoded.append(mapping[codepoint])
            elif 0xE000 <= codepoint <= 0xF8FF:
                raise SourceError(f"FUSSBALL.DE font {font_id} contains an unknown glyph.")
            else:
                decoded.append(character)
        return "".join(decoded)

    def _load_mapping(self, font_id: str) -> dict[int, str]:
        if not re.fullmatch(r"[a-z0-9]+", font_id, flags=re.IGNORECASE):
            raise SourceError("FUSSBALL.DE returned an invalid font identifier.")
        url = f"https://www.fussball.de/export.fontface/-/format/ttf/id/{font_id}/type/font"
        payload = _download(url, self.timeout_seconds)
        try:
            font = TTFont(io.BytesIO(payload), lazy=False)
            cmap = font.getBestCmap() or {}
            mapping: dict[int, str] = {}
            for codepoint, glyph_name in cmap.items():
                decoded = toUnicode(glyph_name)
                if decoded:
                    mapping[codepoint] = decoded
            font.close()
        except Exception as exc:
            raise SourceError("FUSSBALL.DE returned an unreadable obfuscation font.") from exc
        if not mapping:
            raise SourceError("FUSSBALL.DE returned an empty obfuscation font.")
        return mapping


def _download(url: str, timeout_seconds: int, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                if response.status != 200:
                    raise SourceError(f"FUSSBALL.DE returned HTTP {response.status}.")
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < attempts:
                time_module.sleep(attempt)
    status = last_error.code if isinstance(last_error, HTTPError) else "network error"
    raise SourceError(f"FUSSBALL.DE could not be read ({status}).") from last_error


class FussballScheduleClient:
    def __init__(self, config: Config, decoder: FussballFontDecoder | None = None) -> None:
        self.config = config
        self.decoder = decoder or FussballFontDecoder()

    def fetch(self, today: date | None = None) -> SourceResult:
        local_today = today or datetime.now(self.config.timezone).date()
        end_date = local_today + timedelta(days=self.config.lookahead_days)
        source_url = self._source_url(local_today, end_date)
        LOGGER.info("Reading the club schedule from FUSSBALL.DE.")
        html = _download(source_url, timeout_seconds=30).decode("utf-8", errors="strict")
        matches, source_count = self.parse(html, local_today, end_date)
        return SourceResult(
            matches=tuple(matches),
            source_match_count=source_count,
            fetched_at=datetime.now(timezone.utc),
            source_url=source_url,
        )

    def _source_url(self, start_date: date, end_date: date) -> str:
        return (
            "https://www.fussball.de/vereinsspielplan.druck/-/"
            f"datum-bis/{end_date.isoformat()}/datum-von/{start_date.isoformat()}/"
            f"id/{self.config.club_id}/match-type/-1/max/999/mode/PRINT/show-venues/true"
        )

    def parse(self, html: str, start_date: date, end_date: date) -> tuple[list[Match], int]:
        soup = BeautifulSoup(html, "html.parser")
        competition_rows = soup.select("tr.row-competition")
        if not competition_rows:
            page_text = _normalized(soup.get_text(" ", strip=True))
            no_games_markers = ("keine spiele", "keine begegnungen", "keine ergebnisse")
            if not any(marker in page_text for marker in no_games_markers):
                raise SourceError("The FUSSBALL.DE schedule layout could not be recognized.")
            return [], 0

        matches: list[Match] = []
        identities: set[str] = set()
        inherited_date: date | None = None
        for competition_row in competition_rows:
            try:
                match, inherited_date = self._parse_match(competition_row, inherited_date)
            except SourceError:
                raise
            except Exception as exc:
                raise SourceError("A FUSSBALL.DE fixture could not be parsed.") from exc

            if match is None or not start_date <= match.match_date <= end_date:
                continue
            if not self._is_target_venue(match.venue):
                continue
            if any(term in _normalized(match.status) for term in CANCELLED_TERMS):
                continue
            if match.identity in identities:
                continue
            identities.add(match.identity)
            matches.append(match)

        matches.sort(key=lambda item: (item.match_date, item.kick_off or time.max, item.home_team))
        return matches, len(competition_rows)

    def _parse_match(self, competition_row: Tag, inherited_date: date | None) -> tuple[Match | None, date | None]:
        date_cell = competition_row.select_one("td.column-date")
        if date_cell is None:
            return None, inherited_date
        date_text = self._decode_date_cell(date_cell)
        # FUSSBALL.DE can list provisional fixtures without a date. They cannot
        # occupy a specific day yet, so retain the successful read and skip them.
        if not date_text:
            return None, inherited_date
        date_match = re.search(r"(\d{2}\.\d{2}\.(?:\d{4}|\d{2}))(?:\s*[|\-]\s*(\d{2}:\d{2}))?", date_text)
        if date_match:
            date_format = "%d.%m.%Y" if len(date_match.group(1).rsplit(".", 1)[1]) == 4 else "%d.%m.%y"
            match_date = datetime.strptime(date_match.group(1), date_format).date()
            kick_off_text = date_match.group(2)
        else:
            # The print view omits a repeated date when several fixtures share a day.
            # In that case the cell contains only the next kick-off time.
            time_match = re.fullmatch(r"\s*(\d{2}:\d{2})\s*", date_text)
            if not time_match or inherited_date is None:
                raise SourceError(f"Could not decode a fixture date: {date_text!r}")
            match_date = inherited_date
            kick_off_text = time_match.group(1)
        kick_off = datetime.strptime(kick_off_text, "%H:%M").time() if kick_off_text else None

        competition_node = competition_row.select_one("td.column-team")
        competition = _clean(competition_node.get_text(" ", strip=True)) if competition_node else ""
        metadata_cells = competition_row.find_all("td")
        metadata = _clean(metadata_cells[-1].get_text(" ", strip=True)) if metadata_cells else ""
        metadata_parts = [part.strip() for part in metadata.split("|")]
        match_type = metadata_parts[0] if metadata_parts else ""
        number_match = re.search(r"\b\d{6,}\b", metadata)
        match_number = number_match.group(0) if number_match else ""

        match_row = competition_row.find_next_sibling("tr")
        if not isinstance(match_row, Tag):
            raise SourceError("A fixture row is missing below its date row.")
        team_nodes = match_row.select(".club-name")
        if len(team_nodes) < 2:
            return None, match_date
        home_team = _clean(team_nodes[0].get_text(" ", strip=True))
        away_team = _clean(team_nodes[1].get_text(" ", strip=True))
        game_link = match_row.select_one('a[href*="/spiel/"]')
        game_url = str(game_link.get("href", "")) if game_link else ""
        status_node = match_row.select_one(".column-score .info-text")
        status = _clean(status_node.get_text(" ", strip=True)) if status_node else ""

        venue = ""
        venue_row = match_row.find_next_sibling("tr")
        if isinstance(venue_row, Tag) and "row-venue" in (venue_row.get("class") or []):
            for div in venue_row.find_all("div"):
                candidate = _clean(div.get_text(" ", strip=True))
                if candidate.casefold().startswith("spielstätte:"):
                    venue = candidate.split(":", 1)[1].strip()
                    break

        return Match(
            match_date=match_date,
            kick_off=kick_off,
            home_team=home_team,
            away_team=away_team,
            competition=competition,
            match_type=match_type,
            match_number=match_number,
            venue=venue,
            url=game_url,
            status=status,
        ), match_date

    def _decode_date_cell(self, date_cell: Tag) -> str:
        spans = date_cell.select("span[data-obfuscation]")
        if not spans:
            return _clean(date_cell.get_text(" ", strip=True))
        pieces: list[str] = []
        for span in spans:
            font_id = str(span.get("data-obfuscation", ""))
            encoded = span.get_text("", strip=False)
            pieces.append(self.decoder.decode(font_id, encoded))
        return _clean("".join(pieces))

    def _is_target_venue(self, venue: str) -> bool:
        normalized_venue = _normalized(venue)
        return bool(normalized_venue) and any(
            _normalized(term) in normalized_venue for term in self.config.venue_match_terms
        )
