from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pitchbot.discord_client import DiscordWebhookClient, StateStore  # noqa: E402


class RecordingClient(DiscordWebhookClient):
    def __init__(self, state_store: StateStore) -> None:
        super().__init__("https://discord.com/api/webhooks/123/token", state_store)
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def _request(self, method: str, url: str, payload: dict[str, object]) -> dict[str, object]:
        self.requests.append((method, url, payload))
        return {"id": "456"}


class DiscordWebhookClientTests(unittest.TestCase):
    def test_create_keeps_the_webhook_username(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = RecordingClient(StateStore(Path(directory) / "state.json"))
            message_id = client.publish({"username": "Pitch Bot", "embeds": []})
            self.assertEqual(message_id, "456")
            self.assertEqual(client.requests[0][0], "POST")
            self.assertEqual(client.requests[0][2]["username"], "Pitch Bot")

    def test_edit_uses_only_supported_message_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            store.save("456", {"embeds": []})
            client = RecordingClient(store)
            client.publish({"username": "Pitch Bot", "avatar_url": "https://example.test/a.png", "embeds": []})
            self.assertEqual(client.requests[0][0], "PATCH")
            self.assertNotIn("username", client.requests[0][2])
            self.assertNotIn("avatar_url", client.requests[0][2])


if __name__ == "__main__":
    unittest.main()
