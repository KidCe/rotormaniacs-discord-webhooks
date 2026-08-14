from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from korntalbot.dispatch import FEEDS  # noqa: E402
from korntalbot.ical import parse_ical  # noqa: E402
from korntalbot.render import next_event_payload  # noqa: E402


class KorntalCalendarTests(unittest.TestCase):
    def test_parses_cancelled_sko_event(self) -> None:
        payload = """BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:sko-1\nDTSTART;TZID=Europe/Berlin:20261018T110000\nDTEND;TZID=Europe/Berlin:20261018T200000\nSUMMARY:ABGESAGT! Training 3-5 Zoll\nLOCATION:Sporthalle Korntal (SKO)\nCATEGORIES:3-5 Zoll\nURL:https://example.test/event\nEND:VEVENT\nEND:VCALENDAR\n"""
        event = parse_ical(payload)[0]
        self.assertTrue(event.cancelled)
        self.assertIn("Sporthalle Korntal", event.location)
        self.assertTrue(FEEDS[1].matcher(event))

    def test_race_matcher_accepts_whooprennen(self) -> None:
        payload = """BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:race-1\nDTSTART;TZID=Europe/Berlin:20261012T080000\nSUMMARY:Herbst Whooprennen\nEND:VEVENT\nEND:VCALENDAR\n"""
        event = parse_ical(payload)[0]
        self.assertTrue(FEEDS[2].matcher(event))

    def test_next_message_contains_only_reaction_guidance(self) -> None:
        event = parse_ical("""BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:whoop-1\nDTSTART;TZID=Europe/Berlin:20261002T190000\nSUMMARY:Training Whoop\nEND:VEVENT\nEND:VCALENDAR\n""")[0]
        payload = next_event_payload(event, "Training Whoop")
        content = payload["content"]
        self.assertIn("✅", content)
        self.assertIn("❌", content)
        self.assertNotIn("findet statt", content)
        self.assertNotIn("findet nicht statt", content)


if __name__ == "__main__":
    unittest.main()
