from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from decksmith.assembler import assemble_deck, model_from_markdown, render_html
from decksmith.charts import generate_charts
from decksmith.compute import calculate_figure, compute_figures
from decksmith.fixtures import generate_fixtures
from decksmith.io import read_json, write_json
from decksmith.planner import create_outline
from decksmith.verify import verify_deck


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    return generate_fixtures("Grid-scale storage", tmp_path / "pack")


def make_complete_deck(pack_dir: Path) -> tuple[Path, Path, Path]:
    plan_path = create_outline(pack_dir)
    figures_path = compute_figures(pack_dir, plan_path)
    charts_path = generate_charts(pack_dir, figures_path)
    deck_path = assemble_deck(plan_path, charts_path)
    return plan_path, figures_path, deck_path


def test_fixture_pack_is_deterministic_and_has_labelled_gaps(tmp_path: Path) -> None:
    first = generate_fixtures("Grid-scale storage", tmp_path / "first")
    second = generate_fixtures("Grid-scale storage", tmp_path / "second")
    relative_files = [
        "manifest.json", "evidence_gaps.json", "research_notes.md",
        "datasets/quarterly.csv", "datasets/segment_revenue.csv",
    ]
    for name in relative_files:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    manifest = read_json(first / "manifest.json")
    assert manifest["synthetic"] is True
    assert manifest["generation_seed"] == 20260928
    notes = (first / "research_notes.md").read_text(encoding="utf-8")
    gaps = read_json(first / "evidence_gaps.json")["gaps"]
    assert {gap["gap_id"] for gap in gaps} == {"GAP-01", "GAP-02"}
    assert all(f"[GAP: {gap['gap_id']}]" in notes for gap in gaps)
    assert {gap["status"] for gap in gaps} == {"missing", "weak"}


def test_fixture_rejects_empty_topic(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Topic must not be empty"):
        generate_fixtures("  ", tmp_path / "empty")


def test_outline_contains_complete_argument_arc_and_gap_flags(pack: Path) -> None:
    plan_path = create_outline(pack)
    plan = read_json(plan_path)
    assert [slide["arc"] for slide in plan["slides"]][0] == "hook"
    assert {"evidence", "tension", "counterpoint", "resolution", "call_to_action"}.issubset(
        {slide["arc"] for slide in plan["slides"]}
    )
    planned_gaps = {
        slide["uncertainty"]["gap_id"]: slide["uncertainty"]
        for slide in plan["slides"] if slide.get("uncertainty")
    }
    assert set(planned_gaps) == {gap["gap_id"] for gap in plan["gaps"]}
    assert all(item["callout"].startswith("UNCERTAINTY:") for item in planned_gaps.values())
    assert all(slide["uncertainty_flag"] is bool(slide.get("uncertainty")) for slide in plan["slides"])
    assert len(plan["slides"]) == 12


def test_planner_rejects_non_synthetic_pack(pack: Path) -> None:
    manifest_path = pack / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["synthetic"] = False
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="Only explicitly synthetic"):
        create_outline(pack)


def test_named_computations_match_hand_checked_values(pack: Path) -> None:
    plan = create_outline(pack)
    figures_path = compute_figures(pack, plan)
    figures = read_json(figures_path)["figures"]
    assert figures["f00_observation_count"]["value"] == 6
    assert figures["f01_adoption_growth"]["value"] == 183.33
    assert figures["f02_adoption_delta"]["value"] == 22
    assert figures["f03_revenue_growth"]["value"] == 115
    assert figures["f04_top_share"]["value"] == 48.84
    assert figures["f05_top_segment"]["value"] == [{"group": "Growth", "value": 126.0}]
    assert figures["f06_latest_ratio"]["value"] == 1.46
    assert figures["f07_adoption_interval"]["value"] == {"low": 31.0, "high": 37.0}
    assert figures["f07_adoption_interval"]["name"] == "confidence_interval"
    assert figures["f08_cost_growth"]["value"] == 92.39
    assert figures["f04_top_share"]["formula"] == "(largest_group_value / sum(group_values)) * 100"
    assert figures["f04_top_share"]["source"][0]["line_start"] == 2
    assert figures["f04_top_share"]["source"][0]["line_end"] == 4
    assert all("formula" in figure and "inputs" in figure and "source" in figure for figure in figures.values())


def test_column_value_helper_reads_the_named_fixture_cell(pack: Path) -> None:
    result = calculate_figure(pack, {
        "id": "manual-bound",
        "helper": "column_value",
        "dataset": "datasets/quarterly.csv",
        "column": "confidence_high",
        "row": -1,
    })
    assert result["value"] == 37
    assert result["source"][0]["line_start"] == result["source"][0]["line_end"] == 7


def test_figures_are_byte_deterministic(pack: Path, tmp_path: Path) -> None:
    plan = create_outline(pack)
    first = compute_figures(pack, plan, tmp_path / "one.json")
    second = compute_figures(pack, plan, tmp_path / "two.json")
    assert first.read_bytes() == second.read_bytes()


