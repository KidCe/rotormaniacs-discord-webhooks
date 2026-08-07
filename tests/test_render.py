from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pitchbot.config import Config  # noqa: E402
from pitchbot.models import Match, SourceResult  # noqa: E402
from pitchbot.render import build_discord_payload  # noqa: E402


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

    def test_renders_clear_state(self) -> None:
        result = SourceResult((), 4, datetime.now(timezone.utc), "https://www.fussball.de/example")
        payload = build_discord_payload(result, self.config)
        self.assertEqual(payload["embeds"][0]["title"], "Pitch currently clear")


if __name__ == "__main__":
    unittest.main()

