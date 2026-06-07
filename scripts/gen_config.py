#!/usr/bin/env python3
"""
CSV-driven config-header generator for light_config.

Takes a CSV with columns:
    field_name, type, default, min, max, description

and generates:

  1. A C++ struct with YLT_REFL reflection annotation.
  2. A validate_<StructName>() function that checks min/max ranges
     for int and double fields and returns light_config::LoadResult.
  3. (Optional) Sample JSON and YAML config files — one valid set using
     defaults, and one invalid set with out-of-range values that
     exercise every range constraint.

Usage:
    python3 scripts/gen_config.py --input schema.csv --struct-name MyConfig --output include/my_config.hpp
    python3 scripts/gen_config.py ... --generate-samples  # also emit .json + .yaml samples
"""

import argparse
import csv
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Type mapping and value helpers
# ---------------------------------------------------------------------------

def map_type(csv_type: str) -> str:
    """Map CSV type string to C++ type."""
    mapping = {
        "int": "int",
        "double": "double",
        "bool": "bool",
        "string": "std::string",
        "vector<string>": "std::vector<std::string>",
        "vector<int>": "std::vector<int>",
        "vector<double>": "std::vector<double>",
    }
    if csv_type in mapping:
        return mapping[csv_type]
    return csv_type


def _parse_default(val: str, csv_type: str) -> object:
    """Parse a CSV default string into a Python value."""
    val = val.strip()
    if csv_type == "int":
        return int(val)
    if csv_type == "double":
        return float(val)
    if csv_type == "bool":
        return val.lower() == "true"
    if csv_type == "string":
        return val.strip('"')
    return val


def _example_value(csv_type: str) -> object:
    """Return a plausible example value for a type."""
    if csv_type == "int":
        return 0
    if csv_type == "double":
        return 0.0
    if csv_type == "bool":
        return False
    if csv_type == "string":
        return ""
    if csv_type == "vector<string>":
        return ["example"]
    if csv_type == "vector<int>":
        return [1, 2]
    if csv_type == "vector<double>":
        return [1.0, 2.0]
    return ""


def _violating_value(min_val: str, max_val: str, csv_type: str) -> object:
    """Return a value that violates min/max, for testing."""
    if csv_type == "int":
        if max_val:
            return int(max_val) + 1
        return int(min_val) - 1
    if csv_type == "double":
        if max_val:
            return float(max_val) + 1.0
        return float(min_val) - 1.0
    return 0


def _field_value(row: dict, use_default: bool = True, violate: bool = False) -> object:
    """Return a JSON/YAML-appropriate value for a field."""
    csv_type = row["type"].strip()
    default = (row.get("default") or "").strip()

    if use_default:
        if default:
            return _parse_default(default, csv_type)
        return _example_value(csv_type)

    # Generate a violating value for range-constrained fields.
    min_val = (row.get("min") or "").strip()
    max_val = (row.get("max") or "").strip()
    if violate and csv_type in ("int", "double") and (min_val or max_val):
        return _violating_value(min_val, max_val, csv_type)
    if default:
        return _parse_default(default, csv_type)
    return _example_value(csv_type)


# ---------------------------------------------------------------------------
# C++ code generation
# ---------------------------------------------------------------------------

def escape_default(val: str, cpp_type: str) -> str:
    """Return a C++ literal for the default value, or empty string."""
    if val is None or val.strip() == "":
        return ""
    val = val.strip()
    if cpp_type == "std::string":
        return f'"{val}"'
    return val


