"""Deterministic fictional research fixture generator."""

from __future__ import annotations

from pathlib import Path

from .io import line_number, slugify, source_ref, write_json


GENERATION_SEED = 20260928


def generate_fixtures(topic: str, out: Path) -> Path:
    if not topic.strip():
        raise ValueError("Topic must not be empty")
    root = out.expanduser().resolve()
    data_dir = root / "datasets"
    data_dir.mkdir(parents=True, exist_ok=True)

    quarterly_csv = (
        "quarter,adoption_index,revenue_k,cost_k,confidence_low,confidence_high\n"
        "Q1,12,120,92,10,14\n"
        "Q2,15,138,101,13,17\n"
        "Q3,19,161,119,17,21\n"
        "Q4,23,188,136,21,25\n"
        "Q5,28,220,154,26,30\n"
        "Q6,34,258,177,31,37\n"
    )
    segments_csv = (
        "segment,revenue_k,customers\n"
        "Pilot,84,42\n"
        "Growth,126,63\n"
        "Scale,48,16\n"
    )
    (data_dir / "quarterly.csv").write_text(quarterly_csv, encoding="utf-8", newline="\n")
    (data_dir / "segment_revenue.csv").write_text(segments_csv, encoding="utf-8", newline="\n")

    notes = (
        "# Synthetic research notes\n\n"
        f"Topic label: {topic.strip()}\n"
        "All observations in this pack are fictional and generated for software testing.\n"
        "The quarterly table is a constructed example, not a measurement of any real market.\n"
        "The segment table is a constructed example with rounded revenue totals.\n"
        "[GAP: GAP-01] Competitive response evidence is missing from this synthetic pack.\n"
        "[GAP: GAP-02] Willingness-to-pay evidence is weak and self-reported in this synthetic pack.\n"
        "Synthetic recommended next step: collect audited competitive and customer evidence before making a real decision.\n"
    )
    (root / "research_notes.md").write_text(notes, encoding="utf-8", newline="\n")
    note_file = "research_notes.md"
    gaps = [
        {
            "gap_id": "GAP-01",
            "status": "missing",
            "statement": "Competitive response evidence is missing from this synthetic pack.",
            "source": source_ref(note_file, line_number(notes, "[GAP: GAP-01]"), line_number(notes, "[GAP: GAP-01]"), "GAP-01 marker"),
        },
        {
            "gap_id": "GAP-02",
            "status": "weak",
            "statement": "Willingness-to-pay evidence is weak and self-reported in this synthetic pack.",
            "source": source_ref(note_file, line_number(notes, "[GAP: GAP-02]"), line_number(notes, "[GAP: GAP-02]"), "GAP-02 marker"),
        },
    ]
    write_json(root / "evidence_gaps.json", {"synthetic": True, "gaps": gaps})
    write_json(
        root / "manifest.json",
        {
            "format_version": 1,
            "topic": topic.strip(),
            "slug": slugify(topic),
            "synthetic": True,
            "label": "SYNTHETIC DATA",
            "generation_seed": GENERATION_SEED,
            "seed_note": "Fixed metadata seed; fixture values are literal and use no random sampling.",
            "datasets": [
                {"file": "datasets/quarterly.csv", "table": "quarterly", "rows": 6},
                {"file": "datasets/segment_revenue.csv", "table": "segment_revenue", "rows": 3},
            ],
            "notes_file": "research_notes.md",
            "gaps_file": "evidence_gaps.json",
        },
    )
    return root

