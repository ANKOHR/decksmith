"""Command line entry point for Decksmith."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .assembler import assemble_deck, model_from_markdown, render_html
from .charts import generate_charts
from .compute import compute_figures
from .fixtures import generate_fixtures
from .io import read_json, sha256_file
from .planner import create_outline
from .verify import verify_deck


DISCLAIMER = "Synthetic fixture data only. Not real-world research, market figures, or company data."


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decksmith", description="Compile synthetic fixture evidence into a cited, reproducible presentation.")
    parser.add_argument("--version", action="version", version=f"decksmith {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    fixtures = commands.add_parser("fixtures", help="generate a deterministic synthetic topic pack")
    fixtures.add_argument("--topic", required=True)
    fixtures.add_argument("--out", required=True, type=Path)
    outline = commands.add_parser("outline", help="plan a fixed argument arc from a fixture pack")
    outline.add_argument("--pack", required=True, type=Path)
    outline.add_argument("--out", type=Path)
    compute = commands.add_parser("compute", help="compute named figures from fixture tables")
    compute.add_argument("--pack", required=True, type=Path)
    compute.add_argument("--plan", required=True, type=Path)
    compute.add_argument("--out", type=Path)
    charts = commands.add_parser("charts", help="generate fixture-bound labelled SVG charts")
    charts.add_argument("--pack", required=True, type=Path)
    charts.add_argument("--figures", required=True, type=Path)
    charts.add_argument("--out", type=Path)
    build = commands.add_parser("build", help="assemble a self-contained HTML deck and Markdown source")
    build.add_argument("--plan", required=True, type=Path)
    build.add_argument("--charts", required=True, type=Path)
    build.add_argument("--figures", type=Path)
    build.add_argument("--out", type=Path)
    verify = commands.add_parser("verify", help="cross-check slide claims against fixture source files")
    verify.add_argument("--deck", required=True, type=Path)
    render = commands.add_parser("render", help="regenerate identical HTML from a Markdown slide source")
    render.add_argument("--source", required=True, type=Path)
    render.add_argument("--out", required=True, type=Path)
    themes = commands.add_parser("themes", help="show the built-in Field Notes design theme")
    themes.add_argument("--out", type=Path)
    return parser


def _audit(command: str, args: argparse.Namespace, result: dict[str, Any]) -> None:
    audit_path = Path.cwd() / "ds-audit.jsonl"
    pack = getattr(args, "pack", None)
    if pack is None and command == "fixtures":
        pack = getattr(args, "out", None)
    if pack is None and getattr(args, "plan", None):
        pack = args.plan.expanduser().resolve().parent
    if pack is None and command == "verify":
        deck_model = read_json(args.deck.expanduser().resolve() / "deck.json")
        pack = (args.deck.expanduser().resolve() / deck_model["fixture_root"]).resolve()
    if pack is None and command == "render":
        deck_model = model_from_markdown(args.source.expanduser().resolve())
        pack = (args.source.expanduser().resolve().parent / deck_model["fixture_root"]).resolve()
    plan_path = getattr(args, "plan", None)
    if plan_path is None and command == "outline":
        plan_path = result.get("path")
    plan_hash = sha256_file(plan_path) if plan_path and plan_path.is_file() else None
    figures_path = getattr(args, "figures", None)
    if figures_path is None and getattr(args, "plan", None):
        candidate = args.plan.expanduser().resolve().parent / "figures.json"
        figures_path = candidate if candidate.is_file() else None
    if figures_path is None and command == "verify":
        candidate = pack / "figures.json" if pack else None
        figures_path = candidate if candidate and candidate.is_file() else None
    figure_count = int(result.get("figures", 0))
    if figures_path and figures_path.is_file():
        try:
            figures_data = read_json(figures_path)
            figure_count = len(figures_data.get("figures", {}))
            if plan_hash is None:
                plan_hash = figures_data.get("plan_hash")
        except (ValueError, OSError):
            figure_count = 0
    if plan_hash is None and command == "verify":
        plan_hash = deck_model.get("plan_hash")
    if plan_hash is None and command == "render":
        plan_hash = deck_model.get("plan_hash")
    charts_count = int(result.get("charts", 0))
    chart_dir = getattr(args, "charts", None)
    if chart_dir is None and command == "verify" and pack:
        chart_dir = pack / "charts"
    if chart_dir and (chart_dir / "charts_manifest.json").is_file():
        try:
            charts_count = len(read_json(chart_dir / "charts_manifest.json").get("charts", []))
        except (ValueError, OSError):
            charts_count = 0
    entry = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "command": command,
        "pack": str(pack.expanduser().resolve()) if isinstance(pack, Path) else None,
        "plan_hash": plan_hash,
        "figures_computed": figure_count,
        "charts_generated": charts_count,
        "verification_result": result.get("verification_result"),
        "status": result.get("status", "ok"),
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "fixtures":
        path = generate_fixtures(args.topic, args.out)
        print(f"Synthetic topic pack created: {path}")
        return {"path": path}
    if args.command == "outline":
        path = create_outline(args.pack, args.out)
        print(f"Synthetic argument outline created: {path}")
        return {"path": path}
    if args.command == "compute":
        path = compute_figures(args.pack, args.plan, args.out)
        count = len(read_json(path)["figures"])
        print(f"Computed {count} named figures from synthetic fixture tables: {path}")
        return {"path": path, "figures": count}
    if args.command == "charts":
        path = generate_charts(args.pack, args.figures, args.out)
        count = len(read_json(path / "charts_manifest.json")["charts"])
        print(f"Generated {count} synthetic-data SVG charts from fixture tables: {path}")
        return {"path": path, "charts": count}
    if args.command == "build":
        path = assemble_deck(args.plan, args.charts, args.figures, args.out)
        print(f"Built a {read_json(path / 'deck.json')['slide_count']}-slide synthetic deck: {path}")
        print("Outputs: deck.html (offline), deck.md (regeneration source), deck.json (evidence map)")
        return {"path": path}
    if args.command == "verify":
        result = verify_deck(args.deck)
        write_result = args.deck.expanduser().resolve() / "verification.json"
        write_result.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        if result["ok"]:
            print(f"Verified {result['slide_count']} slides against synthetic fixture sources.")
        else:
            for issue in result["errors"]:
                print(f"ERROR: {issue}", file=sys.stderr)
        return {"path": args.deck, "verification_result": result["ok"], "status": "ok" if result["ok"] else "failed", "result": result}
    if args.command == "render":
        model = model_from_markdown(args.source.expanduser().resolve())
        target = args.out.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_html(model), encoding="utf-8", newline="\n")
        print(f"Regenerated self-contained synthetic deck HTML: {target}")
        return {"path": target}
    if args.command == "themes":
        theme_path = Path(__file__).resolve().parent / "theme.yaml"
        text = theme_path.read_text(encoding="utf-8")
        if args.out:
            theme_out = args.out.expanduser().resolve()
            theme_out.parent.mkdir(parents=True, exist_ok=True)
            theme_out.write_text(text, encoding="utf-8", newline="\n")
            print(f"Wrote Field Notes theme: {theme_out}")
        else:
            print(text, end="")
        return {"path": args.out}
    raise ValueError(f"Unknown command {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result: dict[str, Any]
    try:
        result = _run(args)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"decksmith: {error}", file=sys.stderr)
        result = {"status": "failed", "error": str(error)}
        try:
            _audit(args.command, args, result)
        except OSError:
            pass
        return 2
    try:
        _audit(args.command, args, result)
    except OSError as error:
        print(f"decksmith: could not append audit record: {error}", file=sys.stderr)
        return 2
    print(DISCLAIMER)
    if args.command == "verify" and not result["verification_result"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
