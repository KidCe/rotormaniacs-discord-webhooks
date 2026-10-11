# Rotormaniacs Discord Webhooks

GitHub Actions integrations that publish community schedules into Discord through webhooks. The repository is public; all webhook URLs remain private GitHub Actions Secrets.

## AI assistance disclosure

This project was created and maintained with substantial assistance from OpenAI Codex. The repository maintainer directed the work, made the project decisions, and is responsible for reviewing and using the result.

## Links

- [Rotormaniacs / TSV Korntal Discord server](https://discord.com/channels/1308875879786610718/1537600741445738557)
- [GitHub Actions](https://github.com/KidCe/rotormaniacs-discord-webhooks/actions)
- [SV Aich source club page](https://www.fussball.de/verein/sv-aich-wuerttemberg/-/id/00ES8GNA1O000099VV0AG08LVUPGND5I#!/)
- [TSV Korntal calendar](https://fpvkorntal.de/kalender/?ical=1)

## Integrations

### SV Aich home fixtures

The workflow reads the SV Aich schedule from FUSSBALL.DE and keeps the `#sv-aich-heimspiele` channel up to date.

- One chronological dashboard is edited in place and shows only the next five fixtures.
- Only home fixtures at Sportplatz Aich are included.
- Changed or cancelled fixtures create a separate notification.
- A weekend reminder is posted when a coming weekend is affected.
- Three availability polls cover the upcoming Friday, Saturday, and Sunday. They are replaced on the following Monday, updated when a home game affects one of those days, and ask members to react with ✅ or ❌.
- Unchanged runs do not send duplicate notifications.

Workflow: `.github/workflows/sync-fixtures.yml`

Required secret: `DISCORD_WEBHOOK_URL`

### TSV Korntal FPV calendar

The workflow reads the official iCal feed and maintains three independent channels:

- `#training-whoop` — Friday Tiny Whoop training in the Aula-Halle.
- `#training-3-5-zoll` — 3–5 inch training in Sporthalle Korntal (SKO).
- `#whooprace` — Whooprace and race events.

Each channel has one dashboard containing the next six events. Whoop training and race channels also have a separate next-event message.

The **3–5 inch SKO training channel** additionally:

- Announces every newly published training date, including dates beyond the six-event dashboard. Calendar imports are grouped into messages of up to six dates.
- Posts a separate update when a date, start/end time, location, or explicit cancellation changes. Historical announcements stay in the channel.
- Posts one attendance request per training date starting on Monday of its week in **Europe/Berlin**: “This week there is another training at Sporthalle Korntal (SKO). Who will join us and fly?” Members vote by reacting with **✅ I will attend** or **❌ I will not attend**, as in the SV Aich availability messages.
- Catches up if Monday's run is delayed or missed, and keeps the same attendance message when training details change so reactions remain attached. Cancelled dates do not create new attendance requests; existing requests are marked cancelled.
- Recognizes title variants such as `3-5" Hallen Training` and `3–5″ Hallen Training`, plus SKO training identified by calendar categories. Whoopraces remain in the race channel.

Votes use Discord reactions and are not evaluated automatically. Messages respect members' channel notification settings; they do not ping `@everyone` or a role. Unchanged runs stay silent.

Workflow: `.github/workflows/sync-korntal.yml`

Required secrets:

- `KORNTAL_WHOOP_WEBHOOK_URL`
- `KORNTAL_3_5_WEBHOOK_URL`
- `KORNTAL_RACE_WEBHOOK_URL`

## Scheduling and state

Both workflows are scheduled twice daily at 05:07 and 17:07 UTC (07:07/19:07 in German summer time, 06:07/18:07 in winter) and can also be started manually from GitHub Actions. GitHub may start scheduled jobs late. Both syncs execute regardless of their actual start hour and use persistent state to prevent duplicates. They run on GitHub-hosted runners, so the local Windows PC does not need to be online.

The workflows commit only non-secret synchronization state back to `data/state.json` and the Korntal state files. This preserves Discord message IDs and event fingerprints across short-lived runners and prevents duplicate posts.

The Korntal workflow also preserves successful message state after a partial sync failure. It fetches one validated calendar for all three feeds and reports missing webhook configuration or failed feeds as errors instead of silently succeeding. A missing entry is not automatically treated as a cancellation: only explicit cancellation information from the source triggers that notification.

## Security model

- Webhook URLs are stored only as GitHub Actions Secrets.
- `.env` is ignored; `.env.example` contains empty placeholders only.
- No Discord bot token is required.
- No credentials, private keys, or real webhook URLs belong in this repository.
- The public source code cannot post to Discord without access to the private repository secrets.

## Development

The core implementation is Python 3.11+ and can be tested locally without publishing:

```powershell
python -m unittest discover -s tests -v
python run.py sync --dry-run
python run_korntal.py sync --dry-run --feed training-3-5-zoll
```

The Windows convenience launchers were intentionally removed because the supported deployment is GitHub Actions. The Python modules remain available for testing and diagnostics.
