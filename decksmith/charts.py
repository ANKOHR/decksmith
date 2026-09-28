"""Fixture-bound, deterministic SVG chart generators."""

from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any

from .io import csv_records, read_json, source_ref, write_json


PALETTE = ["#2C6E73", "#E5A94F", "#A85D46", "#6586A6", "#8B789F", "#8A9B68"]


def _source_label(dataset: str, count: int) -> tuple[dict[str, Any], str]:
    ref = source_ref(dataset, 2, count + 1, f"all {count} data rows")
    caption = f"Source: {dataset}, rows 2-{count + 1}"
    return ref, caption


def _svg_header(title: str) -> list[str]:
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 500" role="img" aria-label="' + html.escape(title, quote=True) + '">',
        '<rect width="900" height="500" fill="#F8F6F1"/>',
        '<text x="52" y="48" class="title">' + html.escape(title) + '</text>',
        '<style>text{font-family:Arial,sans-serif;fill:#24343A}.title{font-size:24px;font-weight:700}.label{font-size:15px}.small{font-size:13px}.axis{stroke:#9BA8A4;stroke-width:1}.series{fill:none;stroke:#2C6E73;stroke-width:4}.point{fill:#E5A94F;stroke:#24343A;stroke-width:1}</style>',
    ]


def _footer(svg: list[str], source_text: str) -> str:
    svg.extend([
        '<rect x="52" y="430" width="143" height="28" rx="4" fill="#24343A"/>',
        '<text x="63" y="449" fill="#FFFFFF" style="fill:#FFFFFF;font-size:13px;font-weight:700">SYNTHETIC DATA</text>',
        '<text x="210" y="449" class="small">' + html.escape(source_text) + '</text>',
        '</svg>',
    ])
    return "\n".join(svg) + "\n"


def _line_chart(spec: dict[str, Any], rows: list[dict[str, str]], source_text: str) -> str:
    values = [float(row[spec["value_column"]]) for row in rows]
    low, high = min(values), max(values)
    spread = max(high - low, 1.0)
    points = []
    for index, value in enumerate(values):
        x = 95 + index * (710 / max(len(values) - 1, 1))
        y = 350 - ((value - low) / spread) * 220
        points.append((x, y, value, rows[index][spec["label_column"]]))
    svg = _svg_header(spec["title"])
    svg.append('<line x1="75" y1="350" x2="830" y2="350" class="axis"/>')
    svg.append('<line x1="75" y1="105" x2="75" y2="350" class="axis"/>')
    svg.append('<polyline class="series" points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y, _, _ in points) + '"/>')
    for x, y, value, label in points:
        svg.append(f'<circle class="point" cx="{x:.2f}" cy="{y:.2f}" r="7"/>')
        svg.append(f'<text x="{x:.2f}" y="{y - 13:.2f}" text-anchor="middle" class="label">{value:g}</text>')
        svg.append(f'<text x="{x:.2f}" y="378" text-anchor="middle" class="label">{html.escape(label)}</text>')
    return _footer(svg, source_text)


def _bar_chart(spec: dict[str, Any], rows: list[dict[str, str]], source_text: str) -> str:
    values = [float(row[spec["value_column"]]) for row in rows]
    maximum = max(values) or 1
    svg = _svg_header(spec["title"])
    svg.append('<line x1="75" y1="350" x2="830" y2="350" class="axis"/>')
    slot = 710 / len(rows)
    for index, (row, value) in enumerate(zip(rows, values)):
        height = value / maximum * 235
        x = 95 + index * slot
        y = 350 - height
        svg.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{slot * .62:.2f}" height="{height:.2f}" rx="3" fill="{PALETTE[index % len(PALETTE)]}"/>')
        svg.append(f'<text x="{x + slot * .31:.2f}" y="{y - 10:.2f}" text-anchor="middle" class="label">{value:g}</text>')
        svg.append(f'<text x="{x + slot * .31:.2f}" y="378" text-anchor="middle" class="label">{html.escape(row[spec["label_column"]])}</text>')
    return _footer(svg, source_text)


def _donut_chart(spec: dict[str, Any], rows: list[dict[str, str]], source_text: str) -> str:
    values = [float(row[spec["value_column"]]) for row in rows]
    total = sum(values)
    svg = _svg_header(spec["title"])
    cx, cy, radius = 300.0, 260.0, 125.0
    consumed = 0.0
    circumference = 2 * math.pi * radius
    for index, (row, value) in enumerate(zip(rows, values)):
        fraction = value / total
        length = circumference * fraction
        svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="none" stroke="{PALETTE[index % len(PALETTE)]}" stroke-width="58" stroke-dasharray="{length:.4f} {circumference - length:.4f}" stroke-dashoffset="{circumference * (1 - consumed):.4f}" transform="rotate(-90 300 260)"/>')
        legend_y = 168 + index * 47
        svg.append(f'<rect x="540" y="{legend_y - 15}" width="18" height="18" rx="3" fill="{PALETTE[index % len(PALETTE)]}"/>')
        share = value / total * 100
        svg.append(f'<text x="570" y="{legend_y}" class="label">{html.escape(row[spec["label_column"]])}: {value:g} ({share:.1f}%)</text>')
        consumed += fraction
    svg.append('<text x="300" y="257" text-anchor="middle" class="label">SYNTHETIC</text>')
    svg.append('<text x="300" y="282" text-anchor="middle" class="small">fixture total</text>')
    return _footer(svg, source_text)


def render_chart(spec: dict[str, Any], rows: list[dict[str, str]]) -> str:
    if spec["type"] not in {"line", "bar", "donut"}:
        raise ValueError(f"Unsupported chart type: {spec['type']}")
    _, source_text = _source_label(spec["dataset"], len(rows))
    generator = {"line": _line_chart, "bar": _bar_chart, "donut": _donut_chart}[spec["type"]]
    return generator(spec, rows, source_text)


def generate_charts(pack: Path, figures_path: Path, out: Path | None = None) -> Path:
    root = pack.expanduser().resolve()
    figures = read_json(figures_path)
    if figures.get("synthetic") is not True:
        raise ValueError("Figures must be labelled synthetic")
    target = out.expanduser().resolve() if out else root / "charts"
    target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for spec in figures["charts"]:
        relative = Path(spec["dataset"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Fixture dataset path escapes the pack: {spec['dataset']}")
        dataset_path = (root / relative).resolve()
        if root not in dataset_path.parents:
            raise ValueError(f"Fixture dataset path escapes the pack: {spec['dataset']}")
        rows = csv_records(dataset_path)
        source, _ = _source_label(spec["dataset"], len(rows))
        svg = render_chart(spec, rows)
        filename = f"{spec['id']}.svg"
        (target / filename).write_text(svg, encoding="utf-8", newline="\n")
        manifest.append({"id": spec["id"], "type": spec["type"], "title": spec["title"], "file": filename, "dataset": spec["dataset"], "label_column": spec["label_column"], "value_column": spec["value_column"], "source": source})
    write_json(target / "charts_manifest.json", {"synthetic": True, "charts": manifest})
    return target
