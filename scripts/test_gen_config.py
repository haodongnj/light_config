#!/usr/bin/env python3
"""Dependency-free self-check for scripts/gen_config.py.

Run as a plain script:  python3 scripts/test_gen_config.py
Exits nonzero on the first failing assertion.  No pytest / no third-party
imports — only the stdlib and the generator module sitting next to this file.

Covers the fixed-width integer type mapping and the input-validation guards:
  - `int`        -> int32_t          (in generated .hpp)
  - `vector<int>`-> std::vector<int32_t>
  - `uint16`     -> uint16_t         (explicit-width CSV type)
  - `int8`       -> int8_t
  - <cstdint> is included in the generated header
  - unknown CSV type cell  -> generator exits nonzero
  - out-of-range int8 default (300) -> generator exits nonzero
"""

import os
import sys
import tempfile
from pathlib import Path

# Make the sibling gen_config.py importable.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gen_config  # noqa: E402


_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _FAIL
    if not cond:
        print(f"[FAIL] {msg}")
        _FAIL += 1
    else:
        print(f"[PASS] {msg}")


def _write_csv(text: str) -> tuple[Path, Path]:
    """Write *text* to a temp CSV; return (csv_path, out_dir)."""
    tmp = Path(tempfile.mkdtemp(prefix="lc_gen_test_"))
    csv_path = tmp / "schema.csv"
    csv_path.write_text(text)
    out_dir = tmp / "out"
    out_dir.mkdir()
    return csv_path, out_dir


def _generate(csv_text: str) -> tuple[Path, str]:
    """Generate from *csv_text* into a temp dir; return (out_dir, hpp_text)."""
    csv_path, out_dir = _write_csv(csv_text)
    cfg = gen_config.GeneratorConfig(
        input_csv=str(csv_path),
        output_dir=str(out_dir),
    )
    # Silence the generator's stdout/stderr progress lines.
    with open(os.devnull, "w") as devnull:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = devnull
        try:
            gen_config.generate(cfg)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    # Monolithic mode emits <root_snake>.hpp; root is auto-detected.
    hpp = out_dir / "my_config.hpp"
    if not hpp.exists():
        # Fall back to whatever .hpp was emitted.
        hpps = list(out_dir.glob("*.hpp"))
        check(bool(hpps), "a .hpp file was emitted")
        hpp = hpps[0]
    return out_dir, hpp.read_text()


def _generate_exits(csv_text: str) -> bool:
    """Return True if generating from *csv_text* exits nonzero."""
    csv_path, out_dir = _write_csv(csv_text)
    cfg = gen_config.GeneratorConfig(
        input_csv=str(csv_path),
        output_dir=str(out_dir),
    )
    # Suppress the generator's stderr error lines during expected-failure
    # cases so the self-test output stays readable.
    old_err = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            gen_config.generate(cfg)
        return False
    except SystemExit:
        return True
    finally:
        sys.stderr = old_err


def test_type_mapping() -> None:
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "port,MyConfig,int,8080,1,65535,false,Port\n"
        "gears,MyConfig,uint16,0,0,65535,false,Gears\n"
        "slot,MyConfig,int8,3,0,127,false,Slot\n"
        "counts,MyConfig,vector<int>,,,,true,Optional counts\n"
    )
    _, hpp = _generate(csv_text)
    check("int32_t port = 8080;" in hpp, "int -> int32_t")
    check("uint16_t gears = 0;" in hpp, "uint16 -> uint16_t")
    check("int8_t slot = 3;" in hpp, "int8 -> int8_t")
    check("std::optional<std::vector<int32_t>> counts;" in hpp,
          "optional vector<int> -> std::optional<std::vector<int32_t>>")
    check("#include <cstdint>" in hpp, "<cstdint> included")


def test_unknown_type_rejected() -> None:
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "weird,MyConfig,int9,0,,,false,Bad type\n"
    )
    check(_generate_exits(csv_text), "unknown type 'int9' rejected")


def test_out_of_range_default_rejected() -> None:
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "too_big,MyConfig,int8,300,,,false,Too big for int8\n"
    )
    check(_generate_exits(csv_text), "int8 default=300 rejected (out of range)")


def test_out_of_range_bound_rejected() -> None:
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "lo,MyConfig,uint8,0,-1,255,false,Negative min for unsigned\n"
    )
    check(_generate_exits(csv_text), "uint8 min=-1 rejected (out of range)")


def test_back_compat_int_still_works() -> None:
    """Existing CSV using `int` regenerates with fixed-width int32_t."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    _, hpp = _generate(csv_text)
    check("int32_t v = 42;" in hpp, "back-compat: int still emits int32_t")


def test_namespace_from_metadata_emits_wrapper() -> None:
    """__metadata__ namespace=k --> struct is inside namespace k."""
    csv_text = (
        "__metadata__,namespace=myproj\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    _, hpp = _generate(csv_text)
    check("namespace myproj {" in hpp,
          "namespace open emitted from __metadata__")
    check("} // namespace myproj" in hpp,
          "namespace close emitted from __metadata__")


def test_namespace_nested_from_metadata() -> None:
    """__metadata__ namespace=a::b --> nested namespace emitted."""
    csv_text = (
        "__metadata__,namespace=a::b\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    _, hpp = _generate(csv_text)
    check("namespace a::b {" in hpp,
          "nested namespace a::b open emitted")


def test_namespace_cli_override() -> None:
    """CLI --namespace overrides __metadata__ namespace."""
    csv_text = (
        "__metadata__,namespace=csv_ns\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    csv_path, out_dir = _write_csv(csv_text)
    cfg = gen_config.GeneratorConfig(
        input_csv=str(csv_path),
        output_dir=str(out_dir),
        namespace="cli_ns",
    )
    with open(os.devnull, "w") as devnull:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = devnull
        try:
            gen_config.generate(cfg)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    hpps = list(out_dir.glob("*.hpp"))
    check(bool(hpps), "hpp emitted with cli namespace override")
    hpp = hpps[0].read_text()
    check("namespace cli_ns {" in hpp,
          "CLI --namespace overrides __metadata__ namespace")
    check("namespace csv_ns" not in hpp,
          "CSV namespace NOT present when CLI overrides")


def test_back_compat_no_namespace_global_scope() -> None:
    """No namespace metadata or CLI -> structs at global scope (unchanged)."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    _, hpp = _generate(csv_text)
    check("namespace" not in hpp.split("#include")[-1],
          "no namespace wrapper when namespace absent")
    check("struct MyConfig {" in hpp,
          "struct at global scope when namespace absent")


