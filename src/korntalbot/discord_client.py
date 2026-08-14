from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WebhookError(RuntimeError):
    pass


class Webhook:
    def __init__(self, url: str, state_path: Path) -> None:
        self.url = url.rstrip("/")
        self.state_path = state_path

    def _state(self) -> dict[str, object]:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def sync_message(self, slot: str, payload: dict[str, object]) -> bool:
        state = self._state()
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        message = state.get(slot, {})
        if isinstance(message, dict) and message.get("messageId") and message.get("sha256") == digest:
            return False
        message_id = str(message.get("messageId", "")) if isinstance(message, dict) else ""
        if message_id:
            try:
                self._request("PATCH", f"{self.url}/messages/{message_id}", payload)
            except WebhookError as exc:
                if "HTTP 404" not in str(exc):
                    raise
                message_id = ""
        if not message_id:
            message_id = str(self._request("POST", f"{self.url}?wait=true", payload).get("id", ""))
        if not message_id:
            raise WebhookError("Discord did not return a message ID.")
        state[slot] = {"messageId": message_id, "sha256": digest}
        self._save(state)
        return True

    def replace_message(self, slot: str, payload: dict[str, object]) -> bool:
        state = self._state()
        old = state.get(slot, {})
        if isinstance(old, dict) and old.get("messageId"):
            self.delete_message(str(old["messageId"]))
        message_id = str(self._request("POST", f"{self.url}?wait=true", payload).get("id", ""))
        if not message_id:
            raise WebhookError("Discord did not return a message ID.")
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        state[slot] = {"messageId": message_id, "sha256": digest}
        self._save(state)
        return True

    def delete_message(self, message_id: str) -> None:
        if not message_id:
            return
        try:
            self._request("DELETE", f"{self.url}/messages/{message_id}", None)
        except WebhookError as exc:
            if "HTTP 404" not in str(exc):
                raise

    def _request(self, method: str, url: str, payload: dict[str, object] | None) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        request = Request(url, data=body, method=method, headers={"Content-Type": "application/json", "User-Agent": "TSV-Korntal-Calendar-Webhook/1.0"})
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
        except HTTPError as exc:
            raise WebhookError(f"Discord webhook failed with HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise WebhookError("Discord webhook could not be reached.") from exc
        return json.loads(data.decode()) if data else {}
