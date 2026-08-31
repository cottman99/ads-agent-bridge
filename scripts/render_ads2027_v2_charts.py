from __future__ import annotations

import argparse
import html
import json
import statistics
from pathlib import Path
from typing import Any


CASE_ORDER = ("K1", "K3", "K6", "E3")
ROW_ORDER = (
    ("codex", "bridge_a29", "Codex · Bridge a29"),
    ("codex", "bridge_a48", "Codex · Bridge a48"),
    ("codex", "official", "Codex · Official MCP"),
    ("pi", "bridge_a48", "Pi Agent · Bridge a48"),
    ("pi", "official", "Pi Agent · Official MCP"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path, required=True)
    parser.add_argument("--headless-svg", type=Path, required=True)
    parser.add_argument("--knowledge-svg", type=Path, required=True)
    return parser.parse_args()


def aggregate(source: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for agent, arm, _label in ROW_ORDER:
        for case_id in CASE_ORDER:
            runs = [
                run
                for run in source["runs"]
                if run.get("agent") == agent
                and run["arm"] == arm
                and run["case"] == case_id
            ]
            if not runs:
                continue
            rows.append(
                {
                    "agent": agent,
                    "arm": arm,
                    "case": case_id,
                    "passes": sum(run["status"] == "pass" for run in runs),
                    "runs": len(runs),
                    "median_wall_seconds": round(
                        statistics.median(run["wall_seconds"] for run in runs), 3
                    ),
                    "min_wall_seconds": round(
                        min(run["wall_seconds"] for run in runs), 3
                    ),
                    "max_wall_seconds": round(
                        max(run["wall_seconds"] for run in runs), 3
                    ),
                    "median_total_tokens": round(
                        statistics.median(run["total_tokens"] for run in runs)
                    ),
                }
            )
    return rows


def svg_text(
    x: float, y: float, text: str, class_name: str, anchor: str = "start"
) -> str:
    return (
        f'<text x="{x:g}" y="{y:g}" class="{class_name}" '
        f'text-anchor="{anchor}">{html.escape(text)}</text>'
    )


def svg_shell(title: str, description: str, body: list[str], height: int = 520) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="{height}" viewBox="0 0 1120 {height}" role="img" aria-labelledby="title desc">',
            f'  <title id="title">{html.escape(title)}</title>',
            f'  <desc id="desc">{html.escape(description)}</desc>',
            "  <style>",
            "    .title{font:700 25px Inter,Segoe UI,sans-serif;fill:#152233}",
            "    .subtitle{font:14px Inter,Segoe UI,sans-serif;fill:#526071}",
            "    .label{font:600 14px Inter,Segoe UI,sans-serif;fill:#263548}",
            "    .value{font:700 13px ui-monospace,SFMono-Regular,Consolas,monospace;fill:#152233}",
            "    .axis{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;fill:#697789}",
            "    .note{font:12px Inter,Segoe UI,sans-serif;fill:#697789}",
            "    .grid{stroke:#dfe5ec;stroke-width:1}",
            "  </style>",
            '  <rect width="1120" height="100%" fill="#ffffff"/>',
            *[f"  {line}" for line in body],
            "</svg>",
            "",
        ]
    )


def render_headless(rows: list[dict[str, Any]]) -> str:
    selected = [
        next(
            row
            for row in rows
            if row["agent"] == agent and row["arm"] == arm and row["case"] == "E3"
        )
        for agent, arm, _label in ROW_ORDER
    ]
    body = [
        svg_text(40, 42, "ADS 2027 headless AC execution", "title"),
        svg_text(
            40,
            68,
            "Median end-to-end wall time; whiskers show the three-run range. Every E3 run passed.",
            "subtitle",
        ),
    ]
    left, top, scale = 260, 120, 7.0
    for tick in range(0, 101, 20):
        x = left + tick * scale
        body.append(f'<line x1="{x}" y1="{top - 12}" x2="{x}" y2="430" class="grid"/>')
        body.append(svg_text(x, 452, f"{tick}s", "axis", "middle"))
    colors = {"bridge_a29": "#94a3b8", "bridge_a48": "#2f6fed", "official": "#e3a12f"}
    for index, ((agent, arm, label), row) in enumerate(
        zip(ROW_ORDER, selected, strict=True)
    ):
        y = top + index * 62
        median = row["median_wall_seconds"]
        minimum = row["min_wall_seconds"]
        maximum = row["max_wall_seconds"]
        body.append(svg_text(40, y + 20, label, "label"))
        body.append(
            f'<rect x="{left}" y="{y}" width="{median * scale:.1f}" height="28" rx="4" fill="{colors[arm]}"/>'
        )
        body.append(
            f'<line x1="{left + minimum * scale:.1f}" y1="{y + 14}" x2="{left + maximum * scale:.1f}" y2="{y + 14}" stroke="#152233" stroke-width="2"/>'
        )
        for value in (minimum, maximum):
            x = left + value * scale
            body.append(
                f'<line x1="{x:.1f}" y1="{y + 8}" x2="{x:.1f}" y2="{y + 20}" stroke="#152233" stroke-width="2"/>'
            )
        body.append(
            svg_text(
                min(left + maximum * scale + 10, 1005),
                y + 20,
                f"{median:.1f}s · {row['passes']}/{row['runs']}",
                "value",
            )
        )
    body.append(
        svg_text(
            40,
            495,
            "ADS 2027 · gpt-5.6-terra medium · serial counterbalanced · 3 repetitions per row · 2026-09-01",
            "note",
        )
    )
    return svg_shell(
        "ADS 2027 headless AC execution benchmark",
        "Five rows compare median wall time and range for Codex or Pi Agent using Bridge a29, Bridge a48, or the official ADS MCP. All headless execution runs passed.",
        body,
    )


