#!/usr/bin/env python3
"""
Content Bridge: AI日报 Markdown → Content IR → Visual Plan.

Extracts structured Content IR from ai-daily Markdown output and optionally
generates a Visual Plan for the deterministic visual compiler.

Usage:
  content-bridge.py <markdown_file>                    → Content IR JSON to stdout
  content-bridge.py <markdown_file> --visual <out_dir>  → Visual Plan + compile
  content-bridge.py <markdown_file> --save <ir_path>    → Save Content IR to file
"""
import json, os, re, sys, subprocess
from datetime import datetime
from pathlib import Path

CONTENT_IR_VERSION = "1.0"
VISUAL_COMPILER = os.path.expanduser("~/.claude/skills/wechat-article-engine/visual-compiler")


# ═══════════════════════════════════════════════
# §1 Markdown Parser
# ═══════════════════════════════════════════════

def parse_date(text):
    """Extract date from header line like '# 🧠 AI Daily Report — 2026-05-31'"""
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    return m.group(1) if m else None


def parse_executive_judgment(text):
    """Parse Section 1: Executive Judgment."""
    result = {"text": "", "active_themes": []}
    # Extract the blockquote
    m = re.search(r'>\s*(.+?)(?:\n\n|\n\*\*)', text, re.DOTALL)
    if m:
        result["text"] = m.group(1).strip()
    # Extract active themes
    tm = re.search(r'\*\*活跃主题\*\*[：:]\s*(.+)', text)
    if tm:
        themes = re.findall(r'`([^`]+)`', tm.group(1))
        result["active_themes"] = themes
    return result


def parse_structural_shifts(text):
    """Parse Section 2: Structural Shifts. Returns list of shift objects."""
    shifts = []
    # Split by ### headers
    blocks = re.split(r'\n### ', text)
    for block in blocks[1:]:  # Skip content before first ###
        block = block.strip()
        # First line is the title
        lines = block.split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[1:])

        shift = {"title": title, "mechanism": "", "trigger": "", "consequence": "",
                 "impact": "medium", "time_horizon": "medium", "source": ""}

        mech = re.search(r'\*\*机制\*\*[：:]\s*(.+?)(?:\n\*\*|$)', body, re.DOTALL)
        if mech: shift["mechanism"] = mech.group(1).strip()

        trig = re.search(r'\*\*触发\*\*[：:]\s*(.+?)(?:\n\*\*|$)', body, re.DOTALL)
        if trig: shift["trigger"] = trig.group(1).strip()

        cons = re.search(r'\*\*后果\*\*[：:]\s*(.+?)(?:\n\n|\n\*|$)', body, re.DOTALL)
        if cons: shift["consequence"] = cons.group(1).strip()

        # Impact line: "影响：🔴 high | 时间维度：medium"
        imp = re.search(r'影响[：:]\s*\S*\s*(\w+)', body)
        if imp: shift["impact"] = imp.group(1).strip()

        th = re.search(r'时间维度[：:]\s*(\w+)', body)
        if th: shift["time_horizon"] = th.group(1).strip()

        src = re.search(r'\*([^*]+)\*', body.split('\n')[-1] if body.split('\n') else '')
        if not src:
            src = re.search(r'\*([^*]+)\*', body)
        if src: shift["source"] = src.group(1).strip()

        shifts.append(shift)

    return shifts


def parse_event_ledger(text):
    """Parse Section 3: Event Ledger."""
    result = {"capability": [], "behavioral": []}

    # Split by **⚡** and **👥** markers
    cap_match = re.search(r'\*\*⚡\s*Capability\*\*\s*\n(.*?)(?:\n\s*\n\*\*👥|\Z)', text, re.DOTALL)
    if cap_match:
        for line in cap_match.group(1).strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # Format: "1. event text *(source)*"
            m = re.match(r'\d+\.\s*(.+?)\s*\*\(([^)]+)\)\*', line)
            if m:
                result["capability"].append({"title": m.group(1).strip(), "source": m.group(2).strip()})

    beh_match = re.search(r'\*\*👥\s*Behavioral\*\*\s*\n(.*?)(?:\n\s*\n##|\Z)', text, re.DOTALL)
    if beh_match:
        for line in beh_match.group(1).strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'\d+\.\s*(.+?)\s*\*\(([^)]+)\)\*', line)
            if m:
                result["behavioral"].append({"title": m.group(1).strip(), "source": m.group(2).strip()})

    return result


