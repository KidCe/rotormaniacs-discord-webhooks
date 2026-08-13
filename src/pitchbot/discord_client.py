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

    def load_events(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscordError("The local Discord event state is unreadable.") from exc
        return {str(key): str(fingerprint) for key, fingerprint in value.get("events", {}).items()}

    def save(self, message_id: str, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        state = {
            "messageId": message_id,
            "lastPublishedAt": datetime.now(timezone.utc).isoformat(),
            "payloadSha256": hashlib.sha256(serialized).hexdigest(),
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def save_events(self, events: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        if self.path.exists():
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
        current["events"] = events
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


class DiscordWebhookClient:
    def __init__(self, webhook_url: str, state_store: StateStore, timeout_seconds: int = 30) -> None:
        self.webhook_url = self._without_query(webhook_url)
        self.state_store = state_store
        self.timeout_seconds = timeout_seconds

    def publish(self, payload: dict[str, object]) -> str:
        message_id = self.state_store.load_message_id()
        if message_id:
            try:
                edit_payload = {
                    key: value for key, value in payload.items() if key not in {"username", "avatar_url"}
                }
                self._request("PATCH", f"{self.webhook_url}/messages/{message_id}?wait=true", edit_payload)
                self.state_store.save(message_id, payload)
                return message_id
            except DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise

        response = self._request("POST", f"{self.webhook_url}?wait=true", payload)
        new_message_id = str(response.get("id", ""))
        if not new_message_id:
            raise DiscordError("Discord accepted the webhook but returned no message ID.")
        self.state_store.save(new_message_id, payload)
        return new_message_id

    def publish_new(self, payload: dict[str, object]) -> str:
        response = self._request("POST", f"{self.webhook_url}?wait=true", payload)
        message_id = str(response.get("id", ""))
        if not message_id:
            raise DiscordError("Discord accepted the webhook but returned no message ID.")
        return message_id

    def _request(self, method: str, url: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": "SV-Aich-Discord-Bot/1.0"},
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
