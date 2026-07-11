#!/usr/bin/env python3
"""Compile-the-generated-C++ self-check for scripts/gen_config.py.

The text-based self-tests in test_gen_config.py assert on substrings of the
generated source, which catches obvious emit bugs but *cannot* catch defects
that produce syntactically-valid-looking C++ that still fails to compile
(non-compiling vector defaults, unescaped string defaults, non-portable
INT64_MIN literals, min/max emitted on non-ordered types, …).

This harness regenerates a small CSV into a temp dir and actually invokes the
C++ compiler (`-fsyntax-only`) on the output.  It is the integration test the
main review (REVIEW.md, finding M10) identified as the missing guard that let
the CRITICAL generator defects C1–C4 and C7b reach master undetected.

Run as a plain script:  python3 scripts/test_cpp_compile.py
Exits nonzero on the first failing assertion.  Requires a C++17 compiler on
PATH (c++ / clang++ / g++).
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gen_config  # noqa: E402
from _gen_config.exceptions import GeneratorError  # noqa: E402

import _gen_test_helpers as _h  # noqa: E402
from _gen_test_helpers import (  # noqa: E402
    check,
    COMPILER as _COMPILER,
    compile_dir as _compile_dir,
    generate_to_dir as _generate_to_dir,
    generate_exits as _generate_exits,
)

# ---------------------------------------------------------------------------
# Happy-path: the full integer width matrix compiles and links to light_config.
# This is the broad guard REVIEW.md M10 asked for — it would have caught
# C1–C4 and C7b before they reached master.
# ---------------------------------------------------------------------------


def test_full_type_matrix_compiles() -> None:
    """Every supported scalar type compiles against light_config headers."""
    if not _COMPILER:
        check(True, "compile test skipped (no compiler)")
        return
    csv_text = (
        "__metadata__,namespace=mix\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "i8,Mix,int8,-128,-128,127,false,int8\n"
        "i16,Mix,int16,-32768,-32768,32767,false,int16\n"
        "i32,Mix,int32,-2147483648,-2147483648,2147483647,false,int32\n"
        "i64,Mix,int64,-9223372036854775807,-9223372036854775807,9223372036854775807,false,int64\n"
        "u8,Mix,uint8,0,0,255,false,uint8\n"
        "u16,Mix,uint16,0,0,65535,false,uint16\n"
        "u32,Mix,uint32,0,0,4294967295,false,uint32\n"
        "u64,Mix,uint64,0,0,18446744073709551615,false,uint64\n"
        "d,Mix,double,1.5,0.0,100.0,false,double\n"
        "b,Mix,bool,false,,,false,bool\n"
        "s,Mix,string,hello,,,false,string\n"
        "vs,Mix,vector<string>,,,,true,optional vector string\n"
        "vi,Mix,vector<int>,,,,true,optional vector int\n"
        "vd,Mix,vector<double>,,,,true,optional vector double\n"
    )
    out_dir = _generate_to_dir(csv_text)
    ok, diag = _compile_dir(out_dir)
    check(ok, f"full type matrix compiles (c++={_COMPILER})\n{diag}" if not ok
          else "full type matrix compiles")


# ---------------------------------------------------------------------------
# C2: string defaults containing " or \ must compile.
# ---------------------------------------------------------------------------


def test_string_default_with_quote_compiles() -> None:
    """A string default containing a double-quote compiles (C2)."""
    if not _COMPILER:
        check(True, "compile test skipped (no compiler)")
        return
    csv_text = (
        'field_name,group,type,default,min,max,optional,description\n'
        's,Mix,string,a"b,,,false,quoted default\n'
    )
    out_dir = _generate_to_dir(csv_text)
    ok, diag = _compile_dir(out_dir)
    check(ok, f'string default with quote compiles\n{diag}' if not ok
          else 'string default with quote compiles')


def test_string_default_with_backslash_compiles() -> None:
    """A string default containing a backslash compiles (C2)."""
    if not _COMPILER:
        check(True, "compile test skipped (no compiler)")
        return
    csv_text = (
        'field_name,group,type,default,min,max,optional,description\n'
        's,Mix,string,C:\\path\\to\\file,,,false,backslash default\n'
    )
    out_dir = _generate_to_dir(csv_text)
    ok, diag = _compile_dir(out_dir)
    check(ok, f'string default with backslash compiles\n{diag}' if not ok
          else 'string default with backslash compiles')


# ---------------------------------------------------------------------------
# C7b: int64 INT64_MIN (and uint64 INT64_MAX-ish) literals compile under -Werror.
# ---------------------------------------------------------------------------


def test_int64_min_default_compiles_clean() -> None:
    """int64 default = INT64_MIN compiles under -Werror (C7b)."""
    if not _COMPILER:
        check(True, "compile test skipped (no compiler)")
        return
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "lo,Mix,int64,-9223372036854775808,,,false,int64 min default\n"
        "hi,Mix,int64,9223372036854775807,,,false,int64 max default\n"
    )
    out_dir = _generate_to_dir(csv_text)
    ok, diag = _compile_dir(out_dir)
    check(ok, f"int64 INT64_MIN/MAX defaults compile under -Werror\n{diag}" if not ok
          else "int64 INT64_MIN/MAX defaults compile under -Werror")


def test_uint64_max_default_compiles_clean() -> None:
    """uint64 default = UINT64_MAX compiles under -Werror (C7b)."""
    if not _COMPILER:
        check(True, "compile test skipped (no compiler)")
        return
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "hi,Mix,uint64,18446744073709551615,,,false,uint64 max default\n"
    )
    out_dir = _generate_to_dir(csv_text)
    ok, diag = _compile_dir(out_dir)
    check(ok, f"uint64 UINT64_MAX default compiles under -Werror\n{diag}" if not ok
          else "uint64 UINT64_MAX default compiles under -Werror")


def test_int64_min_bound_emitted_portably() -> None:
    """The generator emits the portable (MAX-1) spelling for INT64_MIN bounds.

    The *comparison expression* in the generated validator must use the
    portable spelling; the human-readable error message and the traceability
    comment may keep the original value (those are not compiled).
    """
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "v,Mix,int64,-9223372036854775808,-9223372036854775808,9223372036854775807,false,bound\n"
    )
    out_dir = _generate_to_dir(csv_text)
    cpp_text = next(out_dir.glob("*.cpp")).read_text()
    # The comparison line must use the portable spelling, not the bare literal.
    check("cfg.v < (-9223372036854775807LL - 1)" in cpp_text,
          "INT64_MIN min-bound comparison uses portable (MAX-1) spelling")
    check("cfg.v > 9223372036854775807LL" in cpp_text,
          "INT64_MAX max-bound comparison uses LL-suffixed literal")
    # And the bare literal must NOT appear as a compiled comparison operand
    # (i.e. "cfg.v < -9223372036854775808" without the portable form).
    check("cfg.v < -9223372036854775808" not in cpp_text,
          "no bare -INT64_MIN comparison operand in generated validator")


# ---------------------------------------------------------------------------
# C1: non-empty vector defaults must be REJECTED (no valid C++ emission today).
# ---------------------------------------------------------------------------


def test_vector_string_default_rejected() -> None:
    """A non-empty vector<string> default is rejected, not silently emitted (C1)."""
    csv_text = (
        'field_name,group,type,default,min,max,optional,description\n'
        'vs,Mix,vector<string>,"[""a"",""b""]",,,false,vector default\n'
    )
    check(_generate_exits(csv_text), "non-empty vector<string> default rejected")


def test_vector_int_default_rejected() -> None:
    """A non-empty vector<int> default is rejected, not silently emitted (C1)."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "vi,Mix,vector<int>,1|2|3,,,false,vector int default\n"
    )
    check(_generate_exits(csv_text), "non-empty vector<int> default rejected")


