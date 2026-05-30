"""JSON structured logging setup for ai-daily."""

import json
import logging
from datetime import datetime, timezone


_STANDARD_RECORD_ATTRS: set[str] = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}

_MARKER_ATTR = "_json_formatter_installed"


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON lines.

    Standard LogRecord attributes become top-level keys.
    Any extra attributes passed via ``logger.info("msg", extra={"key": "val"})``
    are collected under an ``"extra"`` key.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Gather non-standard attributes into "extra"
        extra: dict = {}
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_"):
                extra[key] = value

        if extra:
            log_entry["extra"] = extra

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger to emit JSON lines to stdout.

    Idempotent — calling this multiple times will not add duplicate handlers.
    """
    root = logging.getLogger()

    # Guard against duplicate setup
    for handler in root.handlers:
        if getattr(handler, _MARKER_ATTR, False):
            return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)

    # Mark the handler so we can detect it next time
    setattr(handler, _MARKER_ATTR, True)

    root.addHandler(handler)
    root.setLevel(level)
