"""observe/logger.py — Structured JSON logging via structlog.

Usage:
    from observe.logger import configure_logging, get_logger
    configure_logging("INFO", "json", "data/logs/engine.jsonl")
    log = get_logger()
    log.info("cycle_start", run_id=run_id, sources=8)
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import structlog


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    log_file: str = "data/logs/engine.jsonl",
) -> None:
    """Configure structlog + standard logging for the engine.

    Args:
        level: Standard Python log level name (INFO, DEBUG, etc.)
        fmt: Output format — "json" for production, "text" for development
        log_file: Path to rotating log file (in addition to stderr)
    """
    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard logging handlers
    handlers: list[logging.Handler] = []

    # Stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(numeric_level)
    handlers.append(stderr_handler)

    # Rotating file handler (10 MB × 5 files = max 50 MB)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(numeric_level)
    handlers.append(file_handler)

    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        format="%(message)s",
    )

    # Shared processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.contextvars.merge_contextvars,
    ]

    if fmt == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    for handler in handlers:
        handler.setFormatter(formatter)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger."""
    return structlog.get_logger(name)  # type: ignore[return-value]
