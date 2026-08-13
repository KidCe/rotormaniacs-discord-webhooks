from __future__ import annotations

import re
from datetime import datetime

from .config import Config
from .models import Match, SourceResult


DESCRIPTION_LIMIT = 3900


def event_fingerprint(match: Match) -> str:
    return "|".join((match.match_date.isoformat(), str(match.kick_off), match.home_team, match.away_team, match.venue, match.status))


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
    intro = (
        f"These matches occupy **{_escape(config.venue_display_name)}**. "
        "The list is refreshed automatically."
    )
    blocks: list[str] = []
    visible_count = 0
    for match in result.matches[: config.max_events]:
        candidate = _match_block(match, config)
        proposed = intro + "\n\n" + "\n\n".join([*blocks, candidate])
        if len(proposed) > DESCRIPTION_LIMIT:
            break
        blocks.append(candidate)
        visible_count += 1

    if blocks:
        description = intro + "\n\n" + "\n\n".join(blocks)
        color = 0xE74C3C
        title = "Pitch occupied — upcoming home fixtures"
    else:
        description = (
            f"No scheduled matches at **{_escape(config.venue_display_name)}** were found "
            f"for the next {config.lookahead_days} days."
        )
        color = 0x2ECC71
        title = "Pitch currently clear"

    omitted = len(result.matches) - visible_count
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
                "footer": {"text": footer},
                "timestamp": result.fetched_at.isoformat().replace("+00:00", "Z"),
            }
        ],
    }


def build_event_payload(match: Match, config: Config, *, changed: bool = False, cancelled: bool = False) -> dict[str, object]:
    if cancelled:
        title = "🚫 SV Aich home fixture cancelled"
        color = 0x95A5A6
        description = f"**{_escape(match.home_team)} vs {_escape(match.away_team)}**\nThe fixture scheduled for **{match.match_date.strftime('%d.%m.%Y')}** has been cancelled."
    else:
        title = "🔔 SV Aich home fixture changed" if changed else "⚽ SV Aich home fixture"
        color = 0xF1C40F if changed else 0x2ECC71
        when = match.match_date.strftime('%d.%m.%Y')
        if match.kick_off:
            when += f" at {match.kick_off.strftime('%H:%M')}"
        description = f"**{_escape(match.home_team)} vs {_escape(match.away_team)}**\n{when}\n{_escape(match.venue or config.venue_display_name)}"
    if match.url:
        description += f"\n[Open fixture on FUSSBALL.DE]({match.url})"
    return {"username": "SV Aich Spielplan", "allowed_mentions": {"parse": []}, "embeds": [{"title": title, "description": description, "color": color}]}


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

