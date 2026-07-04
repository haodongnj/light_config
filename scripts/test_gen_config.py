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
from _gen_config.exceptions import GeneratorError  # noqa: E402


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
    except (SystemExit, GeneratorError):
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
    check("#include <cstdint>" in hpp, "<cstdint> included (int types present)")


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


# ---------------------------------------------------------------------------
# Enum support
# ---------------------------------------------------------------------------


def test_enum_type_accepted_in_field() -> None:
    """enum declared via __enum__ is accepted as a field type."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info|warn|error,"
        "hpp_file=network.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "level,MyConfig,LogLevel,info,,,false,Log verbosity\n"
    )
    _, hpp = _generate(csv_text)
    check("LogLevel level = LogLevel::info;" in hpp,
          "enum field accepted and emitted with qualified default")


def test_enum_def_parsing_basic() -> None:
    """__enum__ row with auto-sequential values emits correct definition."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info|warn|error,"
        "hpp_file=network.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "level,MyConfig,LogLevel,info,,,false,Log verbosity\n"
    )
    _, hpp = _generate(csv_text)
    check("enum class LogLevel { debug, info, warn, error };" in hpp,
          "enum class emitted with auto-sequential values")
    check("std::array<int, 4> value = {0, 1, 2, 3}" in hpp,
          "enum_value specialization with sequential values")


def test_enum_def_parsing_explicit() -> None:
    """__enum__ row with explicit integer values."""
    csv_text = (
        "__enum__,enum_name=Protocol,enum_def=http=80|https=443|ssh=22,"
        "hpp_file=network.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "p,MyConfig,Protocol,http,,,false,Protocol\n"
    )
    _, hpp = _generate(csv_text)
    check("enum class Protocol { http, https, ssh };" in hpp,
          "enum class emitted with explicit values")
    check("std::array<int, 3> value = {80, 443, 22}" in hpp,
          "enum_value specialization with explicit values")


def test_enum_def_parsing_mixed() -> None:
    """__enum__ row with mixed auto-sequential and explicit values."""
    csv_text = (
        "__enum__,enum_name=Mixed,enum_def=a|b=5|c,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "m,MyConfig,Mixed,a,,,false,Mixed enum\n"
    )
    _, hpp = _generate(csv_text)
    # a=0 (auto), b=5 (explicit), c=1 (next available after 0)
    check("enum class Mixed { a, b, c };" in hpp,
          "enum class emitted with mixed values")
    check("std::array<int, 3> value = {0, 5, 1}" in hpp,
          "enum_value specialization with mixed values (auto-cursor gap fill)")


def test_enum_def_missing_enum_name_rejected() -> None:
    """__enum__ row without enum_name is rejected."""
    csv_text = (
        "__enum__,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    check(_generate_exits(csv_text),
          "__enum__ missing enum_name rejected")


def test_enum_def_empty_enum_def_rejected() -> None:
    """__enum__ row with empty enum_def is rejected."""
    csv_text = (
        "__enum__,enum_name=Empty,enum_def=,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    check(_generate_exits(csv_text),
          "__enum__ empty enum_def rejected")


def test_enum_def_missing_hpp_file_rejected() -> None:
    """__enum__ row without hpp_file is rejected."""
    csv_text = (
        "__enum__,enum_name=NoFile,enum_def=a|b\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    check(_generate_exits(csv_text),
          "__enum__ missing hpp_file rejected")


def test_enum_def_duplicate_name_rejected() -> None:
    """Duplicate enum_name in __enum__ rows is rejected."""
    csv_text = (
        "__enum__,enum_name=Dup,enum_def=a|b,hpp_file=x.hpp\n"
        "__enum__,enum_name=Dup,enum_def=c|d,hpp_file=y.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    check(_generate_exits(csv_text),
          "__enum__ duplicate enum_name rejected")


def test_enum_def_duplicate_enumerator_rejected() -> None:
    """Duplicate enumerator name within an enum is rejected."""
    csv_text = (
        "__enum__,enum_name=DupEnum,enum_def=a|b|a,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "v,MyConfig,int,42,0,100,false,Value\n"
    )
    check(_generate_exits(csv_text),
          "__enum__ duplicate enumerator name rejected")


def test_enum_default_mapped_to_qualified_literal() -> None:
    """Enum default 'info' is emitted as LogLevel::info."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info|warn|error,"
        "hpp_file=network.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "level,MyConfig,LogLevel,info,,,false,Log verbosity\n"
    )
    _, hpp = _generate(csv_text)
    check("LogLevel level = LogLevel::info;" in hpp,
          "enum default emitted as qualified literal")


def test_enum_default_not_an_enumerator_rejected() -> None:
    """Enum default that isn't a valid enumerator is rejected."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info|warn|error,"
        "hpp_file=network.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "level,MyConfig,LogLevel,not_a_level,,,false,Bad default\n"
    )
    check(_generate_exits(csv_text),
          "enum default not matching any enumerator rejected")


