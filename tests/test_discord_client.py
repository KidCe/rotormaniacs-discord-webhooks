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
        super().__init__("https://discord.example/api/webhooks/test-id/test-token", state_store)
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def _request(self, method: str, url: str, payload: dict[str, object] | None) -> dict[str, object]:
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

    def test_unchanged_dashboard_does_not_call_discord_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            payload = {"username": "Pitch Bot", "embeds": []}
            store.save("456", payload)
            client = RecordingClient(store)
            self.assertEqual(client.publish(payload), "456")
            self.assertEqual(client.requests, [])
            self.assertEqual(client.last_operation, "unchanged")

    def test_delete_reminder_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = RecordingClient(StateStore(Path(directory) / "state.json"))
            client.delete("789")
            self.assertEqual(client.requests, [("DELETE", "https://discord.example/api/webhooks/test-id/test-token/messages/789", None)])

    def test_reminder_message_state_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            reminders = {"fixture-1": {"fingerprint": "fingerprint", "messageId": "789"}}
            store.save_reminder_messages(reminders)
            self.assertEqual(store.load_reminder_messages(), reminders)

    def test_availability_message_state_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            messages = {"friday": {"weekendKey": "2026-08-15", "messageId": "789"}}
            store.save_availability_messages(messages)
            self.assertEqual(store.load_availability_messages(), messages)


if __name__ == "__main__":
    unittest.main()
