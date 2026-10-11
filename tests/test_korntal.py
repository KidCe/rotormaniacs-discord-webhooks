from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from korntalbot.dispatch import FEEDS, sync_feed  # noqa: E402
from korntalbot.discord_client import Webhook  # noqa: E402
from korntalbot.ical import parse_ical  # noqa: E402
from korntalbot.render import availability_payload, next_event_payload  # noqa: E402


def sko_event(uid: str = "2410-1792227600-1792274400@fpvkorntal.de", day: str = "20261017"):
    return parse_ical(f'''BEGIN:VCALENDAR
BEGIN:VEVENT
UID:{uid}
DTSTART;TZID=Europe/Berlin:{day}T090000
DTEND;TZID=Europe/Berlin:{day}T220000
SUMMARY:3-5" Hallen Training
LOCATION:Sporthalle Korntal (SKO)
CATEGORIES:offenes Fliegen bis 3 Zoll,offenes Fliegen bis 5 Zoll
END:VEVENT
END:VCALENDAR
''')[0]


class KorntalSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_dir = Path(self.directory.name)
        self.requests = []
        self.messages = {}
        self.failure = None

        def request(client, method, url, payload):
            if self.failure and self.failure(method, payload):
                raise RuntimeError("Simulated Discord failure")
            self.requests.append((method, payload))
            if method == "GET" and "/messages/" in url:
                return self.messages[url.rsplit("/", 1)[1]]
            if method == "POST":
                self.messages[str(len(self.requests))] = {"id": str(len(self.requests)), **payload}
            return {"id": str(len(self.requests)), "guild_id": "123", "channel_id": "456",
                    **({"poll": payload["poll"]} if payload and "poll" in payload else {})}

        self.addCleanup(patch.stopall)
        patch.object(Webhook, "_request", request).start()

    def sync(self, events, day="2026-10-12", hour=7):
        now = datetime.fromisoformat(day).replace(hour=hour, tzinfo=ZoneInfo("Europe/Berlin"))
        with patch("korntalbot.dispatch.fetch_events", return_value=events):
            return sync_feed(FEEDS[1], "https://discord.example/webhook", self.state_dir, now)

    def posts(self):
        return [payload for method, payload in self.requests if method == "POST"]

    def test_all_new_sko_dates_announced_and_unchanged_runs_silent(self):
        events = [sko_event(), sko_event("2411-1-2@fpvkorntal.de", "20261101")]
        result = self.sync(events, "2026-10-11")
        self.assertEqual(result["eventsAnnounced"], 2)
        notifications = [p for p in self.posts() if "NEW" in p["embeds"][0]["title"]]
        self.assertEqual(sum(len(p["embeds"][0]["fields"]) for p in notifications), 2)
        self.requests.clear()
        self.sync(events, "2026-10-11", 19)
        self.assertEqual(self.requests, [])

    def test_monday_poll_for_this_week_only_and_repeat_preserves_id(self):
        events = [sko_event(), sko_event("2411-1-2@fpvkorntal.de", "20261101")]
        self.sync(events, "2026-10-11")
        self.requests.clear()
        result = self.sync(events)
        self.assertEqual(result["availabilityUpdated"], 1)
        self.assertEqual(len(self.posts()), 1)
        poll = self.posts()[0]
        self.assertIn("THIS WEEK", poll["embeds"][0]["title"])
        self.assertEqual([a["poll_media"]["emoji"]["name"] for a in poll["poll"]["answers"]], ["✅", "❌", "🤔"])
        self.assertFalse(poll["poll"]["allow_multiselect"])
        self.assertEqual(poll["poll"]["duration"], 122)
        state_before = json.loads((self.state_dir / FEEDS[1].state_file).read_text(encoding="utf-8"))
        self.requests.clear()
        self.sync(events, "2026-10-14")
        self.assertEqual(self.requests, [])
        self.assertEqual(state_before, json.loads((self.state_dir / FEEDS[1].state_file).read_text(encoding="utf-8")))

    def test_late_week_run_catches_up_and_two_training_days_get_two_polls(self):
        result = self.sync([sko_event(), sko_event("2419-1-2@fpvkorntal.de", "20261018")], "2026-10-15")
        self.assertEqual(result["availabilityUpdated"], 2)

    def test_rescheduled_uid_creates_new_poll_without_editing_or_deleting_old_poll(self):
        event = sko_event()
        self.sync([event])
        self.requests.clear()
        moved = replace(sko_event("2410-1-2@fpvkorntal.de", "20261018"), end=event.end.replace(day=18))
        result = self.sync([moved], "2026-10-13")
        self.assertEqual(result["eventsAnnounced"], 1)
        self.assertIn("UPDATED", self.posts()[0]["embeds"][0]["title"])
        self.assertNotIn("DELETE", [method for method, _ in self.requests])
        self.assertEqual(len(self.posts()), 2)
        self.assertIn("UPDATED DATE", self.posts()[1]["embeds"][0]["title"])
        self.assertFalse(any(method == "PATCH" and "THIS WEEK" in p["embeds"][0]["title"] for method, p in self.requests))
        state = json.loads((self.state_dir / FEEDS[1].state_file).read_text(encoding="utf-8"))
        self.assertEqual(len(state["pollHistory"]["availability:fpvkorntal:2410"]), 1)

    def test_cancellation_notifies_once_without_touching_native_poll(self):
        event = sko_event()
        self.sync([event])
        self.requests.clear()
        cancelled = replace(event, cancelled=True)
        result = self.sync([cancelled], "2026-10-13")
        self.assertEqual(result["eventsAnnounced"], 1)
        self.assertIn("CANCELLED", self.posts()[0]["embeds"][0]["title"])
        self.assertFalse(any(method == "DELETE" for method, _ in self.requests))
        self.assertIn("disregard", self.posts()[0]["embeds"][0]["description"])
        self.assertFalse(any(method == "PATCH" and "CANCELLED" in p["embeds"][0]["title"] for method, p in self.requests))
        self.requests.clear()
        self.sync([cancelled], "2026-10-14")
        self.assertEqual(self.requests, [])

    def test_cancelled_event_does_not_create_new_availability_poll(self):
        result = self.sync([replace(sko_event(), cancelled=True)])
        self.assertEqual(result["availabilityUpdated"], 0)

    def test_poll_not_created_after_training_has_ended(self):
        result = self.sync([sko_event()], "2026-10-17", 23)
        self.assertEqual(result["availabilityUpdated"], 0)

    def test_retained_past_event_does_not_relabel_poll_as_rescheduled(self):
        event = sko_event()
        self.sync([event])
        self.requests.clear()
        result = self.sync([event], "2026-10-19")
        self.assertEqual(result["availabilityUpdated"], 0)
        self.assertFalse(any(p and "RESCHEDULED" in p["embeds"][0]["title"] for _, p in self.requests))

    def test_partial_failure_does_not_repeat_successful_announcements(self):
        event = sko_event()
        self.failure = lambda method, p: method == "POST" and "THIS WEEK" in p["embeds"][0]["title"]
        with self.assertRaises(RuntimeError):
            self.sync([event])
        self.failure = None
        self.requests.clear()
        result = self.sync([event])
        self.assertEqual(result["eventsAnnounced"], 0)
        self.assertEqual(result["availabilityUpdated"], 1)

    def test_winter_monday_uses_berlin_week(self):
        event = sko_event("2420-1-2@fpvkorntal.de", "20270207")
        result = self.sync([event], "2027-02-01")
        self.assertEqual(result["availabilityUpdated"], 1)

    def test_friday_reminder_links_same_poll_and_dashboard_and_only_posts_once(self):
        event = sko_event()
        self.sync([event])
        state = json.loads((self.state_dir / FEEDS[1].state_file).read_text(encoding="utf-8"))
        poll_id = state["availability:fpvkorntal:2410"]["messageId"]
        self.requests.clear()
        result = self.sync([event], "2026-10-16")
        self.assertEqual(result["fridayRemindersUpdated"], 1)
        self.assertEqual(result["availabilityUpdated"], 0)
        self.assertEqual(len(self.posts()), 1)
        self.assertNotIn("poll", self.posts()[0])
        self.assertIn(f"https://discord.com/channels/123/456/{poll_id}", self.posts()[0]["content"])
        self.assertIn(state["dashboard"]["messageId"], self.posts()[0]["embeds"][0]["description"])
        self.requests.clear()
        self.sync([event], "2026-10-16", 19)
        self.assertEqual(self.requests, [])

    def test_missed_friday_reminder_catches_up_before_saturday_training(self):
        event = sko_event()
        self.sync([event])
        self.requests.clear()
        self.assertEqual(self.sync([event], "2026-10-17", 7)["fridayRemindersUpdated"], 1)
        self.requests.clear()
        result = self.sync([event], "2026-10-17", 19)
        self.assertEqual(result["fridayRemindersUpdated"], 0)
        self.assertFalse(self.posts())

    def test_cancelled_event_does_not_get_friday_reminder(self):
        event = sko_event()
        self.sync([event])
        result = self.sync([replace(event, cancelled=True)], "2026-10-16")
        self.assertEqual(result["availabilityUpdated"], 0)
        self.assertEqual(result["fridayRemindersUpdated"], 0)

    def test_title_only_change_preserves_native_poll(self):
        event = sko_event()
        self.sync([event])
        self.requests.clear()
        result = self.sync([replace(event, summary='3–5″ Hallen Training')], "2026-10-13")
        self.assertEqual(result["availabilityUpdated"], 0)
        self.assertEqual(len(self.posts()), 1)

    def test_legacy_reaction_request_migrates_to_native_poll_and_keeps_old_message(self):
        event = sko_event()
        state_path = self.state_dir / FEEDS[1].state_file
        state_path.write_text(json.dumps({"availability:fpvkorntal:2410": {"messageId": "legacy"}}))
        result = self.sync([event])
        self.assertEqual(result["availabilityUpdated"], 1)
        self.assertFalse(any(method == "DELETE" for method, _ in self.requests))
        self.assertTrue(any(method == "PATCH" and "replaced" in payload.get("content", "") for method, payload in self.requests))

    def test_poll_duration_uses_elapsed_hours_across_dst(self):
        event = sko_event("2411-1-2@fpvkorntal.de", "20261025")
        now = datetime(2026, 10, 19, 7, tzinfo=ZoneInfo("Europe/Berlin"))
        self.assertEqual(availability_payload(event, FEEDS[1].label, now)["poll"]["duration"], 147)

    def test_live_probe_removes_only_its_own_message_after_get_validation(self):
        client = Webhook("https://discord.example/webhook", self.state_dir / "probe.json")
        event = sko_event()
        client.verify_poll(availability_payload(event, FEEDS[1].label, event.start))
        self.assertEqual([method for method, _ in self.requests], ["POST", "GET", "DELETE"])
        self.assertEqual(self.posts()[0]["flags"], 4096)
        self.assertFalse((self.state_dir / "probe.json").exists())

    def test_second_failed_import_batch_does_not_duplicate_first_batch(self):
        events = [sko_event(f"{2500 + i}-1-2@fpvkorntal.de") for i in range(8)]
        batches = 0

        def fail_second_batch(method, payload):
            nonlocal batches
            if method == "POST" and "NEW" in payload["embeds"][0]["title"]:
                batches += 1
                return batches == 2
            return False

        self.failure = fail_second_batch
        with self.assertRaises(RuntimeError):
            self.sync(events, "2026-10-11")
        self.failure = None
        self.requests.clear()
        self.assertEqual(self.sync(events, "2026-10-11")["eventsAnnounced"], 2)
        self.assertEqual(len(self.posts()), 1)

    def test_existing_dashboard_state_migrates_without_recreating_dashboard(self):
        state_path = self.state_dir / FEEDS[1].state_file
        state_path.write_text(json.dumps({"dashboard": {"messageId": "old-dashboard", "sha256": "old"}}))
        result = self.sync([sko_event()], "2026-10-11")
        self.assertEqual(result["eventsAnnounced"], 1)
        self.assertEqual(self.requests[0][0], "PATCH")
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["dashboard"]["messageId"], "old-dashboard")


