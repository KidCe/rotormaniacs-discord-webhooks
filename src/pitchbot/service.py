from __future__ import annotations

import html
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Config
from .discord_client import DiscordWebhookClient, StateStore
from .fussball import FussballScheduleClient
from .models import SourceResult
from .render import (
    availability_weekend_start,
    build_availability_payload,
    build_discord_payload,
    build_event_payload,
    build_weekend_reminder_payload,
    event_fingerprint,
    weekend_reminder_due,
)


LOGGER = logging.getLogger(__name__)
LOG_TAG = "road2maniacs-discord-webhooks"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class RuntimeStatus:
    state: str = "starting"
    message: str = "Waiting for the first schedule refresh"
    last_attempt: str | None = None
    last_success: str | None = None
    last_publish: str | None = None
    last_error: str | None = None
    matching_events: int = 0
    source_events: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **changes: Any) -> None:
        with self.lock:
            for name, value in changes.items():
                setattr(self, name, value)

    def snapshot(self, config: Config) -> dict[str, object]:
        with self.lock:
            state = self.state
            message = self.message
            last_attempt = self.last_attempt
            last_success = self.last_success
            last_publish = self.last_publish
            last_error = self.last_error
            matching_events = self.matching_events
            source_events = self.source_events

        alerts: list[dict[str, str]] = []
        if not config.webhook_url:
            alerts.append({
                "severity": "warning",
                "code": "WEBHOOK_NOT_CONFIGURED",
                "message": "Add DISCORD_WEBHOOK_URL to .env before publishing.",
            })
        elif not config.publish_enabled:
            alerts.append({
                "severity": "warning",
                "code": "PUBLISHING_DISABLED",
                "message": "PUBLISH_ENABLED is false; Discord updates are disabled.",
            })
        if last_error:
            alerts.append({"severity": "error", "code": "LAST_SYNC_FAILED", "message": last_error})

        return {
            "schemaVersion": "tool-dashboard-status/v1",
            "summary": {"state": state, "message": message},
            "metrics": {
                "matchingFixtures": {"label": "Pitch occupancies", "value": matching_events, "unit": "matches"},
                "sourceFixtures": {"label": "Club fixtures checked", "value": source_events, "unit": "matches"},
                "refreshInterval": {
                    "label": "Refresh interval",
                    "value": config.sync_interval_minutes,
                    "unit": "minutes",
                },
            },
            "alerts": alerts,
            "extensions": {
                LOG_TAG: {
                    "club": config.club_name,
                    "venue": config.venue_display_name,
                    "lastAttempt": last_attempt,
                    "lastSuccessfulSync": last_success,
                    "lastDiscordPublish": last_publish,
                    "publishingConfigured": config.can_publish,
                }
            },
        }


class SyncEngine:
    def __init__(self, config: Config, status: RuntimeStatus) -> None:
        self.config = config
        self.status = status
        self.source = FussballScheduleClient(config)
        self._run_lock = threading.Lock()

    def run_once(self, dry_run: bool = False) -> tuple[SourceResult, dict[str, object]]:
        with self._run_lock:
            return self._run_once(dry_run)

    def _run_once(self, dry_run: bool = False) -> tuple[SourceResult, dict[str, object]]:
        attempted_at = _utc_now()
        self.status.update(state="syncing", message="Reading FUSSBALL.DE", last_attempt=attempted_at)
        try:
            result = self.source.fetch()
            state_store = StateStore(self.config.state_path)
            known_events = state_store.load_events()
            known_reminders = state_store.load_reminders()
            reminder_messages = state_store.load_reminder_messages()
            notifications_sent = 0
            dashboard_updated = False
            if not dry_run and self.config.can_publish:
                client = DiscordWebhookClient(
                    self.config.webhook_url,
                    StateStore(self.config.state_path),
                )
                client.publish(build_discord_payload(result, self.config))
                dashboard_updated = client.last_operation in {"created", "updated"}
                current_events: dict[str, str] = {}
                for match in result.matches:
                    key = match.identity
                    fingerprint = event_fingerprint(match)
                    current_events[key] = fingerprint
                    if key in known_events and known_events[key] != fingerprint:
                        client.publish_new(build_event_payload(
                            match,
                            self.config,
                            changed=True,
                            cancelled=match.cancelled,
                        ))
                        notifications_sent += 1
                local_today = datetime.now(self.config.timezone).date()
                due_matches = [
                    match for match in result.matches
                    if not match.cancelled and weekend_reminder_due(match, local_today)
                ]
                due_matches.sort(key=lambda match: (match.match_date, match.kick_off or datetime.min.time()))
                current_reminder = due_matches[0] if due_matches else None
                current_key = current_reminder.identity if current_reminder else ""
                current_fingerprint = event_fingerprint(current_reminder) if current_reminder else ""
                for key, reminder in list(reminder_messages.items()):
                    if key != current_key or reminder.get("fingerprint") != current_fingerprint:
                        client.delete(reminder.get("messageId", ""))
                        reminder_messages.pop(key, None)
                        notifications_sent += 1
                availability_messages = state_store.load_availability_messages()
                weekend_start = availability_weekend_start(local_today)
                weekend_key = weekend_start.isoformat()
                if any(
                    record.get("weekendKey") != weekend_key
                    for record in availability_messages.values()
                ) or set(availability_messages) != {"friday", "saturday", "sunday"}:
                    for record in availability_messages.values():
                        client.delete(record.get("messageId", ""))
                    availability_messages = {}
                    for slot, offset in (("friday", -1), ("saturday", 0), ("sunday", 1)):
                        day = weekend_start + timedelta(days=offset)
                        message_id = client.publish_new(build_availability_payload(day, self.config))
                        availability_messages[slot] = {
                            "weekendKey": weekend_key,
                            "messageId": message_id,
                        }
                    state_store.save_availability_messages(availability_messages)
                    notifications_sent += 3
                if current_reminder and current_key not in reminder_messages:
                    message_id = client.publish_new(build_weekend_reminder_payload(current_reminder, self.config))
                    reminder_messages[current_key] = {
                        "fingerprint": current_fingerprint,
                        "messageId": message_id,
                    }
                    notifications_sent += 1
                known_reminders = {key: value["fingerprint"] for key, value in reminder_messages.items()}
                state_store.save_events(current_events, known_reminders)
                state_store.save_reminder_messages(reminder_messages)
            published = dashboard_updated or notifications_sent > 0

            success_at = _utc_now()
            if published:
                state = "ready"
                message = f"Discord is up to date with {len(result.matches)} pitch occupancies"
            elif dry_run:
                state = "ready"
                message = f"Preview completed with {len(result.matches)} pitch occupancies"
            elif self.config.can_publish:
                state = "ready"
                message = f"Discord was already up to date with {len(result.matches)} pitch occupancies"
            else:
                state = "setup_required"
                message = "Schedule read succeeded; Discord publishing is not configured"
            self.status.update(
                state=state,
                message=message,
                last_success=success_at,
                last_publish=success_at if published else self.status.last_publish,
                last_error=None,
                matching_events=len(result.matches),
                source_events=result.source_match_count,
            )
            LOGGER.info(
                "Schedule refresh succeeded: %s source fixtures, %s pitch occupancies%s.",
                result.source_match_count,
                len(result.matches),
                " and Discord was updated" if published else "",
            )
            return result, {
                "dashboardUpdated": dashboard_updated,
                "notificationsSent": notifications_sent,
            }
        except Exception as exc:
            safe_message = str(exc) or exc.__class__.__name__
            self.status.update(state="error", message="The last refresh failed", last_error=safe_message)
            LOGGER.exception("Schedule refresh failed: %s", safe_message)
            raise