def render_knowledge(rows: list[dict[str, Any]]) -> str:
    body = [
        svg_text(40, 42, "ADS 2027 knowledge reliability", "title"),
        svg_text(
            40,
            68,
            "Strict passes in three repetitions. Exact cells reveal which boundary fails; darker means more passes.",
            "subtitle",
        ),
    ]
    columns = (
        ("K1", "Route + boundary"),
        ("K3", "Geometry API"),
        ("K6", "DRC boundary"),
    )
    left, top, cell_w, cell_h = 300, 120, 180, 48
    for index, (_case_id, label) in enumerate(columns):
        body.append(svg_text(left + index * cell_w + 80, 103, label, "label", "middle"))
    body.append(
        svg_text(left + 3 * cell_w + 80, 103, "Knowledge total", "label", "middle")
    )
    fills = {0: "#ffffff", 1: "#dce8ff", 2: "#91b3f7", 3: "#2f6fed"}
    for row_index, (agent, arm, label) in enumerate(ROW_ORDER):
        y = top + row_index * 62
        body.append(svg_text(40, y + 30, label, "label"))
        case_rows = {
            case_id: next(
                row
                for row in rows
                if row["agent"] == agent
                and row["arm"] == arm
                and row["case"] == case_id
            )
            for case_id, _column_label in columns
        }
        for column_index, (case_id, _column_label) in enumerate(columns):
            result = case_rows[case_id]
            passes = result["passes"]
            x = left + column_index * cell_w
            body.append(
                f'<rect x="{x}" y="{y}" width="160" height="{cell_h}" rx="5" fill="{fills[passes]}" stroke="#627086"/>'
            )
            color = "#ffffff" if passes == 3 else "#152233"
            body.append(
                f'<text x="{x + 80}" y="{y + 30}" text-anchor="middle" class="value" fill="{color}" style="fill:{color}">{passes}/3</text>'
            )
        total = sum(result["passes"] for result in case_rows.values())
        x = left + 3 * cell_w
        total_fill = "#2f6fed" if total == 9 else "#91b3f7" if total >= 7 else "#dce8ff"
        body.append(
            f'<rect x="{x}" y="{y}" width="160" height="{cell_h}" rx="5" fill="{total_fill}" stroke="#627086"/>'
        )
        total_color = "#ffffff" if total == 9 else "#152233"
        body.append(
            f'<text x="{x + 80}" y="{y + 30}" text-anchor="middle" class="value" style="fill:{total_color}">{total}/9</text>'
        )
    body.append(svg_text(300, 452, "Passes:", "axis"))
    for index, passes in enumerate((0, 1, 2, 3)):
        x = 345 + index * 70
        body.append(
            f'<rect x="{x}" y="440" width="24" height="16" rx="2" fill="{fills[passes]}" stroke="#627086"/>'
        )
        body.append(svg_text(x + 30, 453, str(passes), "axis"))
    body.append(
        svg_text(
            40,
            495,
            "K1 route · K3 rectangle/polygon/path · K6 reject unverified Python DRC · 3 repetitions · 2026-09-01",
            "note",
        )
    )
    return svg_shell(
        "ADS 2027 knowledge reliability benchmark",
        "A matrix shows strict passes out of three for route selection, geometry API use, and the Python DRC capability boundary across Codex and Pi Agent product combinations.",
        body,
    )


def main() -> int:
    args = parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    rows = aggregate(source)
    public = {
        "schema": "ads-agent-public-benchmark/v2",
        "benchmark_id": "ads2027-current-regression-20260901",
        "date": "2026-09-01",
        "identities": {
            "ads": "ADS 2027",
            "bridge_historical": "ads-agent-bridge 0.1.0a29",
            "bridge_current": "ads-agent-bridge 0.1.0a48",
            "official_mcp_sha256": "b68afcc4e904fae576a3c139898f877261fe9266a5235313ec46d48a2d0e4783",
            "codex": "Codex CLI 0.145.0",
            "pi": "Pi Agent 0.84.4",
            "model": "gpt-5.6-terra",
            "reasoning_effort": "medium",
        },
        "protocol": {
            "execution": "serial-counterbalanced",
            "repetitions": 3,
            "calibration_excluded": True,
            "fresh_agent_home_per_run": True,
            "isolation_violations": 0,
            "pi_official_transport": "thin MCP forwarding extension; no added domain knowledge",
        },
        "rows": rows,
    }
    args.public_summary.parent.mkdir(parents=True, exist_ok=True)
    args.headless_svg.parent.mkdir(parents=True, exist_ok=True)
    with args.public_summary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(public, indent=2) + "\n")
    with args.headless_svg.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_headless(rows))
    with args.knowledge_svg.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_knowledge(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
