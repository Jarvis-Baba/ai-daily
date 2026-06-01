#!/usr/bin/env python3
"""
Daily CI Loop — orchestrates the full AI日报 → Visual Compiler pipeline.

Runs after ai-daily generates the morning report. Produces a daily-summary.json
with Content IR stats, visual complexity, diff results, and governor status.

Usage:
  daily_pipeline.py                           — process today's report
  daily_pipeline.py --date 2026-06-02         — process a specific date
  daily_pipeline.py --markdown <path>          — process a specific Markdown file
  daily_pipeline.py --cron                    — cron mode (minimal stdout)
"""
import json, os, sys, subprocess, shutil, tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
BRIDGE = os.path.join(SCRIPT_DIR, "content-bridge.py")
VISUAL_COMPILER = os.path.expanduser("~/.claude/skills/wechat-article-engine/visual-compiler")
SNAPSHOT_DIR = os.path.join(VISUAL_COMPILER, "snapshots")
SUMMARY_DIR = os.path.join(OUTPUT_DIR, "daily-summaries")

os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(SUMMARY_DIR, exist_ok=True)


def find_report(date_str=None):
    """Find the morning report for a given date."""
    if date_str:
        path = os.path.join(OUTPUT_DIR, f"morning-{date_str}.md")
        if os.path.exists(path):
            return path, date_str
        return None, date_str

    reports = sorted(Path(OUTPUT_DIR).glob("morning-*.md"))
    if not reports:
        return None, None
    latest = reports[-1]
    date_str = latest.stem.replace("morning-", "")
    return str(latest), date_str


def find_previous_report(current_date):
    """Find the report immediately before the current date."""
    reports = sorted(Path(OUTPUT_DIR).glob("morning-*.md"))
    prev = None
    for r in reports:
        d = r.stem.replace("morning-", "")
        if d < current_date:
            prev = str(r)
        else:
            break
    return prev


def step_content_bridge(md_path, date_str, cron=False):
    """Step 1: Markdown → Content IR + Visual Plan + PNGs."""
    vis_dir = os.path.join(OUTPUT_DIR, f"visual-{date_str}")
    ir_path = os.path.join(OUTPUT_DIR, f"morning-{date_str}.ir.json")

    result = subprocess.run(
        [sys.executable, BRIDGE, md_path, "--save", ir_path, "--visual", vis_dir],
        capture_output=cron, text=True
    )
    if result.returncode != 0 and cron:
        result = subprocess.run(
            [sys.executable, BRIDGE, md_path, "--save", ir_path, "--visual", vis_dir],
            capture_output=False, text=True
        )

    with open(ir_path) as f:
        ir = json.load(f)

    vp_path = os.path.join(vis_dir, "visual_plan.json")
    image_count = 0
    template_types = []
    if os.path.exists(vp_path):
        with open(vp_path) as f:
            vp = json.load(f)
        image_count = len(vp.get("images", []))
        template_types = list(set(img["type"] for img in vp.get("images", [])))

    return {
        "ir_path": ir_path,
        "vis_dir": vis_dir,
        "content_ir": ir,
        "image_count": image_count,
        "template_types": template_types,
    }


def step_snapshot(date_str, vis_dir, ir_path):
    """Step 2: Create visual compiler snapshot for today."""
    renderspec_path = os.path.join(vis_dir, "renderspec.json")
    png_dir = os.path.join(vis_dir, "images")

    snapshot_py = os.path.join(VISUAL_COMPILER, "snapshot.py")
    if not os.path.exists(snapshot_py):
        return {"snapshot_id": date_str, "status": "skipped (no snapshot module)"}

    with open(ir_path) as f:
        ir_data = json.load(f)

    subprocess.run(
        [sys.executable, snapshot_py, "save", date_str,
         ir_path, renderspec_path, vis_dir, png_dir],
        capture_output=True, text=True
    )

    image_count = len(list(Path(png_dir).glob("*.png"))) if os.path.isdir(png_dir) else 0

    return {"snapshot_id": date_str, "image_count": image_count, "status": "saved"}


def step_diff(date_str, prev_md_path, vis_dir):
    """Step 3: Diff today's visual output against previous day."""
    if not prev_md_path:
        return {"status": "skipped", "reason": "no previous report"}

    prev_date = Path(prev_md_path).stem.replace("morning-", "")
    prev_snap = os.path.join(SNAPSHOT_DIR, prev_date)

    if not os.path.exists(os.path.join(prev_snap, "manifest.json")):
        prev_vis = os.path.join(OUTPUT_DIR, f"visual-{prev_date}")
        prev_ir = os.path.join(OUTPUT_DIR, f"morning-{prev_date}.ir.json")
        if os.path.exists(prev_vis) and os.path.exists(prev_ir):
            step_snapshot(prev_date, prev_vis, prev_ir)
        else:
            return {"status": "skipped", "reason": f"no previous snapshot or visual for {prev_date}"}

    diff_py = os.path.join(VISUAL_COMPILER, "diff.py")
    if not os.path.exists(diff_py):
        return {"status": "skipped", "reason": "no diff module"}

    snapshot_py = os.path.join(VISUAL_COMPILER, "snapshot.py")
    current_snap = os.path.join(SNAPSHOT_DIR, f"_current_{date_str}")
    renderspec_path = os.path.join(vis_dir, "renderspec.json")
    ir_path = os.path.join(OUTPUT_DIR, f"morning-{date_str}.ir.json")

    subprocess.run(
        [sys.executable, snapshot_py, "save", f"_current_{date_str}",
         ir_path, renderspec_path, vis_dir, os.path.join(vis_dir, "images")],
        capture_output=True, text=True
    )

    result = subprocess.run(
        [sys.executable, diff_py, current_snap, prev_snap, "SEMANTIC"],
        capture_output=True, text=True
    )

    deltas = []
    passed = result.returncode == 0
    for line in result.stdout.split('\n'):
        if '●' in line or '○' in line:
            deltas.append(line.strip())

    if os.path.exists(current_snap):
        shutil.rmtree(current_snap)

    return {
        "status": "pass" if passed else "deltas_detected",
        "previous_date": prev_date,
        "delta_count": len(deltas),
        "deltas": deltas,
        "mode": "SEMANTIC",
    }