def test_chart_svg_is_fixture_bound_labelled_and_deterministic(pack: Path, tmp_path: Path) -> None:
    plan = create_outline(pack)
    figures = compute_figures(pack, plan)
    first = generate_charts(pack, figures, tmp_path / "charts-one")
    second = generate_charts(pack, figures, tmp_path / "charts-two")
    manifest = read_json(first / "charts_manifest.json")
    assert len(manifest["charts"]) == 3
    for entry in manifest["charts"]:
        svg = (first / entry["file"]).read_text(encoding="utf-8")
        rerun = (second / entry["file"]).read_text(encoding="utf-8")
        assert svg == rerun
        assert "SYNTHETIC DATA" in svg
        assert f"Source: {entry['dataset']}" in svg
        assert entry["dataset"] in svg
        assert svg.lstrip().startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "12" in (first / "c01_adoption_line.svg").read_text(encoding="utf-8")
    assert "34" in (first / "c01_adoption_line.svg").read_text(encoding="utf-8")


def test_chart_values_come_from_fixture_table(pack: Path, tmp_path: Path) -> None:
    plan = create_outline(pack)
    figures_path = compute_figures(pack, plan)
    figures = read_json(figures_path)
    figures["untrusted_chart_values"] = [999999]
    altered_figures_path = tmp_path / "altered-figures.json"
    write_json(altered_figures_path, figures)
    chart_dir = generate_charts(pack, altered_figures_path, tmp_path / "charts")
    svg = (chart_dir / "c01_adoption_line.svg").read_text(encoding="utf-8")
    assert "999999" not in svg
    assert "34" in svg


def test_chart_generation_rejects_unlabelled_figures(pack: Path, tmp_path: Path) -> None:
    plan = create_outline(pack)
    figures_path = compute_figures(pack, plan)
    figures = read_json(figures_path)
    figures["synthetic"] = False
    fake_path = tmp_path / "not-synthetic.json"
    write_json(fake_path, figures)
    with pytest.raises(ValueError, match="labelled synthetic"):
        generate_charts(pack, fake_path)


def test_chart_generation_rejects_paths_outside_the_pack(pack: Path, tmp_path: Path) -> None:
    plan = create_outline(pack)
    figures = read_json(compute_figures(pack, plan))
    figures["charts"][0]["dataset"] = "../../outside.csv"
    figures_path = tmp_path / "outside.json"
    write_json(figures_path, figures)
    with pytest.raises(ValueError, match="escapes the pack"):
        generate_charts(pack, figures_path)


def test_build_enforces_slide_bounds(pack: Path, tmp_path: Path) -> None:
    plan_path, _, charts = make_complete_deck(pack)
    original = read_json(plan_path)
    for count in (11, 21):
        altered = dict(original)
        altered["slides"] = original["slides"][:count] if count == 11 else original["slides"] + [original["slides"][-1]] * 9
        altered_path = tmp_path / f"plan-{count}.json"
        write_json(altered_path, altered)
        with pytest.raises(ValueError, match=f"Slide count must be between 12 and 20; got {count}"):
            assemble_deck(altered_path, charts, pack / "figures.json", tmp_path / f"deck-{count}")


def test_html_is_self_contained_and_markdown_regenerates_exactly(pack: Path) -> None:
    _, _, deck = make_complete_deck(pack)
    original = (deck / "deck.html").read_bytes()
    markdown = deck / "deck.md"
    model = model_from_markdown(markdown)
    assert render_html(model).encode("utf-8") == original
    text = original.decode("utf-8")
    assert "<svg " in text
    assert "SYNTHETIC DATA" in text
    assert "ArrowRight" in text
    assert "Source: datasets/quarterly.csv" in text
    assert "<script src=" not in text
    assert "<link rel=" not in text
    assert "https://" not in text
    assert len(model["slides"]) == 12
    assert (deck / "deck.json").is_file()


def test_all_slide_claims_carry_sources_and_both_gaps_are_callouts(pack: Path) -> None:
    _, _, deck = make_complete_deck(pack)
    model = read_json(deck / "deck.json")
    for slide in model["slides"]:
        assert slide["claim"].strip()
        assert slide["evidence"]
        assert slide["citations"]
    gap_slides = [slide for slide in model["slides"] if slide["uncertainty"]]
    assert {slide["uncertainty"]["gap_id"] for slide in gap_slides} == {"GAP-01", "GAP-02"}
    assert all(slide["uncertainty"]["callout"].startswith("UNCERTAINTY:") for slide in gap_slides)
    assert verify_deck(deck)["ok"] is True


def test_unsourced_claim_fails_with_slide_number_and_claim(pack: Path) -> None:
    _, _, deck = make_complete_deck(pack)
    path = deck / "deck.json"
    model = read_json(path)
    model["slides"][4]["evidence"] = []
    model["slides"][4]["claim"] = "unsupported board claim"
    write_json(path, model)
    result = verify_deck(deck)
    assert result["ok"] is False
    assert any("Slide 5: unsourced claim: unsupported board claim" in item for item in result["errors"])


