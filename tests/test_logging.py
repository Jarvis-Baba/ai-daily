"""Tests for JSON structured logging."""

import io
import json
import logging
from src.logging_setup import setup_logging, JsonFormatter


def _capture_log(level: int = logging.DEBUG) -> io.StringIO:
    """Create a logger with a single JsonFormatter handler writing to a buffer."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)

    log = logging.getLogger("test-json-logger")
    log.setLevel(level)
    log.handlers.clear()
    log.addHandler(handler)
    log.propagate = False
    return buf, log


def test_setup_logging_produces_json():
    buf, log = _capture_log()
    log.info("hello world")
    line = buf.getvalue().strip()
    record = json.loads(line)

    assert record["level"] == "INFO"
    assert record["logger"] == "test-json-logger"
    assert record["message"] == "hello world"
    assert "timestamp" in record
    assert "T" in record["timestamp"]


def test_setup_logging_extra_fields():
    buf, log = _capture_log()
    log.info("scored", extra={"items_in": 42, "items_out": 10})
    line = buf.getvalue().strip()
    record = json.loads(line)

    assert record["message"] == "scored"
    assert record["extra"] == {"items_in": 42, "items_out": 10}


def test_setup_logging_is_idempotent():
    """Calling setup_logging twice should not add duplicate handlers."""
    root = logging.getLogger()
    handler_count_before = len(root.handlers)

    setup_logging()
    setup_logging()
    setup_logging()

    assert len(root.handlers) == handler_count_before + 1


def test_json_formatter_multiple_levels():
    buf, log = _capture_log()
    log.debug("debug msg")
    log.info("info msg")
    log.warning("warn msg")
    log.error("error msg")
    log.critical("critical msg")

    lines = [json.loads(l) for l in buf.getvalue().strip().split("\n")]
    levels = [r["level"] for r in lines]
    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def test_json_formatter_exception():
    buf, log = _capture_log()
    try:
        raise RuntimeError("test error")
    except RuntimeError:
        log.exception("something went wrong")

    line = buf.getvalue().strip()
    record = json.loads(line)
    assert record["level"] == "ERROR"
    assert "exception" in record
    assert "RuntimeError" in record["exception"]
    assert "test error" in record["exception"]