def test_vector_double_default_rejected() -> None:
    """A non-empty vector<double> default is rejected (C1)."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "vd,Mix,vector<double>,1.5|2.5,,,false,vector double default\n"
    )
    check(_generate_exits(csv_text), "non-empty vector<double> default rejected")


def test_empty_vector_default_still_allowed() -> None:
    """An empty (or absent) vector default is still allowed — opt-in default."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "vs,Mix,vector<string>,,,,true,optional vector\n"
    )
    out_dir = _generate_to_dir(csv_text)
    hpps = list(out_dir.glob("*.hpp"))
    check(bool(hpps), "empty vector default still generates a header")
    check("std::optional<std::vector<std::string>> vs;" in hpps[0].read_text(),
          "empty optional vector default emitted as std::optional<...>")


# ---------------------------------------------------------------------------
# C3: enum explicit values outside int range must be rejected.
# ---------------------------------------------------------------------------


def test_enum_value_above_int_max_rejected() -> None:
    """An enum explicit value >= 2**31 is rejected (C3)."""
    csv_text = (
        "__enum__,enum_name=Over,enum_def=a=2147483648,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,Mix,Over,a,,,false,over-range enum\n"
    )
    check(_generate_exits(csv_text), "enum value 2147483648 (> INT32_MAX) rejected")


