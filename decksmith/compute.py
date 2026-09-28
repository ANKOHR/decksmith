"""Named deterministic computations over fixture tables."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .io import csv_records, read_json, source_ref, write_json


def _row_refs(dataset: str, indices: list[int]) -> list[dict[str, Any]]:
    if not indices:
        return []
    return [source_ref(dataset, min(indices) + 2, max(indices) + 2, f"data rows {min(indices) + 1} to {max(indices) + 1}")]


def calculate_figure(pack: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Recompute one named figure from its specification and fixture rows."""
    root = pack.expanduser().resolve()
    dataset = spec["dataset"]
    relative = Path(dataset)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Fixture dataset path escapes the pack: {dataset}")
    table_path = (root / relative).resolve()
    if root not in table_path.parents:
        raise ValueError(f"Fixture dataset path escapes the pack: {dataset}")
    records = csv_records(table_path)
    helper = spec["helper"]
    if helper == "count_rows":
        value = len(records)
        inputs = {"dataset": dataset, "row_count": len(records)}
        formula = "count(data rows)"
        indices = list(range(len(records)))
    elif helper in {"growth_rate", "absolute_delta"}:
        start_index, end_index = spec["from_row"], spec["to_row"]
        start_index = start_index if start_index >= 0 else len(records) + start_index
        end_index = end_index if end_index >= 0 else len(records) + end_index
        start = float(records[start_index][spec["column"]])
        end = float(records[end_index][spec["column"]])
        if helper == "growth_rate":
            if start == 0:
                raise ValueError(f"Cannot compute growth from zero for {spec['id']}")
            value = round((end / start - 1) * 100, 2)
            formula = "((end_value / start_value) - 1) * 100"
        else:
            value = round(end - start, 2)
            formula = "end_value - start_value"
        inputs = {"column": spec["column"], "start_value": start, "end_value": end, "start_row": start_index + 1, "end_row": end_index + 1}
        indices = [start_index, end_index]
    elif helper in {"top_share", "top_n"}:
        column, group_column = spec["column"], spec["group_column"]
        total = sum(float(record[column]) for record in records)
        ranked = sorted(records, key=lambda record: (-float(record[column]), record[group_column]))
        if helper == "top_share":
            value = round(float(ranked[0][column]) / total * 100, 2)
            formula = "(largest_group_value / sum(group_values)) * 100"
            inputs = {"group": ranked[0][group_column], "group_value": float(ranked[0][column]), "total": total}
        else:
            n = int(spec["n"])
            value = [{"group": row[group_column], "value": float(row[column])} for row in ranked[:n]]
            formula = "sort by value descending, then group name ascending; take N"
            inputs = {"n": n, "column": column, "group_column": group_column}
        indices = list(range(len(records)))
    elif helper == "ratio":
        index = spec["row"] if spec["row"] >= 0 else len(records) + spec["row"]
        numerator = float(records[index][spec["numerator"]])
        denominator = float(records[index][spec["denominator"]])
        if denominator == 0:
            raise ValueError(f"Cannot divide by zero for {spec['id']}")
        value = round(numerator / denominator, 2)
        formula = "numerator / denominator"
        inputs = {"numerator": numerator, "denominator": denominator, "row": index + 1}
        indices = [index]
    elif helper == "confidence_interval":
        index = spec["row"] if spec["row"] >= 0 else len(records) + spec["row"]
        low = float(records[index][spec["lower_column"]])
        high = float(records[index][spec["upper_column"]])
        if low > high:
            raise ValueError(f"Invalid confidence interval bounds for {spec['id']}")
        value = {"low": low, "high": high}
        formula = "report the supplied lower and upper fixture bounds; do not infer new bounds"
        inputs = {"lower_column": spec["lower_column"], "upper_column": spec["upper_column"], "row": index + 1}
        indices = [index]
    elif helper == "column_value":
        index = spec["row"] if spec["row"] >= 0 else len(records) + spec["row"]
        value = float(records[index][spec["column"]])
        formula = "value from named fixture column and row"
        inputs = {"column": spec["column"], "row": index + 1}
        indices = [index]
    else:
        raise ValueError(f"Unknown computation helper: {helper}")
    unit = (
        "percent" if helper in {"growth_rate", "top_share"}
        else "ratio" if helper == "ratio"
        else "index points" if helper == "absolute_delta"
        else "count" if helper == "count_rows"
        else "index interval" if helper == "confidence_interval"
        else "fixture value"
    )
    return {
        "name": helper,
        "value": value,
        "unit": unit,
        "inputs": inputs,
        "formula": formula,
        "source": _row_refs(dataset, indices),
        "spec": spec,
    }


def compute_figures(pack: Path, plan_path: Path, out: Path | None = None) -> Path:
    root = pack.expanduser().resolve()
    plan = read_json(plan_path)
    if plan.get("synthetic") is not True:
        raise ValueError("Plan must be labelled synthetic")
    results = {spec["id"]: calculate_figure(root, spec) for spec in plan["computations"]}
    result = {
        "format_version": 1,
        "synthetic": True,
        "topic": plan["topic"],
        "plan_hash": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "figures": results,
        "charts": plan["charts"],
        "minimum_slides": plan["minimum_slides"],
        "maximum_slides": plan["maximum_slides"],
    }
    path = out.expanduser().resolve() if out else root / "figures.json"
    write_json(path, result)
    return path

