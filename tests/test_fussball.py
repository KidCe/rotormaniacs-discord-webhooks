from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pitchbot.config import Config  # noqa: E402
from pitchbot.fussball import FussballScheduleClient  # noqa: E402


def fixture(date_text: str, venue: str, status: str = "") -> str:
    status_html = f'<span class="info-text">{status}</span>' if status else ""
    return f"""
    <html><body><table><tbody>
      <tr class="row-competition hidden-small">
        <td class="column-date">{date_text}</td>
        <td class="column-team">Herren | B-Klasse</td>
        <td>ME | 420307002</td>
      </tr>
      <tr>
        <td></td>
        <td><div class="club-name">FC Germania 1907 Eich</div></td>
        <td>:</td>
        <td><div class="club-name">Example FC</div></td>
        <td class="column-score"><a href="https://www.fussball.de/spiel/example/-/spiel/ABC">{status_html}</a></td>
      </tr>
      <tr class="row-venue hidden-small"><td></td><td><div>Spielstätte:{venue}</div></td></tr>
    </tbody></table></body></html>
    """


class ScheduleParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Config.load(ROOT / ".env.example")
        self.client = FussballScheduleClient(self.config)

    def test_includes_only_the_configured_eich_venue(self) -> None:
        matches, source_count = self.client.parse(
            fixture("Saturday, 15.08.2026 - 16:00", "Eich Rasenplatz | Im Wäldchen 1 | 67575 Eich"),
            date(2026, 8, 1),
            date(2026, 12, 31),
        )
        self.assertEqual(source_count, 1)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].kick_off.strftime("%H:%M"), "16:00")

    def test_rejects_a_home_fixture_at_hamm(self) -> None:
        matches, _ = self.client.parse(
            fixture("15.08.26 | 16:00", "Hamm Rasenplatz | Strasse zum Rhein | 67580 Hamm"),
            date(2026, 8, 1),
            date(2026, 12, 31),
        )
        self.assertEqual(matches, [])

    def test_rejects_cancelled_fixture(self) -> None:
        matches, _ = self.client.parse(
            fixture("15.08.2026 | 16:00", "Eich Rasenplatz | Im Wäldchen 1 | 67575 Eich", "Absetzung"),
            date(2026, 8, 1),
            date(2026, 12, 31),
        )
        self.assertEqual(matches, [])

    def test_skips_fixture_without_a_confirmed_date(self) -> None:
        matches, source_count = self.client.parse(
            fixture("", "Eich Rasenplatz | Im Wäldchen 1 | 67575 Eich"),
            date(2026, 8, 1),
            date(2026, 12, 31),
        )
        self.assertEqual(matches, [])
        self.assertEqual(source_count, 1)

    def test_inherits_grouped_date_when_the_next_row_contains_only_a_time(self) -> None:
        second_fixture = """
          <tr class="row-competition hidden-small">
            <td class="column-date">18:00</td><td class="column-team">Herren | B-Klasse</td>
            <td>ME | 420307003</td>
          </tr>
          <tr><td></td><td><div class="club-name">Eich II</div></td><td>:</td>
            <td><div class="club-name">Guests II</div></td>
            <td class="column-score"><a href="https://www.fussball.de/spiel/example-2/-/spiel/DEF"></a></td>
          </tr>
          <tr class="row-venue hidden-small"><td></td><td>
            <div>Spielstätte:Eich Rasenplatz | Im Wäldchen 1 | 67575 Eich</div>
          </td></tr>
        """
        html = fixture(
            "15.08.26 | 16:00", "Eich Rasenplatz | Im Wäldchen 1 | 67575 Eich"
        ).replace("</tbody>", second_fixture + "</tbody>")
        matches, source_count = self.client.parse(html, date(2026, 8, 1), date(2026, 12, 31))
        self.assertEqual(source_count, 2)
        self.assertEqual([match.match_date for match in matches], [date(2026, 8, 15), date(2026, 8, 15)])


if __name__ == "__main__":
    unittest.main()