def step_governor(date_str):
    """Step 4: Run governor drift check."""
    governor_py = os.path.join(VISUAL_COMPILER, "governor.py")
    if not os.path.exists(governor_py):
        return {"status": "skipped", "reason": "no governor module"}

    result = subprocess.run(
        [sys.executable, governor_py, "check", date_str],
        capture_output=True, text=True
    )

    drift_score = "CLEAN"
    drift_alerts = []
    for line in result.stdout.split('\n'):
        if line.startswith("Drift score:"):
            drift_score = line.split(":")[1].strip()
        if '⚠' in line:
            drift_alerts.append(line.strip())

    return {"drift_score": drift_score, "alerts": drift_alerts}


def assemble_summary(date_str, bridge_result, snapshot_result, diff_result, governor_result):
    """Assemble the daily summary JSON."""
    ir = bridge_result.get("content_ir", {})

    summary = {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "1.0",

        "content": {
            "executive_judgment": ir.get("executive_judgment", {}).get("text", "")[:200],
            "structural_shifts": len(ir.get("structural_shifts", [])),
            "capability_events": len(ir.get("events", {}).get("capability", [])),
            "behavioral_events": len(ir.get("events", {}).get("behavioral", [])),
            "risk_items": len(ir.get("risk_layer", [])),
            "decision_hooks": sum(len(v) for v in ir.get("decision_hooks", {}).values()),
            "has_counter_signal": "counter_signal" in ir,
            "active_themes": ir.get("executive_judgment", {}).get("active_themes", []),
        },

        "visual": {
            "image_count": bridge_result.get("image_count", 0),
            "template_types": bridge_result.get("template_types", []),
            "snapshot_id": snapshot_result.get("snapshot_id", date_str),
        },

        "diff": diff_result,

        "governor": governor_result,

        "meta": ir.get("meta", {}),
    }

    return summary


def run(date_str=None, markdown_path=None, cron=False):
    """Run the full daily CI loop."""
    if markdown_path:
        md_path = markdown_path
        date_str = Path(md_path).stem.replace("morning-", "")
    else:
        md_path, date_str = find_report(date_str)
        if not md_path:
            print("No daily report found.")
            return None

    if not cron:
        print(f"Daily CI Loop — {date_str}")
        print(f"  Report: {md_path}")
        print()

    if not cron: print("[1/4] Content Bridge...")
    bridge_result = step_content_bridge(md_path, date_str, cron)
    if not cron:
        print(f"  Content IR: {bridge_result['ir_path']}")
        print(f"  Visual: {bridge_result['image_count']} images ({', '.join(bridge_result['template_types'])})")

    if not cron: print("[2/4] Snapshot...")
    snapshot_result = step_snapshot(date_str, bridge_result["vis_dir"], bridge_result["ir_path"])
    if not cron: print(f"  Snapshot: {snapshot_result['snapshot_id']} ({snapshot_result['image_count']} images)")

    if not cron: print("[3/4] Diff...")
    prev_md = find_previous_report(date_str)
    diff_result = step_diff(date_str, prev_md, bridge_result["vis_dir"])
    if not cron: print(f"  Diff: {diff_result['status']} ({diff_result.get('delta_count', 0)} deltas)")

    if not cron: print("[4/4] Governor...")
    governor_result = step_governor(date_str)
    if not cron: print(f"  Drift: {governor_result['drift_score']}")

    summary = assemble_summary(date_str, bridge_result, snapshot_result, diff_result, governor_result)

    summary_path = os.path.join(SUMMARY_DIR, f"daily-{date_str}.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    if not cron:
        print(f"\n  Summary → {summary_path}")
        print(f"  Status: {'CLEAN' if diff_result.get('status') == 'pass' else 'REVIEW'}")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Daily CI Loop for AI日报 + Visual Compiler")
    parser.add_argument("--date", help="Process a specific date (YYYY-MM-DD)")
    parser.add_argument("--markdown", help="Process a specific Markdown file")
    parser.add_argument("--cron", action="store_true", help="Cron mode (minimal output)")
    args = parser.parse_args()

    summary = run(date_str=args.date, markdown_path=args.markdown, cron=args.cron)
    sys.exit(0 if summary else 1)
