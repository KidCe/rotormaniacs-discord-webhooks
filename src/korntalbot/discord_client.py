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
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary_path.replace(self.state_path)

    def publish_new(self, payload: dict[str, object]) -> str:
        message_id = str(self._request("POST", f"{self.url}?wait=true", payload).get("id", ""))
        if not message_id:
            raise WebhookError("Discord did not return a message ID.")
        return message_id

    def sync_poll(self, slot: str, payload: dict[str, object], event_key: str) -> bool:
        """Create immutable polls once; keep previous votes on schedule changes."""
        state = self._state()
        previous = state.get(slot, {})
        if previous.get("nativePoll") and previous.get("eventKey") == event_key:
            self._redirect_legacy(slot)
            return False
        if "discord" not in state:
            context = self._request("GET", self.url, None)
            if not context.get("guild_id") or not context.get("channel_id"):
                raise WebhookError("Discord did not return the server and channel IDs for poll links.")
            state["discord"] = {"guildId": str(context["guild_id"]), "channelId": str(context["channel_id"])}
            self._save(state)
        message = self._request("POST", f"{self.url}?wait=true", payload)
        message_id = str(message.get("id", ""))
        if not message_id:
            raise WebhookError("Discord did not return a poll message ID.")
        if not message.get("poll"):
            self.delete_message(message_id)
            raise WebhookError("Discord did not create the requested native poll.")
        if previous.get("messageId"):
            state.setdefault("pollHistory", {}).setdefault(slot, []).append(previous)
        state[slot] = {"messageId": message_id, "nativePoll": True, "eventKey": event_key}
        if previous.get("messageId") and not previous.get("nativePoll"):
            state[slot]["legacyMessageId"] = previous["messageId"]
        self._save(state)
        # Legacy reaction requests remain as history but point voters to the new poll.
        self._redirect_legacy(slot)
        return True

    def _redirect_legacy(self, slot: str) -> None:
        state = self._state()
        record = state[slot]
        if not record.get("legacyMessageId"):
            return
        try:
            self._request("PATCH", f"{self.url}/messages/{record['legacyMessageId']}", {
                "content": f"This reaction-based request has been replaced. Please vote here: {self.message_url(record['messageId'])}",
                "embeds": [], "allowed_mentions": {"parse": []},
            })
        except WebhookError as exc:
            if "HTTP 404" not in str(exc):
                raise
        record.pop("legacyMessageId")
        self._save(state)

    def message_url(self, message_id: str) -> str:
        context = self._state()["discord"]
        return f"https://discord.com/channels/{context['guildId']}/{context['channelId']}/{message_id}"

    def verify_poll(self, payload: dict[str, object]) -> None:
        """Silent live API probe. Never edits or deletes an existing event message."""
        payload = {**payload, "flags": 4096, "content": "TEST — checking native webhook polls; this message is automatically removed.",
                   "embeds": [], "poll": {**payload["poll"], "duration": 1,
                                          "question": {"text": "TEST — automatically removed after verification"}}}
        message_id = self.publish_new(payload)
        try:
            message = self._request("GET", f"{self.url}/messages/{message_id}", None)
            poll = message.get("poll", {})
            media = [(answer["poll_media"].get("text"), answer["poll_media"].get("emoji", {}).get("name"))
                     for answer in poll.get("answers", [])]
            expected = [(answer["poll_media"]["text"], answer["poll_media"]["emoji"]["name"])
                        for answer in payload["poll"]["answers"]]
            if media != expected or poll.get("allow_multiselect") is not False:
                raise WebhookError("Live Discord poll verification failed.")
        finally:
            self.delete_message(message_id)

    def sync_message(self, slot: str, payload: dict[str, object]) -> bool:
        state = self._state()
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        message = state.get(slot, {})
        if isinstance(message, dict) and message.get("messageId") and message.get("sha256") == digest:
            return False
        message_id = str(message.get("messageId", "")) if isinstance(message, dict) else ""
        if message_id:
            try:
                editable = {key: value for key, value in payload.items() if key not in {"username", "avatar_url"}}
                self._request("PATCH", f"{self.url}/messages/{message_id}", editable)
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
