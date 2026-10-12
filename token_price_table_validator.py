# -*- coding: utf-8 -*-
"""token-price-table-validator: schema validation for token unit-price tables
(model / direction / price / effective window) + internal consistency checks.

Pure standard library. CLI via argparse.
Schema validation only — this tool ships NO real vendor price data.
Exit codes: 0 valid (warnings allowed), 1 errors, 2 usage error (argparse).
"""
import argparse
import json
import math
import re
import sys
import time
from datetime import date

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")           # ISO-4217 is ASCII by definition
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
UNITS = ("per_token", "per_1k_tokens", "per_1m_tokens")
DIRECTIONS = ("input", "output")
ITEM_KEYS = {"model", "direction", "price_per_unit", "effective_from",
             "effective_to", "source"}
TOP_KEYS = {"version", "currency", "unit", "models"}
OPEN_END = "9999-12-31"


def valid_date(s):
    """Return True when s is a real calendar date in YYYY-MM-DD form."""
    if not isinstance(s, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def validate_table(table):
    """Validate a price-table dict. Returns {errors, warnings} with entries
    {rule, path, message}."""
    errs, warns = [], []

    def err(rule, path, msg):
        errs.append({"rule": rule, "path": path, "message": msg})

    def warn(rule, path, msg):
        warns.append({"rule": rule, "path": path, "message": msg})

    if not isinstance(table, dict):
        err("R1", "$", "price table must be a JSON object")
        return {"errors": errs, "warnings": warns}
    if table.get("version") != 1:
        err("R1", "$.version", "version must be 1")
    cur = table.get("currency")
    if not isinstance(cur, str) or not CURRENCY_RE.match(cur):
        err("R2", "$.currency", "currency must be a 3-letter ISO-4217 code")
    if table.get("unit") not in UNITS:
        err("R3", "$.unit", "unit must be one of %s" % (", ".join(UNITS),))
    for k in table:
        if k not in TOP_KEYS:
            warn("R10", "$." + k, "unknown top-level key %r" % k)
    rows = table.get("models")
    if not isinstance(rows, list) or not rows:
        err("R4", "$.models", "models must be a non-empty array")
        return {"errors": errs, "warnings": warns}

    seen_keys = set()
    intervals = {}
    directions_by_model = {}
    for i, row in enumerate(rows):
        path = "$.models[%d]" % i
        if not isinstance(row, dict):
            err("R5", path, "row must be an object")
            continue
        for k in row:
            if k not in ITEM_KEYS:
                warn("R10", path + "." + k, "unknown row key %r" % k)
        model = row.get("model")
        if not isinstance(model, str) or not MODEL_RE.match(model):
            err("R5", path + ".model", "model must match [a-z0-9][a-z0-9._-]{1,63}")
            model = None
        direction = row.get("direction")
        if direction not in DIRECTIONS:
            err("R6", path + ".direction", "direction must be input|output")
            direction = None
        price = row.get("price_per_unit")
        if isinstance(price, bool) or not isinstance(price, (int, float)) \
                or not math.isfinite(price):
            err("R7", path + ".price_per_unit", "price must be a finite number")
        elif price < 0:
            err("R7", path + ".price_per_unit", "price must be >= 0")
        elif price == 0:
            warn("R7", path + ".price_per_unit", "zero price (free tier or placeholder?)")
        if not valid_date(row.get("effective_from")):
            err("R8", path + ".effective_from", "effective_from must be YYYY-MM-DD")
            eff_from = None
        else:
            eff_from = row["effective_from"]
        eff_to = row.get("effective_to")
        if eff_to is not None:
            if not valid_date(eff_to):
                err("R8", path + ".effective_to", "effective_to must be YYYY-MM-DD")
            elif eff_from is not None and eff_to < eff_from:
                err("R8", path + ".effective_to", "effective_to precedes effective_from")
        if not _nonempty(row.get("source")):
            err("R9", path + ".source", "source must be a non-empty string")
        if model is not None and direction is not None and eff_from is not None:
            key = (model, direction, eff_from)
            if key in seen_keys:
                err("R11", path, "duplicate (model, direction, effective_from) row")
            else:
                seen_keys.add(key)
            intervals.setdefault((model, direction), []).append(
                (eff_from, eff_to if valid_date(eff_to) else OPEN_END))
            directions_by_model.setdefault(model, set()).add(direction)

    for (model, direction), ivs in sorted(intervals.items()):
        ivs.sort()
        for a, b in zip(ivs, ivs[1:]):
            if b[0] <= a[1]:
                err("R12", "$.models", "%s/%s: effective window %s..%s overlaps %s..%s"
                    % (model, direction, a[0], a[1], b[0], b[1]))
    for model, dirs in sorted(directions_by_model.items()):
        missing = set(DIRECTIONS) - dirs
        if missing:
            warn("R13", "$.models", "model %s lacks %s price row(s)"
                 % (model, "/".join(sorted(missing))))
    return {"errors": errs, "warnings": warns}


def _nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_validate(args):
    try:
        table = _load(args.table)
    except (OSError, ValueError) as e:
        print("cannot read/parse %s: %s" % (args.table, e), file=sys.stderr)
        return 1
    rep = validate_table(table)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        for e in rep["errors"]:
            print("error %s %s: %s" % (e["rule"], e["path"], e["message"]))
        for w in rep["warnings"]:
            print("warn  %s %s: %s" % (w["rule"], w["path"], w["message"]))
        print("%d error(s), %d warn(s)" % (len(rep["errors"]), len(rep["warnings"])))
    return 1 if rep["errors"] else 0


def cmd_bench(args):
    rows = []
    n_models = max(1, args.rows // 4)
    for i in range(n_models):
        for direction in DIRECTIONS:
            rows.append({"model": "example-model-%05d" % i, "direction": direction,
                         "price_per_unit": (i % 17) + 0.25,
                         "effective_from": "2026-01-01",
                         "source": "illustrative"})
    table = {"version": 1, "currency": "USD", "unit": "per_1m_tokens", "models": rows}
    t0 = time.perf_counter()
    rep = validate_table(table)
    dt = time.perf_counter() - t0
    print("bench: %d price rows validated in %.3fs (%.0f rows/s, %d errors)"
          % (len(rows), dt, len(rows) / dt if dt > 0 else 0, len(rep["errors"])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="token-price-table-validator",
        description="Schema validator for token unit-price tables (model / "
                    "direction / price / effective window). Schema checks only; "
                    "ships no real vendor price data.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate a price-table JSON file")
    v.add_argument("table")
    v.add_argument("--json", action="store_true")
    v.set_defaults(fn=cmd_validate)
    b = sub.add_parser("bench", help="synthetic benchmark")
    b.add_argument("--rows", type=int, default=10000)
    b.set_defaults(fn=cmd_bench)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
