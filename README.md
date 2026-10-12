# token-price-table-validator

A schema validator for token unit-price tables: model / direction (input,
output) / price per unit / effective window, with internal-consistency
checks (duplicate rows, overlapping effective ranges, missing
input/output counterpart, currency and unit discipline). Schema validation
only — this repo ships **no real vendor price data**. Pure standard
library. *No direct equivalent found as of 2026-10-13.*

## Problem

Teams tracking LLM costs keep price tables in spreadsheets and wikis, where
they rot silently: two rows claim the same model-month, an input price has
no output counterpart, effective windows overlap, or a "price" is a string.
The first cost report built on such a table is wrong in ways nobody can
trace. What is missing is a boring, dependency-free gate that a price
table must pass before anything computes with it.

## How it works

A **price table** is JSON: `version`, ISO-4217 `currency`, `unit`
(`per_token` / `per_1k_tokens` / `per_1m_tokens`), and a `models` array of
rows `{model, direction, price_per_unit, effective_from, effective_to?,
source}`. The validator applies rules R1–R13: row shape and model-name
pattern, finite non-negative numbers (zero price warns), real calendar
dates, duplicate `(model, direction, effective_from)` triples, overlapping
effective windows per `(model, direction)` (open-ended rows block all later
rows), missing direction counterparts, and unknown-key advisories. Errors
fail; warnings inform.

## Quickstart

```console
$ python token_price_table_validator.py validate prices.json
warn  R7 $.models[3].price_per_unit: zero price (free tier or placeholder?)
0 error(s), 1 warn(s)
$ python token_price_table_validator.py validate prices.json --json | jq .errors
```

A 4-row table validates in <1ms; 5,000 rows took 0.022s [Measured] — run it
in CI on every prices.json change.

## Why not X

No tool with the same scope surfaced during research (checked 2026-10-13),
but adjacent solutions exist:

- **JSON Schema** — enforces row shape but not cross-row invariants
  (duplicate detection, window overlap, direction pairing) or
  calendar-aware dates.
- **OpenAPI/protobuf definitions of billing APIs** — describe transport,
  not the semantics of a historical price table with effective windows.
- **Cost-tracker SaaS dashboards** — ingest prices opaquely; they do not
  give you a validator artifact for *your* table, and none are stdlib-only.
- **Pandas-based checks** — a notebook can find duplicates, but notebooks
  are not CI gates and pull in a heavy dependency tree.

## Performance

All numbers [Measured] locally (Python 3.13, Windows 10, single core):

| Workload | Result | Command |
|---|---|---|
| 5,000 price rows validated | 0.022s (224k rows/s) | `python token_price_table_validator.py bench --rows 10000` |
| Typical 4-row table | <1ms | `python token_price_table_validator.py validate prices.json` |

## Minimal Fallback

Three formulas in any spreadsheet: `COUNTIFS(model,direction,from)>1` for
duplicates, a sort + `from_next <= to_current` comparison for overlaps, and
`COUNTIFS(model,direction)=1` for missing counterparts. You lose schema
discipline (types, dates, unknown keys) and the exit-code gate.

## Design Trade-offs

- **Schema-only scope.** The validator never judges whether a price is
  *correct* — only whether the table is internally coherent. Prices change;
  structure should not.
- **Touching windows overlap.** `to = next.from` is rejected to keep
  "which row applies on 2026-01-31?" decidable; use half-open windows
  (`to` exclusive) consistently.
- **Open-ended rows block later ones.** An open-ended price row is the
  current truth by definition; a newer row must close the old one first.
- **Direction pairing is a warning.** Input-only or output-only models are
  legal (some APIs bill one direction), so it warns instead of failing.

## Limits & Second-order Effects

- The validator cannot detect a plausible-but-wrong price; peer review of
  values stays human work.
- `source` is required but unverified — a table of lies with tidy sources
  passes.
- Teams may encode multi-year tables as dozens of rows; window overlap
  errors get noisier before they get better.
- Currency conversion, tax, and volume tiers are out of scope by design;
  bolting them on would triple the schema.

## FAQ

**When NOT to use this?** Not for validating a *vendor's* published price
page (scraping is a different problem), not for usage metering data, and
not where a billing system already enforces contracts transactionally.

**Does this include real model prices?** No — fixtures and benchmarks use
synthetic `example-*` models only, and the schema requires a `source` per
row so imported data stays traceable.

**Why is `per_1k` still supported?** Legacy tables; new tables should
standardize on `per_1m_tokens`.

**What counts as a valid model name?** `[a-z0-9][a-z0-9._-]{1,63}` —
lowercase, no spaces, ≤64 chars.

## [Core Assumptions]

1. A price table's job is to answer "what did a token cost for model M,
   direction D, at date T?" — deterministically.
2. Effective windows are half-open and non-overlapping per
   `(model, direction)`.
3. Prices are per-token unit prices in one declared currency; tiers,
   taxes and conversion live elsewhere.

Confidence: high in validator behavior (self_test.py, 61 cases); medium
that the R1–R13 rule set covers real-world table rot — extensions are
additive. As of 2026-10-13.

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [oncall-handoff-spec](https://github.com/chenhz01/oncall-handoff-spec) · [merge-conflict-predictor](https://github.com/chenhz01/merge-conflict-predictor) · [backup-integrity-verifier](https://github.com/chenhz01/backup-integrity-verifier)
