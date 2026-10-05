from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pitchbot.config import Config
from pitchbot.discord_client import StateStore
from pitchbot.models import Match, SourceResult
from pitchbot.service import RuntimeStatus, SyncEngine


class AvailabilitySyncTests(unittest.TestCase):
    def test_new_week_has_home_game_warning_and_repeat_keeps_message_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = replace(
                Config.load(ROOT / ".env.example"),
                webhook_url="https://discord.example/api/webhooks/test/test",
                publish_enabled=True,
                state_path=Path(directory) / "state.json",
            )
            match = Match(
                date(2026, 10, 11), time(15), "SV 07 Aich", "TSV Neckartenzlingen",
                "League", "ME", "350245045", "Sportplatz Aich | Heideweg 60 | 72631 Aichtal", "",
            )
            result = SourceResult((match,), 1, datetime.now(timezone.utc), "https://example.test")
            engine = SyncEngine(config, RuntimeStatus())
            with patch.object(engine.source, "fetch", return_value=result), patch(
                "pitchbot.service.datetime"
            ) as clock, patch("pitchbot.service.DiscordWebhookClient") as factory:
                clock.now.return_value = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
                client = factory.return_value
                client.publish_new.side_effect = ["friday-id", "saturday-id", "sunday-id"]
                engine.run_once()
                created = [call.args[0]["embeds"][0] for call in client.publish_new.call_args_list]
                self.assertEqual(len(created), 3)
                self.assertNotIn("HOME GAME", created[0]["description"])
                self.assertNotIn("HOME GAME", created[1]["description"])
                self.assertIn("PITCH PROBABLY OCCUPIED", created[2]["description"])
                self.assertIn("✅", created[2]["description"])
                saved = StateStore(config.state_path).load_availability_messages()
                client.reset_mock()
                engine.run_once()
                client.publish_new.assert_not_called()
                client.delete.assert_not_called()
                self.assertEqual(StateStore(config.state_path).load_availability_messages(), saved)
                self.assertEqual(client.edit_message.call_args_list[2].args[0], "sunday-id")
                self.assertIn(
                    "PITCH PROBABLY OCCUPIED",
                    client.edit_message.call_args_list[2].args[1]["embeds"][0]["description"],
                )


if __name__ == "__main__":
    unittest.main()