def parse_signal_map(text):
    """Parse Section 4: Signal Map."""
    result = {"synthesis": "", "causal_chain": "", "supporting_events": []}

    # First ### header is the synthesis title
    blocks = re.split(r'\n### ', text)
    if len(blocks) > 1:
        block = blocks[1]
        lines = block.split('\n')
        result["synthesis"] = lines[0].strip() if lines else ""

    # Causal chain
    cc = re.search(r'\*\*因果链\*\*[：:]\s*(.+?)(?:\n\n|$)', text, re.DOTALL)
    if cc: result["causal_chain"] = cc.group(1).strip()

    # Supporting events
    se = re.search(r'\*\*支撑事件\*\*[：:]\s*(.+?)(?:\n\n|$)', text, re.DOTALL)
    if se:
        events_text = se.group(1).strip()
        result["supporting_events"] = [e.strip() for e in events_text.split('、') if e.strip()]

    return result


def parse_risk_layer(text):
    """Parse Section 5: Risk Layer."""
    risks = []
    for line in text.split('\n'):
        line = line.strip()
        if not line.startswith('- ['):
            continue
        # Format: "- [🫧 bubble] [now] [主题:theme_key] description"
        m = re.match(r'-\s*\[[^\]]*?\s*(\w+)\]\s*\[(\w+)\]\s*\[主题[：:]\s*`?(\w+)`?\]\s*(.+)', line)
        if m:
            risks.append({
                "type": m.group(1),
                "horizon": m.group(2),
                "theme": m.group(3),
                "description": m.group(4).strip()
            })
    return risks


def parse_decision_hooks(text):
    """Parse Section 6: Decision Hooks."""
    hooks = {"developer": [], "founder": [], "investor": []}

    persona_map = {"开发者": "developer", "创业者": "founder", "投资人": "investor"}

    # Split by persona headers
    for cn_label, en_key in persona_map.items():
        # Find this persona's section
        pattern = rf'\*\*{cn_label}\*\*\s*\n(.*?)(?:\n\s*\n\*\*|\Z)'
        m = re.search(pattern, text, re.DOTALL)
        if not m:
            continue

        persona_text = m.group(1)
        # Parse each hook: "1. **触发**：... **动作**：... — *rationale* [`priority`]"
        hooks_list = re.findall(
            r'\d+\.\s*\*\*触发\*\*[：:]\s*(.+?)\s*\*\*动作\*\*[：:]\s*(.+?)\s*—\s*\*(.+?)\*\s*\[`(\w+)`\]',
            persona_text
        )
        for trigger, action, rationale, priority in hooks_list:
            hooks[en_key].append({
                "trigger": trigger.strip(),
                "action": action.strip(),
                "rationale": rationale.strip(),
                "priority": priority.strip()
            })

    return hooks


def parse_counter_signal(text):
    """Parse Counter Signal section if present."""
    result = {}
    mn = re.search(r'\*\*主流叙事\*\*[：:]\s*(.+?)(?:\n\*\*|$)', text, re.DOTALL)
    if mn: result["main_narrative"] = mn.group(1).strip()

    ce = re.search(r'\*\*反向信号\*\*[：:]\s*(.+?)(?:\n\*\*|$)', text, re.DOTALL)
    if ce: result["counter_event"] = ce.group(1).strip()

    tn = re.search(r'\*\*为什么值得注意\*\*[：:]\s*(.+?)(?:\n\n|\n\*|$)', text, re.DOTALL)
    if tn: result["why_matters"] = tn.group(1).strip()

    src = re.search(r'\*\(([^)]+)\)\*', text)
    if src: result["source"] = src.group(1).strip()

    return result if result else None