class PitchBotService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.status = RuntimeStatus()
        self.engine = SyncEngine(config, self.status)
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()
        self.server: ThreadingHTTPServer | None = None

    def serve(self) -> None:
        handler = self._handler_class()
        self.server = ThreadingHTTPServer((self.config.status_host, self.config.status_port), handler)
        worker = threading.Thread(target=self._sync_loop, name="pitchbot-sync", daemon=True)
        worker.start()
        LOGGER.info(
            "Status service ready at http://%s:%s. Press Ctrl+C to stop.",
            self.config.status_host,
            self.config.status_port,
        )
        try:
            self.server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            LOGGER.info("Stopping Pitch Bot.")
        finally:
            self.stop_event.set()
            self.refresh_event.set()
            self.server.server_close()
            worker.join(timeout=10)

    def _sync_loop(self) -> None:
        interval_seconds = self.config.sync_interval_minutes * 60
        while not self.stop_event.is_set():
            try:
                self.engine.run_once()
            except Exception:
                pass
            self.refresh_event.wait(interval_seconds)
            self.refresh_event.clear()

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PitchBotStatus/1.0"

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._json(200, {"status": "ok", "serviceState": service.status.state})
                elif self.path in {"/dashboard/status", "/api/status"}:
                    self._json(200, service.status.snapshot(service.config))
                elif self.path == "/":
                    self._html(200, self._status_page())
                else:
                    self._json(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path == "/refresh":
                    service.refresh_event.set()
                    self._json(202, {"status": "accepted", "message": "A schedule refresh was requested."})
                elif self.path == "/shutdown":
                    self._json(202, {"status": "accepted", "message": "Pitch Bot is stopping."})
                    threading.Thread(target=service._request_shutdown, daemon=True).start()
                else:
                    self._json(404, {"error": "not_found"})

            def log_message(self, format: str, *args: object) -> None:
                return

            def _json(self, status_code: int, value: object) -> None:
                body = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                self._activity(status_code)

            def _html(self, status_code: int, value: str) -> None:
                body = value.encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                self._activity(status_code)

            def _activity(self, status_code: int) -> None:
                timestamp = datetime.now(timezone.utc).isoformat()
                # Keep this exact raw format so the Tool Dashboard can parse it.
                print(f"[{timestamp}] [{LOG_TAG}] {self.command} {self.path} {status_code}", flush=True)

            def _status_page(self) -> str:
                snapshot = service.status.snapshot(service.config)
                summary = snapshot["summary"]
                metrics = snapshot["metrics"]
                return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Road2Maniacs Discord Webhooks</title>
<style>body{{font-family:system-ui;max-width:760px;margin:3rem auto;padding:0 1rem;color:#17202a}}
.card{{border:1px solid #d5d8dc;border-radius:12px;padding:1.25rem;box-shadow:0 2px 8px #0001}}
dt{{font-weight:700;margin-top:1rem}}dd{{margin:.25rem 0}}button{{margin-top:1rem;padding:.7rem 1rem}}</style></head>
<body><h1>Road2Maniacs Discord Webhooks</h1><div class="card">
<p><strong>{html.escape(str(summary['state']))}</strong> — {html.escape(str(summary['message']))}</p>
<dl><dt>Target venue</dt><dd>{html.escape(service.config.venue_display_name)}</dd>
<dt>Pitch occupancies</dt><dd>{metrics['matchingFixtures']['value']}</dd>
<dt>Club fixtures checked</dt><dd>{metrics['sourceFixtures']['value']}</dd></dl>
<form method="post" action="/refresh"><button type="submit">Refresh schedule now</button></form>
</div></body></html>"""

        return Handler

    def _request_shutdown(self) -> None:
        self.stop_event.set()
        self.refresh_event.set()
        if self.server is not None:
            self.server.shutdown()
