# -*- coding: utf-8 -*-
"""self_test for token-price-table-validator (scaffold v2, four defenses inherited).

D1: SystemExit caught in run_cli. D2: unicode source strings exercised.
D3: fixtures written with newline="". D4: last line "SUMMARY: PASS n/n".

NOTE: every fixture uses synthetic illustrative models (example-*) — no real
vendor price data anywhere in this suite.
"""
import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")  # D3

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "core", os.path.join(_HERE, "token_price_table_validator.py"))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
main = core.main

CASES = []


def case(category, name):
    def deco(fn):
        CASES.append((category, name, fn))
        return fn
    return deco


def run_cli(argv):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            ret = main(argv)
            code = 0 if ret is None else int(ret)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


_TMP = tempfile.mkdtemp(prefix="tptv_selftest_")


def write_fixture(name, obj):
    p = os.path.join(_TMP, name)
    with open(p, "w", encoding="utf-8", newline="") as f:  # D3
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
    return p


def row(**over):
    base = {"model": "example-small-1", "direction": "input", "price_per_unit": 0.25,
            "effective_from": "2026-01-01", "source": "illustrative"}
    base.update(over)
    return base


def table(rows):
    return {"version": 1, "currency": "USD", "unit": "per_1m_tokens", "models": rows}


def _rep(x):
    """Accept either a table or an already-computed report."""
    if isinstance(x, dict) and "errors" in x and "warnings" in x:
        return x
    return core.validate_table(x)


def errs(t):
    return sorted({e["rule"] for e in _rep(t)["errors"]})


def warns(t):
    return sorted({w["rule"] for w in _rep(t)["warnings"]})


# ---------- [A] functional ----------
def _t_minimal_valid():
    rep = core.validate_table(table([row(), row(direction="output",
                                               price_per_unit=0.75)]))
    assert rep["errors"] == [] and rep["warnings"] == [], rep
case("A", "minimal valid table")(_t_minimal_valid)

def _t_all_units():
    for unit in core.UNITS:
        t = dict(table([row()]), unit=unit)
        assert core.validate_table(t)["errors"] == []
case("A", "all supported units accepted")(_t_all_units)

def _t_zero_price_warn():
    rep = core.validate_table(table([row(price_per_unit=0)]))
    assert rep["errors"] == [] and "R7" in warns(rep)
case("A", "zero price warns, not errors")(_t_zero_price_warn)

def _t_effective_to_ok():
    t = table([dict(row(), effective_to="2026-01-31"),
               row(direction="output", price_per_unit=1.0),
               row(model="example-small-1", direction="input",
                   price_per_unit=0.30, effective_from="2026-02-01",
                   effective_to="2026-03-01", source="illustrative")])
    assert core.validate_table(t)["errors"] == []
case("A", "non-overlapping effective windows fine")(_t_effective_to_ok)

def _t_duplicate_row():
    t = table([row(), row(), row(direction="output", price_per_unit=1.0)])
    assert "R11" in errs(t)
case("A", "duplicate (model,direction,from) -> R11")(_t_duplicate_row)

def _t_overlap():
    t = table([row(effective_from="2026-01-01", effective_to="2026-06-30"),
               row(effective_from="2026-04-01", effective_to="2026-08-31"),
               row(direction="output", price_per_unit=1.0)])
    assert "R12" in errs(t)
case("A", "overlapping windows -> R12")(_t_overlap)

def _t_open_end_overlap():
    t = table([row(effective_from="2026-01-01"),
               row(effective_from="2026-05-01"),
               row(direction="output", price_per_unit=1.0)])
    assert "R12" in errs(t)
case("A", "open-ended window blocks later row -> R12")(_t_open_end_overlap)

def _t_missing_counterpart():
    t = table([row()])
    assert "R13" in warns(core.validate_table(t))
case("A", "input-only model warns R13")(_t_missing_counterpart)

def _t_unknown_top_key():
    t = dict(table([row(), row(direction="output", price_per_unit=1.0)]),
             vendor_hint="x")
    assert "R10" in warns(core.validate_table(t))
case("A", "unknown top-level key warns R10")(_t_unknown_top_key)

def _t_unknown_row_key():
    t = table([dict(row(), promo=True), row(direction="output", price_per_unit=1.0)])
    assert "R10" in warns(core.validate_table(t))
case("A", "unknown row key warns R10")(_t_unknown_row_key)

def _t_iso4217_currencies():
    for cur in ("USD", "EUR", "CNY"):
        t = dict(table([row(), row(direction="output", price_per_unit=1.0)]),
                 currency=cur)
        assert core.validate_table(t)["errors"] == []
case("A", "ISO-4217 currency codes accepted")(_t_iso4217_currencies)