def parse_meta(text):
    """Extract metadata from footer."""
    meta = {}
    health = re.search(r'信源健康[：:]\s*(\S+)', text)
    if health: meta["source_health"] = health.group(1)

    calls = re.search(r'(\d+)\s*次调用', text)
    if calls: meta["api_calls"] = int(calls.group(1))

    inp = re.search(r'输入\s*([\d,]+)\s*tokens', text)
    if inp: meta["input_tokens"] = int(inp.group(1).replace(',', ''))

    outp = re.search(r'输出\s*([\d,]+)\s*tokens', text)
    if outp: meta["output_tokens"] = int(outp.group(1).replace(',', ''))

    return meta


def extract_content_ir(markdown_text):
    """Parse full Markdown and return Content IR dict."""
    date = parse_date(markdown_text) or datetime.now().strftime("%Y-%m-%d")

    # Split into sections by ## headers
    sections = {}
    current_section = None
    current_text = []

    for line in markdown_text.split('\n'):
        if line.startswith('## '):
            if current_section:
                sections[current_section] = '\n'.join(current_text)
            current_section = line[3:].strip()
            current_text = []
        elif current_section:
            current_text.append(line)
    if current_section:
        sections[current_section] = '\n'.join(current_text)

    # Parse each section
    ir = {
        "content_ir_version": CONTENT_IR_VERSION,
        "pipeline": "ai-daily",
        "date": date,
        "generated_at": datetime.now().isoformat(),
    }

    for section_title, section_text in sections.items():
        if 'Executive Judgment' in section_title or '今日判断' in section_title:
            ir["executive_judgment"] = parse_executive_judgment(section_text)
        elif 'Structural Shift' in section_title or '结构' in section_title or '核心变量' in section_title:
            ir["structural_shifts"] = parse_structural_shifts(section_text)
        elif 'Event Ledger' in section_title or '事件' in section_title:
            ir["events"] = parse_event_ledger(section_text)
        elif 'Signal Map' in section_title or '信号' in section_title:
            ir["signal_map"] = parse_signal_map(section_text)
        elif 'Risk' in section_title or '风险' in section_title:
            ir["risk_layer"] = parse_risk_layer(section_text)
        elif 'Decision Hook' in section_title or '行动' in section_title:
            ir["decision_hooks"] = parse_decision_hooks(section_text)
        elif 'Counter Signal' in section_title or '反向信号' in section_title:
            cs = parse_counter_signal(section_text)
            if cs:
                ir["counter_signal"] = cs

    # Extract meta from footer
    ir["meta"] = parse_meta(markdown_text)

    # Ensure required fields exist
    if "executive_judgment" not in ir:
        ir["executive_judgment"] = {"text": "", "active_themes": []}
    if "structural_shifts" not in ir:
        ir["structural_shifts"] = []
    if "events" not in ir:
        ir["events"] = {"capability": [], "behavioral": []}
    if "signal_map" not in ir:
        ir["signal_map"] = {"synthesis": "", "causal_chain": "", "supporting_events": []}
    if "risk_layer" not in ir:
        ir["risk_layer"] = []
    if "decision_hooks" not in ir:
        ir["decision_hooks"] = {"developer": [], "founder": [], "investor": []}

    return ir


# ═══════════════════════════════════════════════
# §2 Content IR → Visual Plan Mapping
# ═══════════════════════════════════════════════

