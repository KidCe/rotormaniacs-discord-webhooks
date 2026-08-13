from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .config import Config
from .models import Match, SourceResult


DESCRIPTION_LIMIT = 3900


def event_fingerprint(match: Match) -> str:
    return "|".join((match.match_date.isoformat(), str(match.kick_off), match.home_team, match.away_team, match.venue, match.status))


def weekend_reminder_date(match: Match) -> date | None:
    if match.match_date.weekday() not in {5, 6}:
        return None
    saturday = match.match_date - timedelta(days=match.match_date.weekday() - 5)
    return saturday - timedelta(days=3)


def weekend_reminder_due(match: Match, today: date) -> bool:
    reminder_date = weekend_reminder_date(match)
    return reminder_date is not None and reminder_date <= today <= match.match_date


def _escape(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()<>#+\-.!|])", r"\\\1", value)


def _match_block(match: Match, config: Config) -> str:
    if match.kick_off is not None:
        local_start = datetime.combine(match.match_date, match.kick_off, config.timezone)
        when = f"<t:{int(local_start.timestamp())}:F>"
    else:
        when = f"{match.match_date.strftime('%d.%m.%Y')} — time not confirmed"
    teams = f"**{_escape(match.home_team)} vs { _escape(match.away_team)}**"
    competition = _escape(match.competition or "Competition not specified")
    details = f"[FUSSBALL.DE]({match.url})" if match.url else "FUSSBALL.DE"
    return f"**{when}**\n{teams}\n{competition} · {details}"


def build_discord_payload(result: SourceResult, config: Config) -> dict[str, object]:
    matches = sorted(
        result.matches[: config.max_events],
        key=lambda match: (match.match_date, match.kick_off or datetime.min.time()),
    )
    fields: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        if match.kick_off is not None:
            local_start = datetime.combine(match.match_date, match.kick_off, config.timezone)
            timestamp = int(local_start.timestamp())
            when = f"<t:{timestamp}:D> · <t:{timestamp}:t>"
        else:
            when = f"{match.match_date.strftime('%d.%m.%Y')} · time not confirmed"
        label = f"NEXT · {when}" if index == 0 else when
        status = "\n**CANCELLED**" if match.cancelled else ""
        source = f"[Open on FUSSBALL.DE]({match.url})" if match.url else "FUSSBALL.DE"
        fields.append({
            "name": label,
            "value": (
                f"**{_escape(match.home_team)} vs {_escape(match.away_team)}**{status}\n"
                f"{_escape(match.venue or config.venue_display_name)} · {source}"
            ),
            "inline": False,
        })

    if fields:
        first = matches[0]
        if first.kick_off is not None:
            next_start = datetime.combine(first.match_date, first.kick_off, config.timezone)
            next_text = f"The next home fixture starts <t:{int(next_start.timestamp())}:R>."
        else:
            next_text = "The next home fixture is listed first below."
        description = (
            f"{next_text}\nAll known fixtures at **{_escape(config.venue_display_name)}**, "
            "ordered from nearest to furthest away."
        )
        color = 0xE74C3C
        title = "SV Aich — Home fixture dashboard"
    else:
        description = (
            f"No scheduled matches at **{_escape(config.venue_display_name)}** were found "
            f"for the next {config.lookahead_days} days."
        )
        color = 0x2ECC71
        title = "SV Aich — Pitch currently clear"

    omitted = len(result.matches) - len(fields)
    footer = (
        f"Source: FUSSBALL.DE · {result.source_match_count} club fixtures checked · "
        f"{config.lookahead_days}-day window"
    )
    if omitted > 0:
        footer += f" · {omitted} more matching fixtures not shown"

    return {
        "username": "SV Aich Spielplan",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": title,
                "description": description,
                "url": result.source_url,
                "color": color,
                "fields": fields,
                "footer": {"text": footer},
            }
        ],
    }


def _fixture_fields(match: Match, config: Config) -> list[dict[str, object]]:
    when = match.match_date.strftime("%A, %d %B %Y")
    if match.kick_off:
        local_start = datetime.combine(match.match_date, match.kick_off, config.timezone)
        when = f"<t:{int(local_start.timestamp())}:F>\n<t:{int(local_start.timestamp())}:R>"
    return [
        {"name": "Fixture", "value": f"**{_escape(match.home_team)}**\nvs\n**{_escape(match.away_team)}**", "inline": True},
        {"name": "Kick-off", "value": when, "inline": True},
        {"name": "Venue", "value": _escape(match.venue or config.venue_display_name), "inline": False},
    ]


def build_event_payload(match: Match, config: Config, *, changed: bool = False, cancelled: bool = False) -> dict[str, object]:
    if cancelled:
        title = "🚫 HOME FIXTURE CANCELLED"
        color = 0xE74C3C
        description = "This fixture no longer occupies Sportplatz Aich."
    else:
        title = "🔔 HOME FIXTURE UPDATED" if changed else "⚽ SV AICH HOME FIXTURE"
        color = 0xF1C40F if changed else 0x2E8B57
        description = "Sportplatz Aich is occupied for this scheduled match."
    embed: dict[str, object] = {
        "title": title,
        "description": description,
        "color": color,
        "fields": _fixture_fields(match, config),
        "footer": {"text": "Automatic update • Source: FUSSBALL.DE"},
    }
    if match.url:
        embed["url"] = match.url
    return {"username": "SV Aich Spielplan", "allowed_mentions": {"parse": []}, "embeds": [embed]}


def build_weekend_reminder_payload(match: Match, config: Config) -> dict[str, object]:
    embed: dict[str, object] = {
        "title": "⚠️ THIS WEEKEND: PITCH OCCUPIED",
        "description": "Plan your flying accordingly — a home fixture is scheduled at Sportplatz Aich this weekend.",
        "color": 0xE67E22,
        "fields": _fixture_fields(match, config),
        "footer": {"text": "Weekend reminder • Source: FUSSBALL.DE"},
    }
    if match.url:
        embed["url"] = match.url
    return {"username": "SV Aich Spielplan", "allowed_mentions": {"parse": []}, "embeds": [embed]}


def plain_preview(result: SourceResult, config: Config) -> str:
    lines = [
        f"{config.venue_display_name}",
        f"Source fixtures checked: {result.source_match_count}",
        f"Matching active fixtures: {len(result.matches)}",
    ]
    for match in result.matches:
        time_text = match.kick_off.strftime("%H:%M") if match.kick_off else "time not confirmed"
        lines.append(
            f"- {match.match_date.strftime('%d.%m.%Y')} {time_text}: "
            f"{match.home_team} vs {match.away_team} ({match.venue})"
        )
    if not result.matches:
        lines.append("- No pitch occupancy was found in the configured window.")
    return "\n".join(lines)

