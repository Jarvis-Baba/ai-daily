# Observation Phase

**Start:** 2026-06-02 | **Window:** 30 days | **End:** 2026-07-02

## Freeze Rules

Until the observation window closes:

- No new modules
- No governor threshold changes
- No policy matrix modifications
- No Visual ABI version bumps

Allowed: bug fixes for production failures only.

## What We're Watching

1. **Template distribution** — which templates does AI日报 actually produce?
2. **Diff distribution** — CONTENT_DATA vs INLINE_STYLE vs real regressions
3. **Drift curve** — does CLEAN stay CLEAN over 30 days?

## Success Criteria

After 30 days, we should be able to answer:

1. Which templates appear most often?
2. What did the governor actually block?
3. Did drift occur, and if so, what pattern?

## Artifacts

- `output/daily-summaries/daily-{date}.json` — per-day CI summary
- `output/snapshots/` — visual compiler golden baselines
- `output/evo.jsonl` — evolution log (shared with visual-compiler)
