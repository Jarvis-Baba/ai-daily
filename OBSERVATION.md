# Observation Phase

**Start:** 2026-06-02 | **Window:** 100 articles | **Tag:** v1.0.0

## Freeze Rules

- No new modules
- No governor threshold changes
- No policy matrix modifications
- No Visual ABI version bumps

Allowed: bug fixes for production failures only.

## Core Question

> 系统关于"什么是好内容"的假设，是否经得起 100 次现实检验？

139/139 tests prove the system matches its design.
0/100 articles have proven the design matches reality.
These are completely different things.

## Validation Framework

### V1: Theme Discovery Efficacy

After 100 articles:

- How many themes were adopted vs. abandoned?
- Does 20% of themes produce 80% of results?
- Are SEED_THEMES adequate, or do real themes cluster differently?

### V2: Scoring System Trustworthiness

The most dangerous failure mode:

> Score looks scientific but is unrelated to human judgment.

Track:

- Does score-95 content outperform score-72 content in real metrics?
- If not: the problem is in the evaluator, not the generator.

### V3: Pattern Collapse Detection

The silent killer:

> Different topics, same article.

Check at article 50, 80, 100:

- Are openings converging?
- Are structures converging?
- Are viewpoints converging?

If "Compiler Success, Content Failure" appears: freeze immediately, diagnose before iterating.

## Hidden Metric: Manual Edit Rate

More important than read count:

| Metric | Target |
|--------|--------|
| Average edit time per article | Track → reduce |
| Average words changed per article | Track → reduce |
| Direct-publish rate | Target: 95% |

If every article still needs 40 minutes of editing: it's an auto-draft machine, not a compiler.

## Data Assets (do not touch until 100)

```
theme distribution
  ↓
score distribution
  ↓
generated output
  ↓
manual edit delta
  ↓
real-world performance
```

This chain IS the product of Phase A. Phase B (feedback learning) must not begin until this chain exists. Premature feedback risks training the system to please its own scorer.

## Artifacts

- `output/daily-summaries/daily-{date}.json` — per-day CI summary
- `output/snapshots/` — visual compiler golden baselines
- `output/evo.jsonl` — evolution log (shared with visual-compiler)

## Risk Posture

Risk has shifted: **development risk → cognitive risk.**

The system will not die from a bug.
It will die from: see a flaw → add a module → see another flaw → add another module → 100 articles haven't run → system is v1.7.
