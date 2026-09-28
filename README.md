# Decksmith

Decksmith is a deterministic evidence-to-deck compiler. It turns structured, fictional research fixtures into a cited 12 to 20 slide presentation. It computes displayed figures from fixture tables, draws charts from those same tables, and checks that each slide claim points back to fixture evidence.

**All included data and research notes are synthetic. They are not real market figures, real research, or real company data.**

## Quickstart

Python 3.10 or newer is required. The implementation uses the Python standard library. Pytest is needed only to run the development suite.

```powershell
python -m pip install -e .
python -m decksmith fixtures --topic "Grid-scale storage" --out demo-pack
python -m decksmith outline --pack demo-pack
python -m decksmith compute --pack demo-pack --plan demo-pack/plan.json
python -m decksmith charts --pack demo-pack --figures demo-pack/figures.json
python -m decksmith build --plan demo-pack/plan.json --charts demo-pack/charts
python -m decksmith verify --deck demo-pack/deck
python -m decksmith render --source demo-pack/deck/deck.md --out demo-pack/deck/rebuilt.html
```

The build writes `deck.html`, a self-contained offline presentation with keyboard navigation, `deck.md`, a human-readable slide source with a regeneration payload, and `deck.json`, the evidence map used by verification. The regenerated HTML is byte-identical to the original HTML when the Markdown source is unchanged. Every command states that its data is synthetic. CLI runs append a JSON Lines record to `ds-audit.jsonl` in the current working directory.

To run the suite, use `python -m pytest` from the repository root.

## Architecture

```text
synthetic fixture generator
        |
        +--> CSV tables, research notes, planted evidence gaps
                         |
                 narrative planner
                         |
             outline with claims and citations
                    /             \
      named computations       chart specifications
              |                        |
         figures.json            fixture CSV tables
              \                        /
               SVG chart generator
                         |
              theme and slide assembler
                  /             \
              deck.html        deck.md
                  |
          evidence cross-checker
                  |
          ds-audit.jsonl records each CLI run
```

The fixtures are literal tables with a documented fixed metadata seed (`20260928`). Fixture generation does not use random sampling. Plans, figure files, SVGs, deck JSON, HTML, and Markdown use stable serialization and contain no run timestamps. Audit timestamps are intentionally the exception.

## HONESTY BOUNDARY

All slide content is generated from synthetic research fixtures: fictional, generated datasets and research notes labelled as synthetic. Charts are fixture-data visualisations, not real-world data. Every chart visibly says `SYNTHETIC DATA` and names its fixture source. The deck, each CLI command, and this README state that the content is synthetic. Decksmith never presents fixture figures as real market figures, real research, or real company data. The evidence cross-checker traces claims to fixture sources only; it does not verify real-world truth. Missing and weak evidence is shown as an explicit uncertainty callout on the slide. If a viewer could mistake this example deck for genuine research findings, the build has failed its honesty boundary.

## Computation catalogue

Each computed figure records its helper name, input values or rows, formula, unit, and fixture source line range in `figures.json`.

| Helper | What it computes |
| --- | --- |
| `count_rows` | Number of data observations in a fixture table. |
| `growth_rate` | Percentage change between named start and end rows: `((end / start) - 1) * 100`. A zero start value is rejected. |
| `absolute_delta` | End value minus start value for a named column. |
| `top_share` | Largest group's share of the table total as a percentage. All groups are included in the source pointer. |
| `top_n` | Stable ranking by value descending, then group name ascending, returning the requested number of groups. |
| `ratio` | Named numerator divided by denominator for a selected row. A zero denominator is rejected. |
| `confidence_interval` | The supplied lower and upper bounds from one fixture row. Decksmith reports those columns and does not infer a statistical interval. |
| `column_value` | A value from a named fixture column and row for future fixture specifications. |

The fixture includes paired `confidence_low` and `confidence_high` columns. Decksmith reports these supplied bounds. It does not infer a statistical confidence interval from unprovided samples.

## Charts and slide types

The SVG generators support line, bar, and donut charts. Each chart reads its labels and values directly from the named CSV table, includes the synthetic-data label, and includes a source file and row range. Chart colors and the slide theme are fixed for reproducible output.

The Field Notes theme is stored in `decksmith/theme.yaml` and can be printed with `decksmith themes`. It defines the palette, type scale, spacing grid, and these slide templates:

- **Title:** opening hook, large title, claim, and evidence footer.
- **Section:** transition heading with a supported claim or computed figure.
- **Evidence:** claim, computed figures, and source footer.
- **Chart:** claim, fixture-bound inline SVG, and source footer.
- **Comparison:** paired quantitative evidence that presents tension or a counterpoint.
- **Closing:** resolution or call to action with its evidence source.

The default outline has twelve slides and carries a hook, evidence chain, tension, counterpoint, resolution, and call to action. Builds outside the enforced 12 to 20 slide range fail.

## Evidence and audit

`decksmith verify --deck <directory>` checks that every slide has a claim and source references, referenced files and line ranges exist inside the fixture pack, each planted gap appears as an uncertainty callout, and each embedded chart has its synthetic label and source line. A failed claim reports its slide number and claim text. Passing verification means the deck points to its synthetic inputs, not that a claim is true outside the fixture.

Every CLI run appends a record to `ds-audit.jsonl` with a UTC timestamp, command, pack path when available, plan hash, figure and chart counts, verification result, and status. The audit log is ignored by Git because it is a local run artifact.