def make_struct(rows: list[dict], struct_name: str) -> str:
    """Generate the C++ struct definition."""
    lines: list[str] = []
    has_optional = False

    for row in rows:
        fname = row["field_name"].strip()
        ftype_cell = row["type"].strip()
        default_cell = row.get("default", "").strip() if row.get("default") else ""
        cpp_type = map_type(ftype_cell)
        default_literal = escape_default(default_cell, cpp_type)

        desc = (row.get("description") or "").strip()
        if desc:
            lines.append(f"    // {desc}")

        if default_cell == "":
            lines.append(f"    std::optional<{cpp_type}> {fname};")
            has_optional = True
        else:
            lines.append(f"    {cpp_type} {fname} = {default_literal};")

    body = "\n".join(lines)
    refl_fields = ", ".join(r["field_name"].strip() for r in rows)

    include_optional = "#include <optional>" if has_optional else ""

    return f"""#pragma once

/// Auto-generated config struct from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.

#include <light_config/light_config.hpp>
#include <string>
#include <vector>
{include_optional}

struct {struct_name} {{
{body}
}};
YLT_REFL({struct_name}, {refl_fields});
"""


def make_validate(rows: list[dict], struct_name: str) -> str:
    """Generate the validate function that checks min/max ranges."""
    checks: list[str] = []
    has_validation = False

    for row in rows:
        fname = row["field_name"].strip()
        default_cell = row.get("default", "").strip() if row.get("default") else ""
        min_val = (row.get("min") or "").strip()
        max_val = (row.get("max") or "").strip()

        if not min_val and not max_val:
            continue

        is_optional = default_cell == ""
        field_expr = f"cfg.{fname}.value()" if is_optional else f"cfg.{fname}"

        cond_parts: list[str] = []
        msg_parts: list[str] = []

        if min_val and max_val:
            cond_parts.append(f"{field_expr} < {min_val} || {field_expr} > {max_val}")
            msg_parts.append(f'" << {field_expr} << " out of range [{min_val}, {max_val}]')
        elif min_val:
            cond_parts.append(f"{field_expr} < {min_val}")
            msg_parts.append(f'" << {field_expr} << " below minimum {min_val}')
        elif max_val:
            cond_parts.append(f"{field_expr} > {max_val}")
            msg_parts.append(f'" << {field_expr} << " above maximum {max_val}')

        cond_str = " || ".join(cond_parts)
        msg_str = "; ".join(msg_parts)

        check_block = f"""    if ({cond_str}) {{
        std::ostringstream oss;
        oss << "{fname} = {msg_str}";
        errors.push_back(oss.str());
    }}"""

        if is_optional:
            check_block = f"""    if (cfg.{fname}.has_value()) {{
{check_block}
    }}"""

        checks.append(check_block)
        has_validation = True

    if not has_validation:
        return f"""/// Validate range constraints from CSV schema.
/// No range constraints defined; always succeeds.
inline light_config::LoadResult validate_{struct_name}(
    const {struct_name}& /*cfg*/) {{
    return light_config::LoadResult::success();
}}
"""

    body = "\n".join(checks)
    return f"""#include <sstream>

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
inline light_config::LoadResult validate_{struct_name}(
    const {struct_name}& cfg) {{
    std::vector<std::string> errors;
{body}
    if (errors.empty()) {{
        return light_config::LoadResult::success();
    }}

    std::ostringstream summary;
    summary << errors.size() << " validation error(s)";
    for (const auto& e : errors) {{
        summary << "\\n  " << e;
    }}
    return light_config::LoadResult::failure(
        light_config::ErrorCode::kValidationError, summary.str());
}}
"""


# ---------------------------------------------------------------------------
# Sample config generation (JSON + YAML)
# ---------------------------------------------------------------------------

def _build_config_dict(rows: list[dict], use_default: bool, violate: bool) -> dict:
    d: dict[str, object] = {}
    for row in rows:
        fname = row["field_name"].strip()
        d[fname] = _field_value(row, use_default=use_default, violate=violate)
    return d


def _write_json(data: dict, path: Path) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _write_yaml(data: dict, path: Path) -> None:
    with open(path, "w") as f:
        _emit_yaml(data, f, indent=0)


