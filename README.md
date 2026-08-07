# SV 07 Eich Pitch Bot

This small service keeps one Discord message up to date with the days on which the football pitch in Eich is occupied by a scheduled match. It reads the FC Germania 1907 Eich club schedule from FUSSBALL.DE, checks the actual venue of every fixture, excludes cancelled fixtures, and only publishes matches at the configured Eich pitch.

The default configuration is ready for:

- Club: FC Germania 1907 Eich
- FUSSBALL.DE club ID: `00ES8GNBB000003AVV0AG08LVUPGND5I`
- Pitch: Eich Rasenplatz, Im Wäldchen 1, 67575 Eich
- Refresh interval: every 6 hours
- Planning window: 365 days

## Important runtime note

Discord cannot host or execute this code. The bot must run on a Windows computer, home server, NAS, VPS, or Docker host that stays online. Discord receives updates through a channel webhook; no Discord bot token and no public inbound port are required.

## Quick setup on Windows

1. In Discord, open the target channel and choose **Edit Channel > Integrations > Webhooks > New Webhook**.
2. Copy the webhook URL. The user doing this needs the **Manage Webhooks** permission.
3. Double-click `setup.cmd`.
4. Open the newly created `.env` file and paste the URL after `DISCORD_WEBHOOK_URL=`.
5. Double-click `preview.cmd`. It performs a live read but never changes Discord.
6. Double-click `start.cmd`. Keep the visible window open while the bot should run.

On the first successful publish, the service creates one Discord message. Later refreshes edit that same message instead of filling the channel with repeated posts.

To start it automatically after Windows sign-in, double-click `install-startup.cmd`. The service still opens in a visible window so it is obvious that it is running and can be stopped. `uninstall-startup.cmd` removes that shortcut.

## Everyday use

- `start.cmd` — run the scheduled service in a visible window.
- `preview.cmd` — read FUSSBALL.DE and show the result without changing Discord.
- `refresh-now.cmd` — perform one live read and update Discord immediately.
- `http://127.0.0.1:8781` — local status page while the service is running.
- `POST http://127.0.0.1:8781/refresh` — request an immediate background refresh.

The current Discord message ID is stored in `data/state.json`. Keep this file when moving the service if the new computer should continue editing the existing Discord message. If it is missing, the service safely creates a new message.

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
| `FUSSBALL_CLUB_ID` | Club ID from the FUSSBALL.DE URL | FC Germania 1907 Eich ID |
| `VENUE_MATCH_TERMS` | Semicolon-separated venue fragments; any match counts | Eich pitch name/address |
| `VENUE_DISPLAY_NAME` | Name shown in Discord | Eich Rasenplatz (Wäldchen Stadium) |
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
4. It is not marked as cancelled, abandoned, annulled, a no-show, or a bye.

This venue check is intentional: FC Germania teams and joint teams can have nominal home fixtures in Hamm or Rheindürkheim, which do not occupy the Eich pitch.

## Reliability and source limits

The service updates Discord only after a complete, successfully parsed FUSSBALL.DE response. If the website is unavailable or changes its layout, the previous Discord message remains untouched and the local status page reports the error. FUSSBALL.DE remains the source of truth; fixture times and venues can change at short notice.

This project uses low-frequency access intended for a private, non-commercial community schedule. Review the current FUSSBALL.DE terms before using it in another context.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run.py sync --dry-run
```

