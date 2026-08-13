from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pitchbot.config import Config  # noqa: E402
from pitchbot.models import Match, SourceResult  # noqa: E402
from pitchbot.render import (  # noqa: E402
    build_discord_payload,
    build_event_payload,
    build_weekend_reminder_payload,
    weekend_reminder_date,
    weekend_reminder_due,
)


class DiscordRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Config.load(ROOT / ".env.example")

    def test_renders_matching_fixture(self) -> None:
        result = SourceResult(
            matches=(Match(date(2026, 8, 15), time(16), "Eich", "Guests", "B-Klasse", "ME", "42", "Eich Rasenplatz", "https://example.test"),),
            source_match_count=4,
            fetched_at=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
            source_url="https://www.fussball.de/example",
        )
        payload = build_discord_payload(result, self.config)
        embed = payload["embeds"][0]
        self.assertIn("Pitch occupied", embed["title"])
        self.assertIn("Eich vs Guests", embed["description"])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        self.assertNotIn("discord", payload["username"].casefold())

    def test_renders_clear_state(self) -> None:
        result = SourceResult((), 4, datetime.now(timezone.utc), "https://www.fussball.de/example")
        payload = build_discord_payload(result, self.config)
        self.assertEqual(payload["embeds"][0]["title"], "Pitch currently clear")

    def test_renders_structured_fixture_card(self) -> None:
        match = Match(date(2026, 8, 30), time(15), "SV 07 Aich", "Guests", "League", "ME", "42", "Sportplatz Aich", "https://example.test")
        embed = build_event_payload(match, self.config)["embeds"][0]
        self.assertEqual(embed["title"], "⚽ SV AICH HOME FIXTURE")
        self.assertEqual([field["name"] for field in embed["fields"]], ["Fixture", "Kick-off", "Venue"])
        self.assertEqual(embed["url"], "https://example.test")

    def test_weekend_reminder_is_due_from_wednesday(self) -> None:
        sunday_match = Match(date(2026, 8, 30), time(15), "SV 07 Aich", "Guests", "League", "ME", "42", "Sportplatz Aich", "")
        self.assertEqual(weekend_reminder_date(sunday_match), date(2026, 8, 26))
        self.assertFalse(weekend_reminder_due(sunday_match, date(2026, 8, 25)))
        self.assertTrue(weekend_reminder_due(sunday_match, date(2026, 8, 26)))
        self.assertTrue(weekend_reminder_due(sunday_match, date(2026, 8, 30)))
        self.assertIn("THIS WEEKEND", build_weekend_reminder_payload(sunday_match, self.config)["embeds"][0]["title"])


if __name__ == "__main__":
    unittest.main()