def content_ir_to_visual_plan(ir):
    """
    Map Content IR to a Visual Plan for the deterministic visual compiler.

    Rules (from CONTENT-IR-SPEC-v1.md §4):
      1. Max 5 images
      2. INSIGHT_FRAME mandatory (from executive_judgment)
      3. STRUCTURE_MAP if ≥1 structural shift
      4. FLOW_DIAGRAM if signal_map.synthesis exists
      5. COMPARISON_PANEL if ≥2 risk items
      6. DATA_CARD for events (dropped first if >5 images)
    """
    images = []

    # 1. INSIGHT_FRAME (mandatory)
    ej = ir.get("executive_judgment", {})
    judgment_text = ej.get("text", "今日无特殊判断")
    images.append({
        "id": "insight_frame",
        "type": "INSIGHT_FRAME",
        "template": "ONE_LINE_TRUTH",
        "priority": "primary",
        "purpose": "今日核心判断",
        "content": {
            "line1": f"AI日报 · {ir.get('date', '')}",
            "line2": judgment_text[:120]
        }
    })

    # 2. STRUCTURE_MAP (if structural shifts exist)
    shifts = ir.get("structural_shifts", [])
    if shifts:
        layers = []
        for s in shifts[:4]:  # Max 4 layers
            impact_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.get("impact", "medium"), "🟡")
            layers.append({
                "name": s.get("title", "")[:30],
                "desc": s.get("mechanism", "")[:80],
                "tag": f'{impact_emoji} {s.get("impact", "?")} | {s.get("time_horizon", "?")}\n{s.get("source", "")}',
                "color": {"high": "#ef4444", "medium": "#f59e0b", "low": "#3b82f6"}.get(s.get("impact", "medium"), "#f59e0b")
            })
        if layers:
            images.append({
                "id": "structure_map",
                "type": "STRUCTURE_MAP",
                "template": "LAYERED_SYSTEM",
                "priority": "primary",
                "purpose": "结构性变化层级图",
                "content": {
                    "title": "结构性变化",
                    "subtitle": f"{ir.get('date', '')} · {len(shifts)} 项变化",
                    "layers": layers
                }
            })

    # 3. FLOW_DIAGRAM (if signal map exists)
    sm = ir.get("signal_map", {})
    if sm.get("synthesis") or sm.get("causal_chain"):
        nodes = []
        # Synthesis → supporting events → consequences as flow
        if sm.get("synthesis"):
            nodes.append({"label": "信号合成", "desc": sm["synthesis"][:60], "color": "#3b82f6"})
        for i, event in enumerate(sm.get("supporting_events", [])[:3]):
            nodes.append({"label": f"支撑事件 {i+1}", "desc": event[:60], "color": "#f59e0b"})
        if sm.get("causal_chain"):
            nodes.append({"label": "因果链", "desc": sm["causal_chain"][:60], "color": "#10b981"})

        if nodes:
            images.append({
                "id": "signal_flow",
                "type": "FLOW_DIAGRAM",
                "template": "VALUE_FLOW",
                "priority": "primary" if len(shifts) == 0 else "secondary",
                "purpose": "信号流向与因果链",
                "content": {
                    "title": "信号流向",
                    "nodes": nodes
                }
            })

    # 4. COMPARISON_PANEL (risks: bubble/sentiment vs structural/regime)
    risks = ir.get("risk_layer", [])
    if len(risks) >= 2:
        bubble_risks = [r for r in risks if r.get("type") == "bubble"]
        struct_risks = [r for r in risks if r.get("type") in ("structural", "regime")]

        left_items = [r["description"][:60] for r in bubble_risks[:3]] or ["无短期泡沫风险"]
        right_items = [r["description"][:60] for r in struct_risks[:3]] or ["无结构性风险"]

        images.append({
            "id": "risk_panel",
            "type": "COMPARISON_PANEL",
            "template": "LEFT_RIGHT_CONTRAST",
            "priority": "secondary",
            "purpose": "风险对比：泡沫 vs 结构性",
            "content": {
                "title": "风险层对比",
                "left": {"label": "泡沫/情绪风险", "items": left_items, "roi": "短期关注"},
                "right": {"label": "结构/范式风险", "items": right_items, "roi": "中长期关注"},
            }
        })

    # 5. DATA_CARD (events summary)
    events = ir.get("events", {})
    cap_events = events.get("capability", [])
    beh_events = events.get("behavioral", [])
    all_events = cap_events + beh_events
    if all_events:
        cards = []
        for e in all_events[:3]:
            cards.append({
                "cost": str(len(cap_events) if e in cap_events else len(beh_events)),
                "layer": e["title"][:30],
                "desc": e.get("source", "")[:40],
                "color": "#3b82f6" if e in cap_events else "#f59e0b"
            })
        if cards:
            images.append({
                "id": "event_cards",
                "type": "DATA_CARD",
                "template": "LARGE_NUMBER_FOCUS",
                "priority": "secondary",
                "purpose": "事件概览",
                "content": {
                    "title": "今日事件",
                    "subtitle": f"能力 {len(cap_events)} · 行为 {len(beh_events)}",
                }
            })

    # Enforce max 5 images: drop DATA_CARD first, then COMPARISON_PANEL
    if len(images) > 5:
        # Remove secondary-priority images first
        for drop_type in ["DATA_CARD", "COMPARISON_PANEL"]:
            while len(images) > 5:
                for i, img in enumerate(images):
                    if img["type"] == drop_type:
                        images.pop(i)
                        break
                else:
                    break

    return {"images": images}


