from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config, ConfigError
from .render import plain_preview
from .service import PitchBotService, RuntimeStatus, SyncEngine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish SV Aich home fixtures to Discord.")
    parser.add_argument("--env-file", type=Path, help="Read configuration from this .env file.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Run the scheduled service and local status endpoint.")
    sync = subparsers.add_parser("sync", help="Refresh the schedule once and exit.")
    sync.add_argument("--dry-run", action="store_true", help="Show a preview without writing to Discord.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )
    try:
        config = Config.load(args.env_file)
        if args.command in {None, "serve"}:
            PitchBotService(config).serve()
            return 0

        engine = SyncEngine(config, RuntimeStatus())
        result, outcome = engine.run_once(dry_run=args.dry_run)
        print()
        print(plain_preview(result, config))
        if args.dry_run:
            print("\nDry run complete. Discord was not changed.")
        elif config.can_publish and outcome["notificationsSent"]:
            print(f"\nSent {outcome['notificationsSent']} Discord notification(s).")
        elif config.can_publish:
            print("\nNo changes found. Discord was not changed.")
        else:
            print("\nDiscord was not changed because publishing is not configured.")
        return 0
    except ConfigError as exc:
        logging.error("Configuration error: %s", exc)
        return 2
    except Exception as exc:
        logging.error("Pitch Bot stopped: %s", exc)
        return 1