def _emit_yaml(data: dict, f, indent: int) -> None:
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            f.write(f"{prefix}{key}:\n")
            _emit_yaml(value, f, indent + 1)
        elif isinstance(value, list):
            if len(value) == 0:
                f.write(f"{prefix}{key}: []\n")
            else:
                f.write(f"{prefix}{key}:\n")
                for item in value:
                    f.write(f"{prefix}  - {_yaml_scalar(item)}\n")
        elif isinstance(value, bool):
            f.write(f"{prefix}{key}: {'true' if value else 'false'}\n")
        elif isinstance(value, str):
            if any(ch in value for ch in ':{}[]#&*!|>\'"@`,'):
                f.write(f'{prefix}{key}: "{value}"\n')
            elif value == "":
                f.write(f'{prefix}{key}: ""\n')
            else:
                f.write(f"{prefix}{key}: {value}\n")
        elif value is None:
            f.write(f"{prefix}{key}: null\n")
        else:
            f.write(f"{prefix}{key}: {value}\n")


def _yaml_scalar(v: object) -> str:
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


def write_sample_configs(rows: list[dict], output_dir: str) -> tuple[Path, Path, Path, Path]:
    """Write valid and invalid JSON + YAML sample files. Returns the four paths."""
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    valid_json = outdir / "valid_config.json"
    valid_yaml = outdir / "valid_config.yaml"
    invalid_json = outdir / "invalid_config.json"
    invalid_yaml = outdir / "invalid_config.yaml"

    valid_data = _build_config_dict(rows, use_default=True, violate=False)
    invalid_data = _build_config_dict(rows, use_default=False, violate=True)

    _write_json(valid_data, valid_json)
    _write_yaml(valid_data, valid_yaml)
    _write_json(invalid_data, invalid_json)
    _write_yaml(invalid_data, invalid_yaml)

    return valid_json, valid_yaml, invalid_json, invalid_yaml


def has_range_constraints(rows: list[dict]) -> bool:
    for row in rows:
        if (row.get("min") or "").strip() or (row.get("max") or "").strip():
            return True
    return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate(input_path: str, struct_name: str, output_path: str,
             generate_samples: bool = False, sample_dir: str = "") -> None:
    inpath = Path(input_path)
    if not inpath.exists():
        print(f"Error: input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(inpath, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("Error: CSV file is empty.", file=sys.stderr)
        sys.exit(1)

    header = set(reader.fieldnames or [])
    missing = {"field_name", "type"} - header
    if missing:
        print(f"Error: CSV missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)

    header_src = make_struct(rows, struct_name)
    validate_src = make_validate(rows, struct_name)

    outpath = Path(output_path)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        f.write(header_src)
        f.write("\n")
        f.write(validate_src)

    print(f"Generated {output_path} ({len(rows)} fields)")

    if generate_samples:
        sdir = sample_dir if sample_dir else outpath.parent
        vj, vy, ij, iy = write_sample_configs(rows, str(sdir))
        print(f"Generated {vj}")
        print(f"Generated {vy}")
        if has_range_constraints(rows):
            print(f"Generated {ij} (out-of-range values)")
            print(f"Generated {iy} (out-of-range values)")
        else:
            print("(no range constraints in CSV — skipping invalid configs)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate light_config struct + validation code from a CSV schema."
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Path to CSV schema file.")
    parser.add_argument("--struct-name", "-s", required=True,
                        help="Name of the generated C++ struct.")
    parser.add_argument("--output", "-o", required=True,
                        help="Path to output header file.")
    parser.add_argument("--generate-samples", action="store_true",
                        help="Emit valid.json, valid.yaml, invalid.json, invalid.yaml "
                             "sample config files.")
    parser.add_argument("--sample-dir", default="",
                        help="Directory for sample configs (default: same as output).")
    args = parser.parse_args()
    generate(args.input, args.struct_name, args.output,
             generate_samples=args.generate_samples,
             sample_dir=args.sample_dir)


if __name__ == "__main__":
    main()
