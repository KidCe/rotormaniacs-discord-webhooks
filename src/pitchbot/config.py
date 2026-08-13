from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    pass


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Invalid .env entry on line {line_number}.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false.")


def _int(value: str, name: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number.") from exc
    if not minimum <= result <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return result


@dataclass(frozen=True, slots=True)
class Config:
    project_root: Path
    webhook_url: str
    publish_enabled: bool
    club_id: str
    club_name: str
    venue_match_terms: tuple[str, ...]
    venue_display_name: str
    lookahead_days: int
    sync_interval_minutes: int
    max_events: int
    timezone_name: str
    status_host: str
    status_port: int
    state_path: Path

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def can_publish(self) -> bool:
        return self.publish_enabled and bool(self.webhook_url)

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Config":
        root = PROJECT_ROOT
        file_values = _read_env_file(env_file or root / ".env")

        def value(name: str, default: str) -> str:
            return os.environ.get(name, file_values.get(name, default)).strip()

        terms = tuple(part.strip() for part in value(
            "VENUE_MATCH_TERMS", "Sportplatz Aich;Heideweg 60;72631 Aichtal"
        ).split(";") if part.strip())
        if not terms:
            raise ConfigError("VENUE_MATCH_TERMS must contain at least one term.")

        club_id = value("FUSSBALL_CLUB_ID", "00ES8GNA1O000099VV0AG08LVUPGND5I")
        if not re.fullmatch(r"[A-Z0-9]{20,40}", club_id, flags=re.IGNORECASE):
            raise ConfigError("FUSSBALL_CLUB_ID does not look like a valid club ID.")

        timezone_name = value("TIMEZONE", "Europe/Berlin")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Unknown timezone: {timezone_name}") from exc

        webhook_url = value("DISCORD_WEBHOOK_URL", "")
        if webhook_url:
            parsed = urlparse(webhook_url)
            allowed_hosts = {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
            if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
                raise ConfigError("DISCORD_WEBHOOK_URL must be an HTTPS Discord webhook URL.")
            if not re.match(r"^/api(?:/v\d+)?/webhooks/\d+/[^/]+/?$", parsed.path):
                raise ConfigError("DISCORD_WEBHOOK_URL does not have the expected webhook path.")

        return cls(
            project_root=root,
            webhook_url=webhook_url,
            publish_enabled=_bool(value("PUBLISH_ENABLED", "true"), "PUBLISH_ENABLED"),
            club_id=club_id,
            club_name=value("FUSSBALL_CLUB_NAME", "SV Aich"),
            venue_match_terms=terms,
            venue_display_name=value("VENUE_DISPLAY_NAME", "Sportplatz Aich"),
            lookahead_days=_int(value("LOOKAHEAD_DAYS", "365"), "LOOKAHEAD_DAYS", 1, 730),
            sync_interval_minutes=_int(
                value("SYNC_INTERVAL_MINUTES", "360"), "SYNC_INTERVAL_MINUTES", 15, 10080
            ),
            max_events=_int(value("MAX_EVENTS", "25"), "MAX_EVENTS", 1, 25),
            timezone_name=timezone_name,
            status_host=value("STATUS_HOST", "127.0.0.1"),
            status_port=_int(value("STATUS_PORT", "8781"), "STATUS_PORT", 1024, 65535),
            state_path=root / "data" / "state.json",
        )

