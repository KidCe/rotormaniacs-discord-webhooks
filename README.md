# SV Aich Discord Bot

This small service maintains one chronological Discord dashboard for SV Aich home fixtures. It reads the SV Aich club schedule from FUSSBALL.DE, checks each actual venue, and silently edits the same dashboard message only when its contents change. Separate messages are reserved for meaningful fixture changes, explicit cancellations, and weekend reminders.

The default configuration is ready for:

- Club: SV Aich / SV 07 Aich
- FUSSBALL.DE club ID: `00ES8GNA1O000099VV0AG08LVUPGND5I`
- Pitch: Sportplatz Aich, Heideweg 60, 72631 Aichtal
- Cloud refresh: twice daily, around 07:00 and 19:00 German local time
- Planning window: 365 days

## Automatic GitHub Actions hosting

The repository includes a GitHub Actions workflow that runs twice daily, around 07:00 and 19:00 German local time, including daylight-saving changes. It can also be started manually from the repository's **Actions** page. This is the recommended deployment: it works while personal computers are turned off and requires no Discord bot token or public server.

Store the Discord webhook as the repository secret `DISCORD_WEBHOOK_URL`. The non-secret notification history in `data/state.json` is committed by the workflow only when it changes. This prevents duplicate messages across short-lived GitHub runners.

The workflow needs **Read and write permissions** for repository contents so it can persist that state file.

## Optional local Windows setup

## Quick setup on Windows

1. In Discord, open the target channel and choose **Edit Channel > Integrations > Webhooks > New Webhook**.
2. Copy the webhook URL. The user doing this needs the **Manage Webhooks** permission.
3. Double-click `setup.cmd`.
4. Open the newly created `.env` file and paste the URL after `DISCORD_WEBHOOK_URL=`.
5. Double-click `preview.cmd`. It performs a live read but never changes Discord.
6. Double-click `start.cmd`. Keep the visible window open while the bot should run.

On the first successful publish, the service creates one dashboard message containing all currently known home fixtures in chronological order. The nearest fixture is shown at the top. Later runs edit that same message; they do not append another fixture list to the channel. If the dashboard is unchanged, Discord is not contacted at all. A changed or explicitly cancelled known fixture creates one additional notification.

For Saturday or Sunday fixtures, the service posts one additional warning on the preceding Wednesday. The reminder message ID is stored separately, so later checks do not repeat it. After that weekend fixture has passed, the next check deletes the old reminder; if another upcoming weekend fixture is already due, only its reminder remains.

To start it automatically after Windows sign-in, double-click `install-startup.cmd`. The service still opens in a visible window so it is obvious that it is running and can be stopped. `uninstall-startup.cmd` removes that shortcut.

## Everyday use

- `start.cmd` — run the scheduled service in a visible window.
- `preview.cmd` — read FUSSBALL.DE and show the result without changing Discord.
- `refresh-now.cmd` — perform one live read and update Discord immediately.
- `http://127.0.0.1:8781` — local status page while the service is running.
- `POST http://127.0.0.1:8781/refresh` — request an immediate background refresh.

The dashboard message ID, known fixture fingerprints, and reminder history are stored in `data/state.json`. Keep this file when moving the service so the existing dashboard can be edited and notifications are not repeated.

## Move to another Windows computer

Copy the complete project folder, including `.env` and `data/state.json`, to the new computer. Do not copy `.venv`; run `setup.cmd` on the new computer and then `start.cmd`. Python 3.11 or newer is required.

Treat `.env` like a password because the Discord webhook URL permits posting to its channel. It is excluded from Git by default.

## Docker

Copy `.env.example` to `.env`, add the Discord webhook URL, then run:

```powershell
docker compose up -d --build
```

The container restarts automatically. Its status page is only exposed on `127.0.0.1:8781` of the Docker host. Stop it with:

```powershell
docker compose down
```

## Configuration

| Setting | Purpose | Default |
| --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook; leave empty for read-only operation | empty |
| `PUBLISH_ENABLED` | Emergency publishing switch | `true` |
| `FUSSBALL_CLUB_ID` | Club ID from the FUSSBALL.DE URL | SV Aich ID |
| `VENUE_MATCH_TERMS` | Semicolon-separated venue fragments; any match counts | Sportplatz Aich name/address |
| `VENUE_DISPLAY_NAME` | Name shown in Discord | Sportplatz Aich |
| `LOOKAHEAD_DAYS` | Future planning window | `365` |
| `SYNC_INTERVAL_MINUTES` | Automatic refresh interval | `360` |
| `MAX_EVENTS` | Maximum fixtures shown in one Discord message | `25` |
| `STATUS_HOST` / `STATUS_PORT` | Local health and status service | `127.0.0.1:8781` |

After changing `.env`, restart the service.

## How occupancy is decided

A match blocks FPV training only when all of these conditions are true:

1. It appears in the configured club schedule on FUSSBALL.DE.
2. Its actual listed venue contains one of `VENUE_MATCH_TERMS`.
3. Its date is inside the configured future window.
4. If it is explicitly marked as cancelled, abandoned, annulled, or a no-show, it is retained long enough to publish a cancellation notice.

This venue check is intentional: SV Aich teams can have fixtures at other venues, which do not occupy Sportplatz Aich.

## Reliability and source limits

The service updates Discord only after a complete, successfully parsed FUSSBALL.DE response. If the website is unavailable or changes its layout, the previous Discord message remains untouched and the local status page reports the error. FUSSBALL.DE remains the source of truth; fixture times and venues can change at short notice.

This project uses low-frequency access intended for a private, non-commercial community schedule. Review the current FUSSBALL.DE terms before using it in another context.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run.py sync --dry-run
```

