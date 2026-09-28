"""Rule-based narrative planner with an explicit argument arc."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import read_json, source_ref, write_json


def _rows(file: str, start: int, end: int, label: str) -> list[dict[str, Any]]:
    return [source_ref(file, start, end, label)]


def create_outline(pack: Path, out: Path | None = None) -> Path:
    root = pack.expanduser().resolve()
    manifest = read_json(root / "manifest.json")
    if manifest.get("synthetic") is not True:
        raise ValueError("Only explicitly synthetic fixture packs can be planned")
    topic = manifest["topic"]
    gaps = read_json(root / manifest["gaps_file"])["gaps"]
    qsource = "datasets/quarterly.csv"
    ssource = "datasets/segment_revenue.csv"
    note = manifest["notes_file"]
    gap_by_id = {gap["gap_id"]: gap for gap in gaps}

    nodes = [
        {"id": "s01", "type": "title", "arc": "hook", "title": f"A synthetic case for {topic}", "claim": "Across the generated fixture period, the adoption index changes by {figure:f01_adoption_growth}%. The dataset is fictional.", "evidence": _rows(qsource, 2, 7, "quarterly observations"), "figures": ["f01_adoption_growth"], "chart": None},
        {"id": "s02", "type": "section", "arc": "evidence", "title": "Start with the fixture", "claim": "The pack contains {figure:f00_observation_count} quarterly observations generated for this example.", "evidence": _rows(qsource, 2, 7, "quarterly data observations"), "figures": ["f00_observation_count"], "chart": None},
        {"id": "s03", "type": "chart", "arc": "evidence", "title": "Adoption rises through the constructed period", "claim": "The line chart plots every adoption observation in the synthetic quarterly table.", "evidence": _rows(qsource, 2, 7, "adoption_index observations"), "figures": [], "chart": "c01_adoption_line"},
        {"id": "s04", "type": "evidence", "arc": "evidence", "title": "The endpoint is above the starting point", "claim": "Adoption index changed by {figure:f02_adoption_delta} points from first to last quarter.", "evidence": _rows(qsource, 2, 7, "first and last adoption observations"), "figures": ["f02_adoption_delta"], "chart": None},
        {"id": "s05", "type": "chart", "arc": "evidence", "title": "Revenue also expands in the fixture", "claim": "The bars show quarterly revenue values from the constructed dataset.", "evidence": _rows(qsource, 2, 7, "quarterly revenue observations"), "figures": ["f03_revenue_growth"], "chart": "c02_revenue_bar"},
        {"id": "s06", "type": "chart", "arc": "evidence", "title": "The segment mix is concentrated", "claim": "The segment chart is computed from the synthetic segment revenue table. Largest segment: {figure:f05_top_segment}. Largest segment share: {figure:f04_top_share}%.", "evidence": _rows(ssource, 2, 4, "segment revenue observations"), "figures": ["f04_top_share", "f05_top_segment"], "chart": "c03_segment_donut"},
        {"id": "s07", "type": "evidence", "arc": "evidence", "title": "Revenue exceeds cost in the final quarter", "claim": "Latest-quarter revenue-to-cost ratio: {figure:f06_latest_ratio}x. Supplied fixture interval for adoption: {figure:f07_adoption_interval}.", "evidence": _rows(qsource, 7, 7, "latest quarter revenue, cost, and interval"), "figures": ["f06_latest_ratio", "f07_adoption_interval"], "chart": None},
        {"id": "s08", "type": "comparison", "arc": "tension", "title": "Growth comes with rising costs", "claim": "Revenue grew {figure:f03_revenue_growth}% over the period while costs changed by {figure:f08_cost_growth}%.", "evidence": _rows(qsource, 2, 7, "first and last revenue and cost observations"), "figures": ["f03_revenue_growth", "f08_cost_growth"], "chart": None},
        {"id": "s09", "type": "evidence", "arc": "counterpoint", "title": "Competitive response remains unknown", "claim": "{gap:GAP-01}", "evidence": [gap_by_id["GAP-01"]["source"]], "figures": [], "chart": None, "uncertainty": {"gap_id": "GAP-01", "status": "missing", "callout": "UNCERTAINTY: {gap:GAP-01}"}},
        {"id": "s10", "type": "evidence", "arc": "counterpoint", "title": "Customer willingness to pay is weak evidence", "claim": "{gap:GAP-02}", "evidence": [gap_by_id["GAP-02"]["source"]], "figures": [], "chart": None, "uncertainty": {"gap_id": "GAP-02", "status": "weak", "callout": "UNCERTAINTY: {gap:GAP-02}"}},
        {"id": "s11", "type": "section", "arc": "resolution", "title": "A bounded reading of the synthetic results", "claim": "The constructed tables support an upward adoption pattern and leave real-world conclusions untested.", "evidence": _rows(qsource, 2, 7, "adoption observations"), "figures": ["f01_adoption_growth"], "chart": None},
        {"id": "s12", "type": "closing", "arc": "call_to_action", "title": "Close the evidence gaps before acting", "claim": "{note:recommended_next_step}", "evidence": [source_ref(note, 9, 9, "synthetic recommended next step")], "figures": [], "chart": None},
    ]
    for node in nodes:
        node["uncertainty_flag"] = bool(node.get("uncertainty"))
    plan = {
        "format_version": 1,
        "topic": topic,
        "synthetic": True,
        "argument_arc": ["hook", "evidence", "tension", "counterpoint", "resolution", "call_to_action"],
        "minimum_slides": 12,
        "maximum_slides": 20,
        "source_pack": ".",
        "gaps": gaps,
        "computations": [
            {"id": "f00_observation_count", "helper": "count_rows", "dataset": "datasets/quarterly.csv", "column": "quarter"},
            {"id": "f01_adoption_growth", "helper": "growth_rate", "dataset": "datasets/quarterly.csv", "column": "adoption_index", "from_row": 0, "to_row": -1},
            {"id": "f02_adoption_delta", "helper": "absolute_delta", "dataset": "datasets/quarterly.csv", "column": "adoption_index", "from_row": 0, "to_row": -1},
            {"id": "f03_revenue_growth", "helper": "growth_rate", "dataset": "datasets/quarterly.csv", "column": "revenue_k", "from_row": 0, "to_row": -1},
            {"id": "f04_top_share", "helper": "top_share", "dataset": "datasets/segment_revenue.csv", "column": "revenue_k", "group_column": "segment"},
            {"id": "f05_top_segment", "helper": "top_n", "dataset": "datasets/segment_revenue.csv", "column": "revenue_k", "group_column": "segment", "n": 1},
            {"id": "f06_latest_ratio", "helper": "ratio", "dataset": "datasets/quarterly.csv", "numerator": "revenue_k", "denominator": "cost_k", "row": -1},
            {"id": "f07_adoption_interval", "helper": "confidence_interval", "dataset": "datasets/quarterly.csv", "lower_column": "confidence_low", "upper_column": "confidence_high", "row": -1},
            {"id": "f08_cost_growth", "helper": "growth_rate", "dataset": "datasets/quarterly.csv", "column": "cost_k", "from_row": 0, "to_row": -1},
        ],
        "charts": [
            {"id": "c01_adoption_line", "type": "line", "dataset": "datasets/quarterly.csv", "label_column": "quarter", "value_column": "adoption_index", "title": "Adoption index by quarter"},
            {"id": "c02_revenue_bar", "type": "bar", "dataset": "datasets/quarterly.csv", "label_column": "quarter", "value_column": "revenue_k", "title": "Revenue by quarter (synthetic $k)"},
            {"id": "c03_segment_donut", "type": "donut", "dataset": "datasets/segment_revenue.csv", "label_column": "segment", "value_column": "revenue_k", "title": "Revenue share by segment (synthetic $k)"},
        ],
        "slides": nodes,
    }
    path = out.expanduser().resolve() if out else root / "plan.json"
    write_json(path, plan)
    return path
