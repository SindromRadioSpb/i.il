"""main.py — Local Engine entry point.

PATCH-01: Minimal entry — initialises DB, runs one no-op cycle, exits.
Full scheduler loop is added in later patches.

Usage:
    cd apps/local-engine
    python main.py              # run one cycle
    python main.py --daemon     # run in scheduler loop (after all patches complete)
"""

from __future__ import annotations

import asyncio
import sys

from config.settings import Settings
from db.connection import get_db
from db.migrate import apply_migrations
from observe.logger import configure_logging, get_logger


async def run_once(settings: Settings) -> None:
    """Run a single no-op cycle to verify DB and logging work."""
    log = get_logger("main")
    log.info("engine_start", config=settings.safe_repr())

    async with get_db(settings.database_path) as db:
        await apply_migrations(db)
        log.info("migrations_ok", database=settings.database_path)
        log.info("engine_ready", note="Full pipeline not yet implemented (PATCH-01 scaffold)")


def sync_main() -> None:
    """Synchronous entry point for the project.scripts console_script."""
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, settings.log_file)
    asyncio.run(run_once(settings))


if __name__ == "__main__":
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, settings.log_file)

    if "--daemon" in sys.argv:
        print("Daemon mode not yet implemented. Running one cycle.", file=sys.stderr)

    asyncio.run(run_once(settings))