def _t_unicode_source():
    t = table([dict(row(), source="示意数据-α"), row(direction="output",
                                                    price_per_unit=1.0)])
    assert core.validate_table(t)["errors"] == []
case("A", "unicode source string accepted (D2)")(_t_unicode_source)

def _t_cli_validate_ok():
    p = write_fixture("ok.json", table([row(), row(direction="output",
                                                   price_per_unit=0.75)]))
    code, out, _ = run_cli(["validate", p])
    assert code == 0 and "0 error(s)" in out
case("A", "CLI validate good -> 0")(_t_cli_validate_ok)

def _t_cli_validate_json():
    p = write_fixture("ok.json", table([row(), row(direction="output",
                                                   price_per_unit=0.75)]))
    code, out, _ = run_cli(["validate", p, "--json"])
    parsed = json.loads(out)
    assert code == 0 and parsed["errors"] == []
case("A", "CLI validate --json round-trip")(_t_cli_validate_json)

def _t_cli_validate_bad():
    p = write_fixture("bad.json", {"version": 2})
    code, out, _ = run_cli(["validate", p])
    assert code == 1 and "R1" in out
case("A", "CLI validate bad -> 1")(_t_cli_validate_bad)

def _t_cli_bench():
    code, out, _ = run_cli(["bench", "--rows", "500"])
    assert code == 0 and "rows/s" in out
case("A", "CLI bench runs")(_t_cli_bench)

def _t_report_shape():
    rep = core.validate_table(table([row()]))
    assert set(rep) == {"errors", "warnings"}
case("A", "report shape stable")(_t_report_shape)

def _t_2k_and_1m():
    t1 = dict(table([row(), row(direction="output", price_per_unit=1.0)]),
              unit="per_1k_tokens")
    t2 = dict(table([row(), row(direction="output", price_per_unit=1.0)]),
              unit="per_1m_tokens")
    assert core.validate_table(t1)["errors"] == []
    assert core.validate_table(t2)["errors"] == []
case("A", "per_1k and per_1m units valid")(_t_2k_and_1m)

def _t_multiple_models():
    rows = [row(model="example-a"), row(model="example-a", direction="output",
                                        price_per_unit=1.0),
            row(model="example-b"), row(model="example-b", direction="output",
                                        price_per_unit=2.0)]
    assert core.validate_table(table(rows))["errors"] == []
case("A", "multiple models validated")(_t_multiple_models)

# ---------- [B] exception paths ----------
def _t_non_dict():
    assert errs([1]) == ["R1"]
case("B", "non-dict table -> R1")(_t_non_dict)

def _t_bad_version():
    assert "R1" in errs(dict(table([row()]), version=2))
case("B", "version 2 -> R1")(_t_bad_version)

def _t_bad_currency():
    assert "R2" in errs(dict(table([row()]), currency="usd"))
    assert "R2" in errs(dict(table([row()]), currency="DOLLAR"))
case("B", "bad currency -> R2")(_t_bad_currency)

def _t_bad_unit():
    assert "R3" in errs(dict(table([row()]), unit="per_1000"))
case("B", "unknown unit -> R3")(_t_bad_unit)

def _t_empty_models():
    assert "R4" in errs(table([]))
case("B", "empty models -> R4")(_t_empty_models)

def _t_models_not_list():
    assert "R4" in errs(dict(table([row()]), models="all"))
case("B", "models not a list -> R4")(_t_models_not_list)

def _t_bad_model_name():
    assert "R5" in errs(table([dict(row(), model="BigModel")]))
    assert "R5" in errs(table([dict(row(), model="-lead")]))
case("B", "model name pattern violations -> R5")(_t_bad_model_name)

def _t_bad_direction():
    assert "R6" in errs(table([dict(row(), direction="inbound")]))
case("B", "unknown direction -> R6")(_t_bad_direction)

def _t_negative_price():
    assert "R7" in errs(table([dict(row(), price_per_unit=-0.1)]))
case("B", "negative price -> R7")(_t_negative_price)

def _t_nonfinite_price():
    t = {"version": 1, "currency": "USD", "unit": "per_1m_tokens",
         "models": [{"model": "example-x", "direction": "input",
                     "price_per_unit": float("inf"),
                     "effective_from": "2026-01-01", "source": "s"}]}
    assert "R7" in errs(t)
case("B", "infinite price -> R7")(_t_nonfinite_price)

def _t_price_string():
    t = {"version": 1, "currency": "USD", "unit": "per_1m_tokens",
         "models": [{"model": "example-x", "direction": "input",
                     "price_per_unit": "0.25",
                     "effective_from": "2026-01-01", "source": "s"}]}
    assert "R7" in errs(t)
case("B", "string price -> R7")(_t_price_string)