def test_enum_cross_file_include_emitted() -> None:
    """Cross-file enum reference generates #include."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info,hpp_file=network.hpp\n"
        "field_name,group,type,default,min,max,optional,description,hpp_file\n"
        "level,MyConfig,LogLevel,info,,,false,Log level,my_config.hpp\n"
    )
    out_dir, hpp = _generate(csv_text)
    # Find the file containing MyConfig
    mc_hpp = out_dir / "my_config.hpp"
    check(mc_hpp.exists(), "my_config.hpp emitted")
    content = mc_hpp.read_text()
    check('#include "network.hpp"' in content,
          "cross-file include emitted for enum")


def test_enum_same_file_no_include() -> None:
    """Enum used in same hpp_file does not generate a cross-file include."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info,"
        "hpp_file=my_config.hpp\n"
        "field_name,group,type,default,min,max,optional,description,hpp_file\n"
        "level,MyConfig,LogLevel,info,,,false,Log level,my_config.hpp\n"
    )
    out_dir, hpp = _generate(csv_text)
    mc_hpp = out_dir / "my_config.hpp"
    content = mc_hpp.read_text()
    # Should NOT have an include for itself
    check('#include "my_config.hpp"' not in content,
          "no self-include for enum in same file")


def test_enum_value_specialization_emitted() -> None:
    """enum_value<T> specialization is emitted in generated code."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info,hpp_file=x.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "level,MyConfig,LogLevel,info,,,false,Log level\n"
    )
    _, hpp = _generate(csv_text)
    check("iguana::enum_value<LogLevel>" in hpp,
          "enum_value specialization emitted")
    check("#include <array>" in hpp,
          "#include <array> emitted for enum def")


def test_enum_validation_skipped() -> None:
    """Enum fields produce no range checks in validate_ function."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info|warn|error,"
        "hpp_file=network.hpp\n"
        "field_name,group,type,default,min,max,optional,description\n"
        "level,MyConfig,LogLevel,info,,,false,Log verbosity\n"
        "port,MyConfig,int,8080,1,65535,false,Port with range\n"
    )
    out_dir, hpp = _generate(csv_text)
    cpp_files = list(out_dir.glob("*.cpp"))
    check(bool(cpp_files), "cpp file emitted")
    cpp = cpp_files[0].read_text()
    # Port should have range check, LogLevel should not
    check("cfg.port" in cpp, "port field has validation")
    check("cfg.level" not in cpp, "enum field has no validation check")
    check("#include <array>" in hpp, "#include <array> emitted")


def test_sample_json_uses_enum_string() -> None:
    """Generated JSON sample uses enum string, not integer."""
    csv_text = (
        "__enum__,enum_name=LogLevel,enum_def=debug|info|warn|error,"
        "hpp_file=my_config.hpp\n"
        "field_name,group,type,default,min,max,optional,description,hpp_file\n"
        "level,MyConfig,LogLevel,info,,,false,Log level,my_config.hpp\n"
    )
    csv_path, out_dir = _write_csv(csv_text)
    cfg = gen_config.GeneratorConfig(
        input_csv=str(csv_path),
        output_dir=str(out_dir),
        generate_samples=True,
    )
    with open(os.devnull, "w") as devnull:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = devnull
        try:
            gen_config.generate(cfg)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    jf = out_dir / "valid_config.json"
    check(jf.exists(), "valid_config.json emitted")
    data = jf.read_text()
    check('"info"' in data, "enum value in JSON is string 'info'")
    check("0" not in data.split('"level"')[1][:20],
          "enum value is NOT integer 0")


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
    test_enum_type_accepted_in_field()
    test_enum_def_parsing_basic()
    test_enum_def_parsing_explicit()
    test_enum_def_parsing_mixed()
    test_enum_def_missing_enum_name_rejected()
    test_enum_def_empty_enum_def_rejected()
    test_enum_def_missing_hpp_file_rejected()
    test_enum_def_duplicate_name_rejected()
    test_enum_def_duplicate_enumerator_rejected()
    test_enum_default_mapped_to_qualified_literal()
    test_enum_default_not_an_enumerator_rejected()
    test_enum_cross_file_include_emitted()
    test_enum_same_file_no_include()
    test_enum_value_specialization_emitted()
    test_enum_validation_skipped()
    test_sample_json_uses_enum_string()
    if _FAIL:
        print(f"\n{_FAIL} self-test(s) failed.")
        return 1
    print("\nAll self-tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
