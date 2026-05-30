"""Tests for checkpoint save/load and pipeline resume logic."""

import json
import os
import tempfile
from datetime import date

import pytest

from src.checkpoint import Checkpoint, save_checkpoint, load_checkpoint
from src.pipeline.stage import PipelineContext
from src.pipeline.engine import PipelineEngine


class AppendStage:
    """Stage that appends a value to a context key (for testing)."""
    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value

    def process(self, ctx: PipelineContext) -> PipelineContext:
        ctx.set(self.key, ctx.get(self.key, "") + self.value)
        return ctx


class FailingStage:
    def process(self, ctx: PipelineContext) -> PipelineContext:
        raise RuntimeError("stage failure")


# ---------------------------------------------------------------------------
# Checkpoint save/load
# ---------------------------------------------------------------------------

def test_save_and_load_checkpoint():
    with tempfile.TemporaryDirectory() as tmpdir:
        date_str = "2026-05-30"
        completed = ["FetchStage", "FilterStage"]

        save_checkpoint(tmpdir, date_str, completed)

        cp = load_checkpoint(tmpdir, date_str)
        assert cp is not None
        assert cp.date == date_str
        assert cp.completed == completed
        assert cp.timestamp  # non-empty ISO timestamp


def test_load_checkpoint_nonexistent():
    with tempfile.TemporaryDirectory() as tmpdir:
        cp = load_checkpoint(tmpdir, "2026-05-30")
        assert cp is None


def test_load_checkpoint_corrupt():
    with tempfile.TemporaryDirectory() as tmpdir:
        date_str = "2026-05-30"
        path = os.path.join(tmpdir, f".checkpoint-{date_str}.json")
        with open(path, "w") as f:
            f.write("not valid json")
        cp = load_checkpoint(tmpdir, date_str)
        assert cp is None


# ---------------------------------------------------------------------------
# Engine resume behaviour
# ---------------------------------------------------------------------------

def test_engine_resume_skips_completed_stages():
    today_str = date.today().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate checkpoint after first 2 stages
        save_checkpoint(tmpdir, today_str, ["AppendStage", "AppendStage"])

        ctx = PipelineContext()
        ctx.set("output_dir", tmpdir)

        engine = PipelineEngine([
            AppendStage("log", "A"),
            AppendStage("log", "B"),
            AppendStage("log", "C"),
            AppendStage("log", "D"),
        ])

        result = engine.run(ctx, resume=True)

        # First two stages should be skipped — only C and D run
        assert result.get("log") == "CD"


def test_engine_no_resume_runs_all_stages():
    today_str = date.today().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Checkpoint exists but resume=False, so all should run
        save_checkpoint(tmpdir, today_str, ["AppendStage", "AppendStage"])

        ctx = PipelineContext()
        ctx.set("output_dir", tmpdir)

        engine = PipelineEngine([
            AppendStage("log", "A"),
            AppendStage("log", "B"),
            AppendStage("log", "C"),
            AppendStage("log", "D"),
        ])

        result = engine.run(ctx, resume=False)

        # All four stages run regardless of checkpoint
        assert result.get("log") == "ABCD"


def test_checkpoint_updated_after_each_stage():
    today_str = date.today().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = PipelineContext()
        ctx.set("output_dir", tmpdir)

        engine = PipelineEngine([
            AppendStage("log", "A"),
            AppendStage("log", "B"),
            AppendStage("log", "C"),
        ])

        engine.run(ctx, resume=False)

        # After 3 stages, checkpoint file should exist with 3 entries
        cp = load_checkpoint(tmpdir, today_str)
        assert cp is not None
        assert cp.completed == ["AppendStage", "AppendStage", "AppendStage"]


def test_engine_resume_with_existing_context_data():
    """Verify resume preserves context data from non-skipped stages."""
    today_str = date.today().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        save_checkpoint(tmpdir, today_str, ["AppendStage"])

        ctx = PipelineContext()
        ctx.set("output_dir", tmpdir)
        ctx.set("log", "PRE")  # pre-existing data

        engine = PipelineEngine([
            AppendStage("log", "A"),   # skipped
            AppendStage("log", "B"),   # runs
        ])

        result = engine.run(ctx, resume=True)
        assert result.get("log") == "PREB"


def test_engine_resume_with_stage_failure_does_not_update_checkpoint():
    """Verify checkpoint is NOT updated for a stage that fails."""
    today_str = date.today().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = PipelineContext()
        ctx.set("output_dir", tmpdir)

        engine = PipelineEngine([
            AppendStage("log", "A"),
            FailingStage(),
            AppendStage("log", "C"),
        ])

        with pytest.raises(RuntimeError, match="stage failure"):
            engine.run(ctx, resume=False)

        # Checkpoint should only list the first stage (the one that succeeded)
        cp = load_checkpoint(tmpdir, today_str)
        assert cp is not None
        assert cp.completed == ["AppendStage"]  # FailingStage NOT in list