def _t_bad_date_format():
    assert "R8" in errs(table([dict(row(), effective_from="01/02/2026")]))
    assert "R8" in errs(table([dict(row(), effective_from="2026-2-1")]))
case("B", "malformed dates -> R8")(_t_bad_date_format)

def _t_impossible_date():
    assert "R8" in errs(table([dict(row(), effective_from="2026-02-30")]))
case("B", "2026-02-30 rejected -> R8")(_t_impossible_date)

def _t_to_before_from():
    t = table([dict(row(), effective_to="2025-12-31")])
    assert "R8" in errs(t)
case("B", "effective_to before from -> R8")(_t_to_before_from)

def _t_missing_source():
    t = table([dict(row(), source="")])
    assert "R9" in errs(t)
case("B", "blank source -> R9")(_t_missing_source)

def _t_row_not_dict():
    t = {"version": 1, "currency": "USD", "unit": "per_1m_tokens", "models": ["x"]}
    assert "R5" in errs(t)
case("B", "row not an object -> R5")(_t_row_not_dict)

def _t_no_args():
    code, _, _ = run_cli([])
    assert code == 2
case("B", "CLI no args -> SystemExit 2 (D1)")(_t_no_args)

def _t_unknown_cmd():
    code, _, _ = run_cli(["price"])
    assert code == 2
case("B", "CLI unknown subcommand -> 2")(_t_unknown_cmd)

def _t_missing_file():
    code, _, err = run_cli(["validate", os.path.join(_TMP, "nope.json")])
    assert code == 1 and "cannot read" in err
case("B", "CLI missing file -> 1")(_t_missing_file)

def _t_broken_json():
    p = os.path.join(_TMP, "broken.json")
    with open(p, "w", encoding="utf-8", newline="") as f:  # D3
        f.write("{oops")
    code, _, _ = run_cli(["validate", p])
    assert code == 1
case("B", "CLI unparseable JSON -> 1")(_t_broken_json)

# ---------- [C] extreme edges ----------
def _t_crlf_file():
    p = os.path.join(_TMP, "crlf.json")
    with open(p, "w", encoding="utf-8", newline="") as f:  # D3
        f.write(json.dumps(table([row(), row(direction="output",
                                             price_per_unit=1.0)])) + "\r\n")
    code, _, _ = run_cli(["validate", p])
    assert code == 0
case("C", "CRLF-terminated table file (D3)")(_t_crlf_file)

def _t_long_model_name():
    name = "example-" + "x" * 56  # exactly 64 chars
    t = table([dict(row(), model=name),
               dict(row(), model=name, direction="output", price_per_unit=1.0)])
    assert core.validate_table(t)["errors"] == []
case("C", "64-char model name accepted")(_t_long_model_name)

def _t_too_long_model_name():
    name = "example-" + "x" * 100
    assert "R5" in errs(table([dict(row(), model=name)]))
case("C", "over-long model name -> R5")(_t_too_long_model_name)

def _t_leap_day_ok():
    t = table([dict(row(), effective_from="2028-02-29"),
               row(direction="output", price_per_unit=1.0)])
    assert core.validate_table(t)["errors"] == []
case("C", "leap day 2028-02-29 accepted")(_t_leap_day_ok)

def _t_non_leap_rejected():
    assert "R8" in errs(table([dict(row(), effective_from="2026-02-29")]))
case("C", "2026-02-29 rejected (non-leap)")(_t_non_leap_rejected)

def _t_many_rows():
    rows = []
    for i in range(100):
        rows.append(row(model="example-m%03d" % i))
        rows.append(row(model="example-m%03d" % i, direction="output",
                        price_per_unit=1.0))
    rep = core.validate_table(table(rows))
    assert rep["errors"] == [] and rep["warnings"] == []
case("C", "200-row table validates cleanly")(_t_many_rows)

def _t_epoch_price_types():
    t = table([dict(row(), price_per_unit=1),  # int is a valid number
               row(direction="output", price_per_unit=2)])
    assert core.validate_table(t)["errors"] == []
case("C", "integer prices accepted")(_t_epoch_price_types)

def _t_bool_price_rejected():
    assert "R7" in errs(table([dict(row(), price_per_unit=True)]))
case("C", "boolean price rejected -> R7")(_t_bool_price_rejected)

def _t_effective_to_open_chain():
    t = table([dict(row(), effective_from="2026-01-01", effective_to="2026-01-31"),
               row(effective_from="2026-02-01", effective_to="2026-02-28"),
               row(effective_from="2026-03-01"),
               row(direction="output", price_per_unit=1.0)])
    assert core.validate_table(t)["errors"] == []
case("C", "chained windows without gaps fine")(_t_effective_to_open_chain)