# ═══════════════════════════════════════════════
# §3 CLI
# ═══════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: content-bridge.py <markdown_file> [--save <ir_path>] [--visual <out_dir>]")
        print("       content-bridge.py --batch <output_dir> [--visual]")
        sys.exit(1)

    if sys.argv[1] == '--batch':
        batch_dir = sys.argv[2]
        do_visual = '--visual' in sys.argv
        md_files = sorted(Path(batch_dir).glob('morning-*.md'))
        if not md_files:
            print(f"No morning-*.md files in {batch_dir}")
            sys.exit(1)
        print(f"Processing {len(md_files)} reports...")
        for md_file in md_files:
            date = parse_date(md_file.read_text())
            print(f"  {date}: {md_file.name}")
            ir = extract_content_ir(md_file.read_text())
            ir_path = md_file.with_suffix('.ir.json')
            with open(ir_path, 'w') as f:
                json.dump(ir, f, indent=2, ensure_ascii=False)
            if do_visual:
                _compile_visual(ir, str(md_file.parent / f'visual-{date}'))
        print(f"Done. {len(md_files)} Content IR files written.")
        return

    md_path = sys.argv[1]
    with open(md_path) as f:
        md_text = f.read()

    ir = extract_content_ir(md_text)

    save_path = None
    visual_out = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--save' and i + 1 < len(args):
            save_path = args[i + 1]
            i += 2
        elif args[i] == '--visual' and i + 1 < len(args):
            visual_out = args[i + 1]
            i += 2
        else:
            i += 1

    if visual_out:
        _compile_visual(ir, visual_out)
        print(f"Visual compiled → {visual_out}")

    if save_path:
        os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump(ir, f, indent=2, ensure_ascii=False)
        print(f"Content IR saved → {save_path}")
    elif not visual_out:
        print(json.dumps(ir, indent=2, ensure_ascii=False))


def _compile_visual(ir, out_dir):
    """Feed Content IR through the Visual Compiler pipeline."""
    out_dir = os.path.abspath(out_dir)
    visual_plan = content_ir_to_visual_plan(ir)

    os.makedirs(out_dir, exist_ok=True)
    plan_path = os.path.join(out_dir, 'visual_plan.json')
    with open(plan_path, 'w') as f:
        json.dump(visual_plan, f, indent=2, ensure_ascii=False)

    if os.path.exists(VISUAL_COMPILER):
        vkernel = os.path.join(VISUAL_COMPILER, 'vkernel.py')
        render = os.path.join(VISUAL_COMPILER, 'render.py')
        if os.path.exists(vkernel):
            subprocess.run([sys.executable, vkernel, plan_path, out_dir], check=True)
            png_dir = os.path.join(out_dir, 'images')
            if os.path.exists(render):
                subprocess.run([sys.executable, render, out_dir, png_dir], check=True)
    else:
        print(f"Visual compiler not found at {VISUAL_COMPILER}")
        print(f"Visual plan saved to {plan_path}")


if __name__ == '__main__':
    main()