def test_schema_version_constant_emitted() -> None:
    """__metadata__ schema_version → constexpr constant in generated code."""
    csv_text = (
        "__metadata__,schema_version=3.2.1,generator=light_config\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    _, hpp = _generate(csv_text)
    check(
        'constexpr std::string_view kMyConfigSchemaVersion{"3.2.1"};' in hpp,
        "schema_version 3.2.1 emitted as constexpr constant",
    )


def test_schema_version_missing_metadata_emits_empty() -> None:
    """No __metadata__ schema_version → empty constant emitted."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    _, hpp = _generate(csv_text)
    check(
        'constexpr std::string_view kMyConfigSchemaVersion{""};' in hpp,
        "missing schema_version emits empty string constant",
    )


def test_optional_column_required() -> None:
    """CSV missing the 'optional' column is rejected."""
    csv_text = (
        "field_name,group,type,default,min,max,description\n"
        "v,MyConfig,int,42,0,100,Value\n"
    )
    check(_generate_exits(csv_text),
          "missing 'optional' column is rejected")


def test_optional_true_without_default() -> None:
    """optional=true, no default -> std::optional<T> (no initializer)."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "cert,MyConfig,string,,,,true,Cert file\n"
    )
    _, hpp = _generate(csv_text)
    check("std::optional<std::string> cert;" in hpp,
          "optional without default -> std::optional<T> field;")


def test_optional_true_with_default() -> None:
    """optional=true with default -> std::optional<T> = val."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "port,MyConfig,int,8080,1,65535,true,Optional port\n"
    )
    _, hpp = _generate(csv_text)
    check("std::optional<int32_t> port = 8080;" in hpp,
          "optional with default -> std::optional<T> = val")


def test_required_without_default_rejected() -> None:
    """optional=false and no default -> generator error."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "port,MyConfig,int,,,,false,Required port\n"
    )
    check(_generate_exits(csv_text),
          "required field without default is rejected")


def test_optional_nested_struct_rejected() -> None:
    """optional=true on a nested-struct type -> generator error."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "host,Nested,string,localhost,,,false,IP\n"
        "parent,Root,Nested,,,,true,Nested struct\n"
    )
    check(_generate_exits(csv_text),
          "optional=true on nested struct type is rejected")


def test_optional_false_explicit() -> None:
    """optional=false with default -> plain T field."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "port,MyConfig,int,8080,1,65535,false,Required port\n"
    )
    _, hpp = _generate(csv_text)
    check("int32_t port = 8080;" in hpp,
          "optional=false -> plain T field")
    check("std::optional" not in hpp,
          "optional=false -> no optional in output")


def test_optional_empty_treated_as_false() -> None:
    """Empty optional column is treated as false."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "port,MyConfig,int,8080,1,65535,,Required port\n"
    )
    _, hpp = _generate(csv_text)
    check("int32_t port = 8080;" in hpp,
          "empty optional column -> plain T field")
    check("std::optional" not in hpp,
          "empty optional column -> no optional in output")


def test_optional_validation_uses_value() -> None:
    """Validate code uses .value() for optional fields with range constraints."""
    csv_text = (
        "field_name,group,type,default,min,max,optional,description\n"
        "port,MyConfig,int,,1,65535,true,Optional port with range\n"
        "host,MyConfig,string,localhost,,,false,Required host\n"
    )
    out_dir, hpp = _generate(csv_text)
    # Find the .cpp file
    cpp_files = list(out_dir.glob("*.cpp"))
    check(bool(cpp_files), "cpp file emitted for validation test")
    cpp = cpp_files[0].read_text()
    check("cfg.port.has_value()" in cpp,
          "optional field validation guards with has_value()")
    check("cfg.port.value()" in cpp,
          "optional field validation accesses .value()")


def main() -> int:
    test_type_mapping()
    test_unknown_type_rejected()
    test_out_of_range_default_rejected()
    test_out_of_range_bound_rejected()
    test_back_compat_int_still_works()
    test_namespace_from_metadata_emits_wrapper()
    test_namespace_nested_from_metadata()
    test_namespace_cli_override()
    test_back_compat_no_namespace_global_scope()
    test_schema_version_constant_emitted()
    test_schema_version_missing_metadata_emits_empty()
    test_optional_column_required()
    test_optional_true_without_default()
    test_optional_true_with_default()
    test_required_without_default_rejected()
    test_optional_nested_struct_rejected()
    test_optional_false_explicit()
    test_optional_empty_treated_as_false()
    test_optional_validation_uses_value()
    if _FAIL:
        print(f"\n{_FAIL} self-test(s) failed.")
        return 1
    print("\nAll self-tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