class KorntalCalendarTests(unittest.TestCase):
    def test_live_sko_title_variants_and_categories_exclude_races_and_whoops(self):
        event = sko_event()
        for title in ('3-5" Hallen Training', '3–5″ Hallen Training', '3 - 5 Zoll Training', 'Hallen Training'):
            with self.subTest(title=title):
                self.assertTrue(FEEDS[1].matcher(replace(event, summary=title)))
        self.assertFalse(FEEDS[1].matcher(replace(event, summary="Winter Whooprace")))
        self.assertFalse(FEEDS[1].matcher(replace(event, summary="Training Whoop")))
        self.assertFalse(FEEDS[1].matcher(replace(event, location="Outdoor race track")))

    def test_folded_lines_utc_times_and_explicit_cancelled_status(self):
        payload = '''BEGIN:VCALENDAR
BEGIN:VEVENT
UID:test-utc
DTSTART:20261101T080000Z
SUMMARY:3–5″ Hallen
 Training
LOCATION:Sporthalle Korntal (SKO)
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
'''
        event = parse_ical(payload)[0]
        self.assertEqual(event.summary, "3–5″ HallenTraining")
        self.assertEqual(event.start.hour, 9)
        self.assertEqual(event.start.utcoffset().total_seconds(), 3600)
        self.assertTrue(event.cancelled)
        self.assertTrue(FEEDS[1].matcher(event))

    def test_html_error_page_is_not_an_empty_calendar(self):
        with self.assertRaises(ValueError):
            parse_ical("<html>Temporarily unavailable</html>")

    def test_end_time_changes_fingerprint(self):
        event = sko_event()
        self.assertNotEqual(event.fingerprint, replace(event, end=event.end.replace(hour=20)).fingerprint)

    def test_property_names_are_exact(self):
        payload = '''BEGIN:VCALENDAR
BEGIN:VEVENT
UID:sko-1
DTSTART;TZID=Europe/Berlin:20261017T090000
SUMMARY:3-5 Hallen Training
SUMMARY-ALT:Wrong title
END:VEVENT
END:VCALENDAR
'''
        self.assertEqual(parse_ical(payload)[0].summary, "3-5 Hallen Training")

    def test_workflow_never_gates_sync_on_actual_start_hour(self):
        workflow = (ROOT / ".github/workflows/sync-korntal.yml").read_text(encoding="utf-8")
        self.assertNotIn("local_hour", workflow)
        self.assertNotIn("steps.schedule.outputs.run", workflow)

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
