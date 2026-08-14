# Rotormaniacs Discord Webhooks

GitHub Actions integrations that publish community schedules into Discord through webhooks. The repository is public; all webhook URLs remain private GitHub Actions Secrets.

## Links

- [Rotormaniacs / TSV Korntal Discord server](https://discord.com/channels/1308875879786610718/1537600741445738557)
- [GitHub Actions](https://github.com/KidCe/rotormaniacs-discord-webhooks/actions)
- [SV Aich source club page](https://www.fussball.de/verein/sv-aich-wuerttemberg/-/id/00ES8GNA1O000099VV0AG08LVUPGND5I#!/)
- [TSV Korntal calendar](https://fpvkorntal.de/kalender/?ical=1)

## Integrations

### SV Aich home fixtures

The workflow reads the SV Aich schedule from FUSSBALL.DE and keeps the `#sv-aich-heimspiele` channel up to date.

- One chronological dashboard is edited in place.
- Only home fixtures at Sportplatz Aich are included.
- Changed or cancelled fixtures create a separate notification.
- A weekend reminder is posted when a coming weekend is affected.
- Three availability polls cover the upcoming Friday, Saturday, and Sunday. They are replaced on the following Monday and ask members to react with ✅ or ❌.
- Unchanged runs do not send duplicate notifications.

Workflow: `.github/workflows/sync-fixtures.yml`

Required secret: `DISCORD_WEBHOOK_URL`

### TSV Korntal FPV calendar

The workflow reads the official iCal feed and maintains three independent channels:

- `#training-whoop` — Friday Tiny Whoop training in the Aula-Halle.
- `#training-3-5-zoll` — 3–5 inch training in Sporthalle Korntal (SKO).
- `#whooprace` — Whooprace and race events.

Each channel has one dashboard containing the next six events. The next event also gets a separate message, which is deleted and recreated when the next event changes so subscribers receive a fresh notification. Users can react with ✅ or ❌; reactions are not evaluated automatically.

Workflow: `.github/workflows/sync-korntal.yml`

Required secrets:

- `KORNTAL_WHOOP_WEBHOOK_URL`
- `KORNTAL_3_5_WEBHOOK_URL`
- `KORNTAL_RACE_WEBHOOK_URL`

## Scheduling and state

Both workflows run twice daily around 07:00 and 19:00 Europe/Berlin and can also be started manually from GitHub Actions. They run on GitHub-hosted runners, so the local Windows PC does not need to be online.

The workflows commit only non-secret synchronization state back to `data/state.json` and the Korntal state files. This preserves Discord message IDs and event fingerprints across short-lived runners and prevents duplicate posts.

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
```

The Windows convenience launchers were intentionally removed because the supported deployment is GitHub Actions. The Python modules remain available for testing and diagnostics.
