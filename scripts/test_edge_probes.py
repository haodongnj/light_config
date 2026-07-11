#!/usr/bin/env python3
"""Generator edge-probe harness.

Promotes the 18 CSV probes that lived under build/edge_probes/ (gitignored,
created during the REVIEW.md audit) into a permanent self-test.  Each CSV is
read from tests/edge_probes/<name>.csv and run through gen_config.py:

  COMPILE probes — generate, then -fsyntax-only the output under -Werror
  (same flags as test_cpp_compile.py).  Verifies the generator emits
  compiling C++ for the wide type matrix the CRITICAL fixes targeted.

  REJECT probes — assert the generator exits nonzero AND that the error
  message contains a recognizable substring, so a regression that rejects
  for the *wrong* reason still trips the test.

Run:  python3 scripts/test_edge_probes.py
Exits nonzero on the first failing assertion.  Requires a C++17 compiler on
PATH for COMPILE probes; REJECT probes run without one.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _gen_test_helpers as h  # noqa: E402
from _gen_test_helpers import check, COMPILER  # noqa: E402

# The probes live under tests/edge_probes/ (one level up from scripts/).
_PROBE_DIR = (SCRIPT_DIR.parent / "tests" / "edge_probes").resolve()

# ---- probe classification (verified against the current generator) ----
COMPILE_PROBES = [
    "int64_extremes", "double_extremes", "big_enum", "signed_enum",
    "enum_neg_auto_cursor", "deep_nest_5level", "two_roots",
    "string_special_default",
]
REJECT_PROBES = {
    "cycle": "circular containment",
    "dup_enumerator": "duplicate enumerator",
    "enum_name_collide_cross_file": "duplicate enum_name",
    "two_enums_same_name": "duplicate enum_name",
    "conflicting_hpp_per_group": "conflicting hpp_file",
    "group_diff_hpp": "conflicting hpp_file",
    "enum_over_int32": "int range",
    "special_char_default": "vector defaults are not supported",
    "optional_vector_with_range": "min/max are not supported on this type",
    "empty_optional_no_default": "conflicting hpp_file",
}


def _probe_csv(name: str) -> str:
    p = _PROBE_DIR / f"{name}.csv"
    assert p.exists(), f"missing probe CSV: {p}"
    return p.read_text()


def _generate_capture_stderr(csv_text: str) -> tuple[bool, str]:
    """Generate; return (ok, stderr_text).  ok=False if generation raised."""
    import gen_config
    from _gen_config.exceptions import GeneratorError
    import tempfile, os
    tmp = Path(tempfile.mkdtemp(prefix="lc_edge_"))
    csv_path = tmp / "schema.csv"
    csv_path.write_text(csv_text)
    out_dir = tmp / "out"
    out_dir.mkdir()
    cfg = gen_config.GeneratorConfig(input_csv=str(csv_path),
                                     output_dir=str(out_dir),
                                     namespace="edge")
    import io
    old_err = sys.stderr
    sys.stderr = io.StringIO()
    try:
        gen_config.generate(cfg)
        return True, ""
    except (SystemExit, GeneratorError) as e:
        return False, (sys.stderr.getvalue() + str(e))
    finally:
        sys.stderr = old_err


def test_compile_probes() -> None:
    if not COMPILER:
        check(True, "compile probes skipped (no C++ compiler)")
        return
    for name in COMPILE_PROBES:
        out_dir = h.generate_to_dir(_probe_csv(name), namespace="edge")
        ok, diag = h.compile_dir(out_dir)
        check(ok, f"compile probe '{name}'\n{diag}" if not ok
              else f"compile probe '{name}'")


def test_reject_probes() -> None:
    for name, expected_substr in REJECT_PROBES.items():
        csv_text = _probe_csv(name)
        ok, stderr = _generate_capture_stderr(csv_text)
        if ok:
            check(False, f"reject probe '{name}' should have failed but succeeded")
            continue
        check(expected_substr in stderr,
              f"reject probe '{name}' error mentions '{expected_substr}'"
              f"\n  got: {stderr.strip()[:160]}"
              if expected_substr not in stderr
              else f"reject probe '{name}' error mentions '{expected_substr}'")


def main() -> int:
    if not COMPILER:
        print("NOTE: no C++ compiler on PATH — COMPILE probes will be skipped, "
              "REJECT probes still run.")
    test_compile_probes()
    test_reject_probes()
    if h.get_fail_count():
        print(f"\n{h.get_fail_count()} edge-probe self-test(s) failed.")
        return 1
    print("\nAll edge-probe self-tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