def test_enum_value_below_int_min_rejected() -> None:
    """An enum explicit value < -2**31 is rejected (C3)."""
    csv_text = (
        "__enum__,enum_name=Under,enum_def=a=-2147483649,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,Mix,Under,a,,,false,under-range enum\n"
    )
    check(_generate_exits(csv_text), "enum value -2147483649 (< INT32_MIN) rejected")


def test_enum_value_at_int_max_allowed() -> None:
    """An enum explicit value == INT32_MAX is allowed (boundary, C3)."""
    if not _COMPILER:
        check(True, "compile test skipped (no compiler)")
        return
    csv_text = (
        "__enum__,enum_name=Edge,enum_def=hi=2147483647,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,Mix,Edge,hi,,,false,edge enum\n"
    )
    out_dir = _generate_to_dir(csv_text)
    ok, diag = _compile_dir(out_dir)
    check(ok, f"enum value INT32_MAX compiles\n{diag}" if not ok
          else "enum value INT32_MAX compiles")


# ---------------------------------------------------------------------------
# C4: min/max on string / bool / vector<*> must be rejected.
# ---------------------------------------------------------------------------


def test_min_max_on_string_rejected() -> None:
    """min/max on a string field is rejected, not emitted as non-compiling code (C4)."""
    for col, val in (("min", "1"), ("max", "100")):
        other = "" if col == "min" else "1"
        csv_text = (
            "field_name,group,type,default,min,max,optional,description\n"
            f"s,Mix,string,hi,{val if col=='min' else other},{val if col=='max' else other},false,str bound\n"
        )
        check(_generate_exits(csv_text), f"string field with '{col}' rejected")


def test_min_max_on_bool_rejected() -> None:
    """min/max on a bool field is rejected (C4)."""
    for col, val in (("min", "0"), ("max", "1")):
        other = "" if col == "min" else "0"
        csv_text = (
            "field_name,group,type,default,min,max,optional,description\n"
            f"b,Mix,bool,false,{val if col=='min' else other},{val if col=='max' else other},false,bool bound\n"
        )
        check(_generate_exits(csv_text), f"bool field with '{col}' rejected")


def test_min_max_on_vector_rejected() -> None:
    """min/max on a vector<*> field is rejected (C4)."""
    for vtype in ("vector<string>", "vector<int>", "vector<double>"):
        # Optional vector (no default) carrying a min/max bound.  The
        # bound is what we want rejected — everything else is valid.
        csv_text = (
            "field_name,group,type,default,min,max,optional,description\n"
            f"v,Mix,{vtype},,1,10,true,vector bound\n"
        )
        check(_generate_exits(csv_text), f"{vtype} field with min/max rejected")


# ---------------------------------------------------------------------------
# Regression: the existing sample_config.csv still regenerates and compiles.
# This is the guard that the checked-in examples keep building after the fixes.
# ---------------------------------------------------------------------------


def test_sample_config_regenerates_and_compiles() -> None:
    """examples/sample_config.csv regenerates and compiles (no regression)."""
    if not _COMPILER:
        check(True, "compile test skipped (no compiler)")
        return
    out_dir = _generate_to_dir(
        (SCRIPT_DIR.parent / "examples" / "sample_config.csv").read_text()
    )
    ok, diag = _compile_dir(out_dir)
    check(ok, f"sample_config.csv regenerates and compiles\n{diag}" if not ok
          else "sample_config.csv regenerates and compiles")


def main() -> int:
    if not _COMPILER:
        print("NOTE: no C++ compiler on PATH — compile tests will be skipped, "
              "rejection tests still run.")
    test_full_type_matrix_compiles()
    test_string_default_with_quote_compiles()
    test_string_default_with_backslash_compiles()
    test_int64_min_default_compiles_clean()
    test_uint64_max_default_compiles_clean()
    test_int64_min_bound_emitted_portably()
    test_vector_string_default_rejected()
    test_vector_int_default_rejected()
    test_vector_double_default_rejected()
    test_empty_vector_default_still_allowed()
    test_enum_value_above_int_max_rejected()
    test_enum_value_below_int_min_rejected()
    test_enum_value_at_int_max_allowed()
    test_min_max_on_string_rejected()
    test_min_max_on_bool_rejected()
    test_min_max_on_vector_rejected()
    test_sample_config_regenerates_and_compiles()
    if _h.get_fail_count():
        print(f"\n{_h.get_fail_count()} compile/reject self-test(s) failed.")
        return 1
    print("\nAll compile/reject self-tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
