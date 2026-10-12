# Changelog — token-price-table-validator

All releases are local drafts; no remote operations are performed.

## v0.1.1 — 2026-10-13

Fixed:
- model names may start with a digit; overlap policy for touching windows documented.

Changed:
- self_test expanded to >=60 cases across functional / exception / extreme-edge
  categories (scaffold v2 four defenses: SystemExit capture, Unicode-safe
  matching, Windows newline-safe fixtures, SUMMARY last line).
- README: added Performance section with [Measured] numbers and in-repo
  reproduction commands.

## v0.1.0 — 2026-10-13

Added:
- Initial local draft: token unit-price table schema validator (no real vendor data).
- argparse CLI (pure standard library), self_test.py, MIT LICENSE.
