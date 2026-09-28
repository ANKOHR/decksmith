"""Slide assembly, HTML rendering, and Markdown source generation."""

from __future__ import annotations

import base64
import html
import json
import os
import re
from pathlib import Path
from typing import Any

from .io import canonical_json, read_json, write_json


MIN_SLIDES = 12
MAX_SLIDES = 20


def _display(value: Any) -> str:
    if isinstance(value, dict) and set(value) == {"low", "high"}:
        return f"{_display(value['low'])} to {_display(value['high'])}"
    if isinstance(value, list):
        if value and isinstance(value[0], dict) and "group" in value[0]:
            return str(value[0]["group"])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _substitute(template: str, figures: dict[str, Any], gaps: dict[str, Any], notes: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        kind, key = match.group(1), match.group(2)
        if kind == "figure":
            if key not in figures:
                raise ValueError(f"Slide references unknown figure: {key}")
            return _display(figures[key]["value"])
        if kind == "gap":
            if key not in gaps:
                raise ValueError(f"Slide references unknown evidence gap: {key}")
            return gaps[key]["statement"]
        if kind == "note":
            if key not in notes:
                raise ValueError(f"Slide references unknown note: {key}")
            return notes[key]
        raise ValueError(f"Unknown template token: {kind}")

    return re.sub(r"\{(figure|gap|note):([A-Za-z0-9_-]+)\}", replace, template)


def _source_caption(ref: dict[str, Any]) -> str:
    if "line_start" in ref:
        location = f"lines {ref['line_start']}-{ref['line_end']}"
    else:
        location = str(ref.get("location", "fixture table"))
    return f"{ref['file']}, {location}"


def _unique_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: dict[tuple[str, int, int], dict[str, Any]] = {}
    for ref in refs:
        key = (ref["file"], int(ref.get("line_start", 0)), int(ref.get("line_end", 0)))
        if key not in found:
            found[key] = ref
    return [found[key] for key in sorted(found)]


def create_model(plan: dict[str, Any], figures_file: dict[str, Any], charts_dir: Path, pack_root: Path, output_dir: Path) -> dict[str, Any]:
    slides = plan.get("slides", [])
    if not MIN_SLIDES <= len(slides) <= MAX_SLIDES:
        raise ValueError(f"Slide count must be between {MIN_SLIDES} and {MAX_SLIDES}; got {len(slides)}")
    if plan.get("synthetic") is not True or figures_file.get("synthetic") is not True:
        raise ValueError("Deck inputs must be labelled synthetic")
    figure_data = figures_file["figures"]
    gaps = {item["gap_id"]: item for item in plan["gaps"]}
    notes_lines = (pack_root / "research_notes.md").read_text(encoding="utf-8").splitlines()
    notes = {
        "recommended_next_step": notes_lines[8].split(": ", 1)[-1],
    }
    chart_manifest = read_json(charts_dir / "charts_manifest.json")
    if chart_manifest.get("synthetic") is not True:
        raise ValueError("Chart manifest must be labelled synthetic")
    chart_index = {chart["id"]: chart for chart in chart_manifest["charts"]}
    chart_content: dict[str, str] = {}
    model_slides = []
    for slide in slides:
        claim = _substitute(slide["claim"], figure_data, gaps, notes)
        title = slide["title"]
        source_refs = list(slide.get("evidence", []))
        slide_figures = []
        for figure_id in slide.get("figures", []):
            figure = figure_data[figure_id]
            slide_figures.append({"id": figure_id, **figure})
            source_refs.extend(figure["source"])
        chart_id = slide.get("chart")
        chart = None
        if chart_id:
            if chart_id not in chart_index:
                raise ValueError(f"Slide references missing chart: {chart_id}")
            spec = chart_index[chart_id]
            svg = (charts_dir / spec["file"]).read_text(encoding="utf-8")
            chart_content[chart_id] = svg
            chart = {**spec, "svg": svg}
            source_refs.extend([spec["source"]])
        uncertainty = slide.get("uncertainty")
        if uncertainty:
            uncertainty = {**uncertainty, "callout": _substitute(uncertainty["callout"], figure_data, gaps, notes)}
        refs = _unique_refs(source_refs)
        model_slides.append({
            "id": slide["id"], "number": len(model_slides) + 1, "type": slide["type"], "arc": slide["arc"],
            "title": title, "claim": claim, "evidence": refs,
            "citations": [_source_caption(ref) for ref in refs], "figures": slide_figures,
            "chart": chart, "uncertainty": uncertainty,
        })
    relative_pack = os.path.relpath(pack_root.resolve(), output_dir.resolve()).replace("\\", "/")
    return {
        "format_version": 1,
        "synthetic": True,
        "label": "SYNTHETIC DATA - FICTIONAL EXAMPLE, NOT REAL-WORLD RESEARCH",
        "topic": plan["topic"],
        "plan_hash": figures_file.get("plan_hash"),
        "fixture_root": relative_pack,
        "slide_count": len(model_slides),
        "slides": model_slides,
    }


def render_html(model: dict[str, Any]) -> str:
    slide_html = []
    for slide in model["slides"]:
        figures = "".join(
            '<div class="metric"><span class="metric-name">' + html.escape(figure["id"].replace("_", " ")) + '</span><strong>' + html.escape(_display(figure["value"])) + '</strong><span class="metric-unit">' + html.escape(figure["unit"]) + '</span></div>'
            for figure in slide["figures"]
        )
        chart = '<div class="chart">' + slide["chart"]["svg"] + '</div>' if slide["chart"] else ""
        uncertainty = '<aside class="uncertainty" role="note">' + html.escape(slide["uncertainty"]["callout"]) + '</aside>' if slide["uncertainty"] else ""
        citations = ", ".join(html.escape(citation) for citation in slide["citations"])
        slide_html.append(
            f'<section class="slide type-{html.escape(slide["type"])}" id="{html.escape(slide["id"])}" aria-label="Slide {slide["number"]} of {model["slide_count"]}" {"" if slide["number"] == 1 else "hidden"}>'
            '<div class="eyebrow">SYNTHETIC DATA | FICTIONAL EXAMPLE</div>'
            f'<div class="slide-number">{slide["number"]:02d}</div>'
            f'<h1>{html.escape(slide["title"])}</h1>'
            f'<p class="claim">{html.escape(slide["claim"])}</p>'
            f'{uncertainty}<div class="metrics">{figures}</div>{chart}'
            f'<footer>Source: {citations}<br/>Synthetic fixture evidence only. This deck does not establish real-world findings.</footer>'
            '</section>'
        )
    slides_markup = "\n".join(slide_html)
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Decksmith synthetic deck: """ + html.escape(model["topic"]) + """</title>
<style>
:root{--ink:#24343A;--teal:#2C6E73;--amber:#E5A94F;--rust:#A85D46;--paper:#F8F6F1;--white:#fff}
*{box-sizing:border-box}body{margin:0;background:#d8dfdc;color:var(--ink);font-family:Arial,Helvetica,sans-serif}
.slide{position:relative;width:min(100vw,1440px);height:min(56.25vw,810px);min-height:600px;margin:24px auto;padding:70px 86px 62px;background:var(--paper);overflow:auto;box-shadow:0 10px 36px #24343a22}
.slide[hidden]{display:none}.type-title{background:var(--ink);color:var(--white)}.type-title .claim,.type-title footer{color:#e1e9e5}.eyebrow{color:var(--teal);font-size:14px;font-weight:700;letter-spacing:2px}.type-title .eyebrow{color:var(--amber)}
h1{max-width:1050px;margin:64px 0 24px;font-size:46px;line-height:1.08;letter-spacing:-1px}.type-title h1{font-size:62px}.claim{max-width:1040px;font-size:25px;line-height:1.45;margin:0 0 28px}.slide-number{position:absolute;right:86px;top:65px;font-size:18px;color:#75827e}
.metrics{display:flex;gap:18px;flex-wrap:wrap;margin:28px 0}.metric{min-width:190px;padding:18px 22px;background:#fff;border-top:4px solid var(--teal);display:grid;gap:8px}.metric strong{font-size:32px}.metric-name,.metric-unit{font-size:14px;color:#64736f;text-transform:capitalize}
.chart{width:min(100%,920px);margin:15px auto}.chart svg{display:block;width:100%;height:auto;max-height:390px}.uncertainty{border-left:6px solid var(--rust);background:#f5e7df;padding:18px 22px;margin:22px 0;font-size:20px;line-height:1.4}
footer{position:absolute;bottom:26px;left:86px;right:86px;border-top:1px solid #b9c1bc;padding-top:12px;font-size:13px;color:#586762;line-height:1.55}.type-title footer{border-color:#667672}.nav{position:fixed;z-index:5;bottom:14px;left:50%;transform:translateX(-50%);background:var(--ink);color:#fff;border-radius:30px;padding:10px 18px;display:flex;gap:18px;align-items:center;font-size:14px}.nav button{background:transparent;color:#fff;border:0;font-size:20px;cursor:pointer}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:700px){.slide{width:100vw;height:100vh;min-height:0;margin:0;padding:54px 24px 100px}.slide-number{right:24px;top:48px}h1{font-size:36px;margin-top:58px}.type-title h1{font-size:43px}.claim{font-size:20px}footer{left:24px;right:24px;bottom:16px}.chart svg{max-height:300px}.metric{min-width:130px}}
</style>
</head>
<body>
<main id="deck" aria-live="polite">
""" + slides_markup + """
</main>
<nav class="nav" aria-label="Slide navigation"><button id="previous" aria-label="Previous slide">&#8592;</button><span id="counter">1 / """ + str(model["slide_count"]) + """</span><button id="next" aria-label="Next slide">&#8594;</button><span>Arrow keys</span></nav>
<script>
(() => { const slides = Array.from(document.querySelectorAll('.slide')); let index = 0;
const show = (next) => { index = Math.max(0, Math.min(slides.length - 1, next)); slides.forEach((slide, i) => { slide.hidden = i !== index; }); document.getElementById('counter').textContent = `${index + 1} / ${slides.length}`; };
document.getElementById('previous').addEventListener('click', () => show(index - 1)); document.getElementById('next').addEventListener('click', () => show(index + 1));
document.addEventListener('keydown', (event) => { if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') show(index + 1); if (event.key === 'ArrowLeft' || event.key === 'PageUp') show(index - 1); });
})();
</script>
</body>
</html>
"""


def render_markdown(model: dict[str, Any]) -> str:
    lines = [
        f"# Decksmith slide source: {model['topic']}",
        "",
        "> SYNTHETIC DATA. This is a fictional example, not real-world research.",
        "",
        "Regenerate the self-contained HTML with `decksmith render --source deck.md --out deck.html`.",
        "",
    ]
    for slide in model["slides"]:
        lines.extend([f"## Slide {slide['number']}: {slide['title']}", "", slide["claim"], ""])
        if slide["uncertainty"]:
            lines.extend([f"> {slide['uncertainty']['callout']}", ""])
        for figure in slide["figures"]:
            lines.append(f"- {figure['id']}: {_display(figure['value'])} {figure['unit']}")
        if slide["chart"]:
            lines.append(f"- Chart: {slide['chart']['title']} ({slide['chart']['type']})")
        if slide["figures"] or slide["chart"]:
            lines.append("")
        for citation in slide["citations"]:
            lines.append(f"- Source: {citation}")
        lines.append("")
    payload = base64.b64encode(canonical_json(model).encode("utf-8")).decode("ascii")
    lines.extend(["## Regeneration data", "", "```decksmith-model-base64", payload, "```", ""])
    return "\n".join(lines)


def model_from_markdown(source: Path) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    match = re.search(r"```decksmith-model-base64\s*\n([A-Za-z0-9+/=\s]+)\n```", text)
    if not match:
        raise ValueError("Markdown file does not contain a Decksmith regeneration payload")
    return json.loads(base64.b64decode("".join(match.group(1).split())).decode("utf-8"))


def assemble_deck(plan_path: Path, charts_dir: Path, figures_path: Path | None = None, out: Path | None = None) -> Path:
    plan_file = plan_path.expanduser().resolve()
    root = plan_file.parent
    figure_file = figures_path.expanduser().resolve() if figures_path else root / "figures.json"
    output = out.expanduser().resolve() if out else root / "deck"
    model = create_model(read_json(plan_file), read_json(figure_file), charts_dir.expanduser().resolve(), root, output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "deck.html").write_text(render_html(model), encoding="utf-8", newline="\n")
    (output / "deck.md").write_text(render_markdown(model), encoding="utf-8", newline="\n")
    write_json(output / "deck.json", model)
    return output
