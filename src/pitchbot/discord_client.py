from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


class DiscordError(RuntimeError):
    pass


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_message_id(self) -> str:
        if not self.path.exists():
            return ""
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscordError("The local Discord message state is unreadable.") from exc
        message_id = value.get("messageId", "")
        return str(message_id) if message_id else ""

    def load_payload_sha256(self) -> str:
        if not self.path.exists():
            return ""
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscordError("The local Discord message state is unreadable.") from exc
        payload_sha256 = value.get("payloadSha256", "")
        return str(payload_sha256) if payload_sha256 else ""

    def load_events(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscordError("The local Discord event state is unreadable.") from exc
        return {str(key): str(fingerprint) for key, fingerprint in value.get("events", {}).items()}

    def load_reminders(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscordError("The local Discord reminder state is unreadable.") from exc
        return {str(key): str(fingerprint) for key, fingerprint in value.get("reminders", {}).items()}

    def load_reminder_messages(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscordError("The local Discord message state is unreadable.") from exc
        result: dict[str, dict[str, str]] = {}
        for key, reminder in value.get("reminderMessages", {}).items():
            if isinstance(reminder, dict):
                result[str(key)] = {
                    "fingerprint": str(reminder.get("fingerprint", "")),
                    "messageId": str(reminder.get("messageId", "")),
                }
        return result

    def load_availability_messages(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscordError("The local Discord message state is unreadable.") from exc
        result: dict[str, dict[str, str]] = {}
        for key, message in value.get("availabilityMessages", {}).items():
            if isinstance(message, dict):
                result[str(key)] = {
                    "weekendKey": str(message.get("weekendKey", "")),
                    "messageId": str(message.get("messageId", "")),
                }
        return result

    def save(self, message_id: str, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        state = {}
        if self.path.exists():
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
        state.update({
            "messageId": message_id,
            "lastPublishedAt": datetime.now(timezone.utc).isoformat(),
            "payloadSha256": hashlib.sha256(serialized).hexdigest(),
        })
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def save_events(self, events: dict[str, str], reminders: dict[str, str] | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        if self.path.exists():
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
        current["events"] = events
        if reminders is not None:
            current["reminders"] = reminders
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def save_reminder_messages(self, reminders: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        if self.path.exists():
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
        current["reminderMessages"] = reminders
        current["reminders"] = {key: value["fingerprint"] for key, value in reminders.items()}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def save_availability_messages(self, messages: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        if self.path.exists():
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
        current["availabilityMessages"] = messages
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


class DiscordWebhookClient:
    def __init__(self, webhook_url: str, state_store: StateStore, timeout_seconds: int = 30) -> None:
        self.webhook_url = self._without_query(webhook_url)
        self.state_store = state_store
        self.timeout_seconds = timeout_seconds
        self.last_operation = "unchanged"

    def publish(self, payload: dict[str, object]) -> str:
        message_id = self.state_store.load_message_id()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        payload_sha256 = hashlib.sha256(serialized).hexdigest()
        if message_id and self.state_store.load_payload_sha256() == payload_sha256:
            self.last_operation = "unchanged"
            return message_id
        if message_id:
            try:
                edit_payload = {
                    key: value for key, value in payload.items() if key not in {"username", "avatar_url"}
                }
                self._request("PATCH", f"{self.webhook_url}/messages/{message_id}?wait=true", edit_payload)
                self.state_store.save(message_id, payload)
                self.last_operation = "updated"
                return message_id
            except DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise

        response = self._request("POST", f"{self.webhook_url}?wait=true", payload)
        new_message_id = str(response.get("id", ""))
        if not new_message_id:
            raise DiscordError("Discord accepted the webhook but returned no message ID.")
        self.state_store.save(new_message_id, payload)
        self.last_operation = "created"
        return new_message_id

    def publish_new(self, payload: dict[str, object]) -> str:
        response = self._request("POST", f"{self.webhook_url}?wait=true", payload)
        message_id = str(response.get("id", ""))
        if not message_id:
            raise DiscordError("Discord accepted the webhook but returned no message ID.")
        return message_id

    def delete(self, message_id: str) -> None:
        if not message_id:
            return
        try:
            self._request("DELETE", f"{self.webhook_url}/messages/{message_id}", None)
        except DiscordError as exc:
            if "HTTP 404" not in str(exc):
                raise

    def _request(self, method: str, url: str, payload: dict[str, object] | None) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": "Road2Maniacs-Discord-Webhooks/1.0"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read()
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace").strip()
            suffix = f" Response: {details}" if details else ""
            raise DiscordError(f"Discord webhook failed with HTTP {exc.code}.{suffix}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise DiscordError("Discord could not be reached.") from exc
        if not response_body:
            return {}
        try:
            return json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DiscordError("Discord returned an unreadable response.") from exc

    @staticmethod
    def _without_query(url: str) -> str:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