def test_edited_figure_value_fails_fixture_recomputation(pack: Path) -> None:
    _, _, deck = make_complete_deck(pack)
    path = deck / "deck.json"
    model = read_json(path)
    model["slides"][0]["figures"][0]["value"] = 9999
    write_json(path, model)
    result = verify_deck(deck)
    assert result["ok"] is False
    assert any("Slide 1: figure f01_adoption_growth does not match its fixture computation" in issue for issue in result["errors"])


def test_edited_chart_fails_fixture_regeneration(pack: Path) -> None:
    _, _, deck = make_complete_deck(pack)
    path = deck / "deck.json"
    model = read_json(path)
    model["slides"][2]["chart"]["svg"] = model["slides"][2]["chart"]["svg"].replace(">12</text>", ">999</text>", 1)
    write_json(path, model)
    result = verify_deck(deck)
    assert result["ok"] is False
    assert any("Slide 3: chart does not match its fixture table" in issue for issue in result["errors"])


def test_invalid_or_missing_fixture_source_fails(pack: Path) -> None:
    _, _, deck = make_complete_deck(pack)
    path = deck / "deck.json"
    model = read_json(path)
    model["slides"][0]["evidence"][0]["file"] = "datasets/not-present.csv"
    write_json(path, model)
    result = verify_deck(deck)
    assert result["ok"] is False
    assert any("Slide 1: missing fixture source datasets/not-present.csv" in item for item in result["errors"])


def test_gap_callout_cannot_be_silently_removed(pack: Path) -> None:
    _, _, deck = make_complete_deck(pack)
    path = deck / "deck.json"
    model = read_json(path)
    model["slides"][8]["uncertainty"] = None
    write_json(path, model)
    result = verify_deck(deck)
    assert any("Planted evidence gap GAP-01 is not shown" in issue for issue in result["errors"])


def test_theme_has_palette_grid_and_required_slide_templates() -> None:
    theme = (ROOT / "decksmith" / "theme.yaml").read_text(encoding="utf-8")
    assert "palette:" in theme
    assert "type_scale:" in theme
    assert "spacing_grid_px: 8" in theme
    for slide_type in ("title", "section", "evidence", "chart", "comparison", "closing"):
        assert f"  {slide_type}:" in theme


def test_cli_smoke_all_subcommands_and_audit(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([sys.executable, "-m", "decksmith", *args], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "synthetic" in (result.stdout + result.stderr).casefold()
        return result

    pack_dir = tmp_path / "cli-pack"
    run("fixtures", "--topic", "CLI smoke", "--out", str(pack_dir))
    run("outline", "--pack", str(pack_dir))
    run("compute", "--pack", str(pack_dir), "--plan", str(pack_dir / "plan.json"))
    run("charts", "--pack", str(pack_dir), "--figures", str(pack_dir / "figures.json"))
    run("build", "--plan", str(pack_dir / "plan.json"), "--charts", str(pack_dir / "charts"))
    run("verify", "--deck", str(pack_dir / "deck"))
    run("render", "--source", str(pack_dir / "deck" / "deck.md"), "--out", str(tmp_path / "rendered.html"))
    run("themes", "--out", str(tmp_path / "theme.yaml"))
    assert (tmp_path / "rendered.html").read_bytes() == (pack_dir / "deck" / "deck.html").read_bytes()
    assert (tmp_path / "theme.yaml").is_file()
    audit = [json.loads(line) for line in (tmp_path / "ds-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["command"] for entry in audit] == ["fixtures", "outline", "compute", "charts", "build", "verify", "render", "themes"]
    assert audit[2]["figures_computed"] == 9
    assert audit[3]["charts_generated"] == 3
    assert audit[5]["verification_result"] is True
    assert audit[1]["plan_hash"]
    assert audit[5]["figures_computed"] == 9
    assert audit[5]["charts_generated"] == 3


def test_end_to_end_rebuild_is_byte_for_byte_deterministic(tmp_path: Path) -> None:
    pack_dir = generate_fixtures("Reproducibility", tmp_path / "repro-pack")
    plan = create_outline(pack_dir)
    figures = compute_figures(pack_dir, plan)
    charts = generate_charts(pack_dir, figures)
    deck = assemble_deck(plan, charts)
    assert verify_deck(deck)["ok"] is True
    names = [
        "plan.json", "figures.json", "charts/c01_adoption_line.svg", "charts/c02_revenue_bar.svg",
        "charts/c03_segment_donut.svg", "charts/charts_manifest.json", "deck/deck.html", "deck/deck.md", "deck/deck.json",
    ]
    before = {name: (pack_dir / name).read_bytes() for name in names}
    generate_fixtures("Reproducibility", pack_dir)
    plan = create_outline(pack_dir)
    figures = compute_figures(pack_dir, plan)
    charts = generate_charts(pack_dir, figures)
    deck = assemble_deck(plan, charts)
    assert verify_deck(deck)["ok"] is True
    assert {name: (pack_dir / name).read_bytes() for name in names} == before
