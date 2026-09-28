"""Evidence cross-checking for assembled slide decks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .assembler import model_from_markdown, render_html
from .charts import render_chart
from .compute import calculate_figure
from .io import canonical_json, csv_records, read_json


def _validate_source(root: Path, ref: dict[str, Any]) -> str | None:
    relative = Path(ref.get("file", ""))
    if not ref.get("file") or relative.is_absolute() or ".." in relative.parts:
        return "invalid fixture source path"
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        return "fixture source escapes the pack directory"
    if not path.is_file():
        return f"missing fixture source {ref['file']}"
    if "line_start" in ref:
        lines = path.read_text(encoding="utf-8").splitlines()
        start, end = int(ref["line_start"]), int(ref["line_end"])
        if start < 1 or end < start or end > len(lines):
            return f"invalid source lines {start}-{end} in {ref['file']}"
        if ref["file"].endswith(".csv") and start < 2:
            return f"CSV evidence must point to a data row in {ref['file']}"
    return None


def verify_deck(deck_dir: Path) -> dict[str, Any]:
    folder = deck_dir.expanduser().resolve()
    deck_file = folder / "deck.json"
    model = read_json(deck_file)
    root = (folder / model["fixture_root"]).resolve()
    errors: list[str] = []
    if model.get("synthetic") is not True:
        errors.append("Deck is not labelled synthetic")
    if not 12 <= len(model.get("slides", [])) <= 20:
        errors.append(f"Deck slide count must be between 12 and 20; got {len(model.get('slides', []))}")
    for slide in model.get("slides", []):
        claim = str(slide.get("claim", "")).strip()
        number = slide.get("number", "?")
        if not claim:
            errors.append(f"Slide {number}: empty claim")
        refs = slide.get("evidence", [])
        if not refs:
            errors.append(f"Slide {number}: unsourced claim: {claim}")
        for ref in refs:
            issue = _validate_source(root, ref)
            if issue:
                errors.append(f"Slide {number}: {issue} for claim: {claim}")
        for figure in slide.get("figures", []):
            try:
                expected = calculate_figure(root, figure["spec"])
                for field in ("name", "value", "unit", "inputs", "formula", "source"):
                    if figure.get(field) != expected.get(field):
                        errors.append(f"Slide {number}: figure {figure.get('id')} does not match its fixture computation for claim: {claim}")
                        break
            except (KeyError, TypeError, ValueError, OSError) as issue:
                errors.append(f"Slide {number}: cannot recompute figure {figure.get('id')}: {issue} for claim: {claim}")
        uncertainty = slide.get("uncertainty")
        if uncertainty:
            callout = str(uncertainty.get("callout", ""))
            if not callout.startswith("UNCERTAINTY:"):
                errors.append(f"Slide {number}: evidence gap {uncertainty.get('gap_id')} lacks an explicit uncertainty callout")
            if not any(uncertainty.get("gap_id", "") in ref.get("label", "") for ref in refs):
                errors.append(f"Slide {number}: uncertainty gap {uncertainty.get('gap_id')} has no matching source marker")
            else:
                marker = f"[GAP: {uncertainty.get('gap_id')}]"
                matching = [ref for ref in refs if uncertainty.get("gap_id", "") in ref.get("label", "")]
                marker_found = False
                for ref in matching:
                    if _validate_source(root, ref) is not None or "line_start" not in ref:
                        continue
                    lines = (root / ref["file"]).read_text(encoding="utf-8").splitlines()
                    start, end = int(ref["line_start"]), int(ref["line_end"])
                    marker_found = marker_found or any(marker in line for line in lines[start - 1:end])
                if not marker_found:
                    errors.append(f"Slide {number}: uncertainty gap {uncertainty.get('gap_id')} does not point to its planted marker")
        chart = slide.get("chart")
        if chart:
            svg = chart.get("svg", "")
            if "SYNTHETIC DATA" not in svg or "Source:" not in svg or chart.get("dataset", "") not in svg:
                errors.append(f"Slide {number}: chart is missing its synthetic label or fixture source")
            chart_ref_issue = _validate_source(root, {"file": chart.get("dataset", "")})
            if chart_ref_issue:
                errors.append(f"Slide {number}: chart fixture source issue: {chart_ref_issue}")
            else:
                try:
                    expected_svg = render_chart(chart, csv_records(root / chart["dataset"]))
                    if svg != expected_svg:
                        errors.append(f"Slide {number}: chart does not match its fixture table")
                except (KeyError, TypeError, ValueError, OSError) as issue:
                    errors.append(f"Slide {number}: chart cannot be regenerated from its fixture table: {issue}")

    gaps_path = root / "evidence_gaps.json"
    if gaps_path.is_file():
        gaps = read_json(gaps_path).get("gaps", [])
        present = {slide.get("uncertainty", {}).get("gap_id") for slide in model.get("slides", []) if slide.get("uncertainty")}
        for gap in gaps:
            if gap["gap_id"] not in present:
                errors.append(f"Planted evidence gap {gap['gap_id']} is not shown as slide uncertainty")

    html_path = folder / "deck.html"
    if html_path.is_file() and html_path.read_text(encoding="utf-8") != render_html(model):
        errors.append("deck.html does not match the structured evidence map")
    markdown_path = folder / "deck.md"
    if markdown_path.is_file():
        try:
            markdown_model = model_from_markdown(markdown_path)
            if canonical_json(markdown_model) != canonical_json(model):
                errors.append("deck.md regeneration payload does not match the structured evidence map")
        except (ValueError, OSError, TypeError) as issue:
            errors.append(f"deck.md regeneration payload is invalid: {issue}")

    result = {"ok": not errors, "errors": errors, "slide_count": len(model.get("slides", [])), "deck": str(folder)}
    return result