def _t_adjacent_windows_ok():
    t = table([dict(row(), effective_from="2026-01-01", effective_to="2026-01-31"),
               row(effective_from="2026-01-31", effective_to="2026-02-28"),
               row(direction="output", price_per_unit=1.0)])
    assert "R12" in errs(core.validate_table(t))
case("C", "touching windows count as overlap (policy)")(_t_adjacent_windows_ok)

def _t_extra_keys_only_warns():
    t = dict(table([dict(row(), note="x"), row(direction="output",
                                               price_per_unit=1.0)]),
             metadata={"v": 2})
    rep = core.validate_table(t)
    assert rep["errors"] == [] and len(rep["warnings"]) == 2
case("C", "unknown keys warn but never error")(_t_extra_keys_only_warns)

def _t_currency_digit():
    assert "R2" in errs(dict(table([row()]), currency="US1"))
case("A", "currency with digit -> R2")(_t_currency_digit)

def _t_month_zero():
    assert "R8" in errs(table([dict(row(), effective_from="2026-00-10")]))
case("A", "month 00 rejected -> R8")(_t_month_zero)

def _t_model_digit_start():
    t = table([dict(row(), model="1model"),
               dict(row(), model="1model", direction="output", price_per_unit=1.0)])
    assert "R5" not in errs(t)
case("A", "model may start with a digit")(_t_model_digit_start)

def _t_model_underscore_ok():
    t = table([dict(row(), model="ex_ample.v2"),
               row(model="ex_ample.v2", direction="output", price_per_unit=1.0)])
    assert core.validate_table(t)["errors"] == []
case("A", "model with underscore/dot accepted")(_t_model_underscore_ok)

def _t_overlap_across_directions_ok():
    t = table([dict(row(), effective_from="2026-01-01"),
               dict(row(direction="output", price_per_unit=1.0),
                    effective_from="2026-01-01")])
    assert "R12" not in errs(t) and "R11" not in errs(t)
case("A", "same window on input/output is fine")(_t_overlap_across_directions_ok)

def _t_dup_requires_same_direction():
    t = table([row(effective_from="2026-01-01"),
               row(effective_from="2026-01-01", effective_to="2026-02-01"),
               row(direction="output", price_per_unit=1.0)])
    rep = core.validate_table(t)
    assert any(e["rule"] == "R11" for e in rep["errors"])
    assert any(e["rule"] == "R12" for e in rep["errors"])
case("A", "identical windows: both R11 and R12 fire")(_t_dup_requires_same_direction)

def _t_zero_price_path():
    rep = core.validate_table(table([dict(row(), price_per_unit=0),
                                     row(direction="output", price_per_unit=1.0)]))
    z = [w for w in rep["warnings"] if w["rule"] == "R7"]
    assert z and z[0]["path"].endswith("price_per_unit")
case("A", "zero-price warning carries field path")(_t_zero_price_path)

def _t_unknown_key_path():
    t = table([dict(row(), promo=True),
               row(direction="output", price_per_unit=1.0)])
    rep = core.validate_table(t)
    w = [w for w in rep["warnings"] if w["rule"] == "R10"]
    assert w and w[0]["path"].endswith("promo")
case("A", "unknown row key warning carries key path")(_t_unknown_key_path)

def _t_gap_between_windows_ok():
    t = table([dict(row(), effective_from="2026-01-01", effective_to="2026-01-31"),
               row(effective_from="2026-03-01"),
               row(direction="output", price_per_unit=1.0)])
    assert core.validate_table(t)["errors"] == []
case("A", "gap between windows is not an overlap")(_t_gap_between_windows_ok)

def _t_json_warnings_shape():
    p = write_fixture("warn.json", table([dict(row(), price_per_unit=0),
                                          row(direction="output", price_per_unit=1.0)]))
    code, out, _ = run_cli(["validate", p, "--json"])
    parsed = json.loads(out)
    assert code == 0 and parsed["warnings"] and set(parsed) == {"errors", "warnings"}
case("A", "--json warnings shape stable")(_t_json_warnings_shape)

def _t_meta_count():
    assert len(CASES) >= 60
case("C", "meta: at least 60 cases defined")(_t_meta_count)


class T(unittest.TestCase):
    pass


def _add(i, cat, name, fn):
    def t(self, _f=fn):
        _f()
    t.__doc__ = "%s: %s" % (cat, name)
    setattr(T, "test_%s_%03d_%s" % (cat, i, re.sub(r"[^0-9A-Za-z_]", "_", name)), t)


for _i, (_c, _n, _f) in enumerate(CASES):
    _add(_i + 1, _c, _n, _f)

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))  # D4
    sys.exit(0 if fails == 0 else 1)
