#!/usr/bin/env python3
"""
CSV-driven config-header generator for light_config.

Takes a CSV with columns:
    field_name, group, type, default, min, max, description

Every row belongs to a struct via the 'group' column (the exact C++ struct
type name).  Containment is expressed in the CSV itself: when a row's 'type'
matches another group name, that struct becomes a nested member of the current
group.  The member field name comes from 'field_name'.

The root struct is auto-detected: the group that no other group references as
a member type.

Usage:
    python3 scripts/gen_config.py --input schema.csv --output include/my_config.hpp
    python3 scripts/gen_config.py ... --generate-samples  # also emit .json + .yaml samples
"""

import argparse
import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path


# ---------------------------------------------------------------------------
# Type mapping and value helpers
# ---------------------------------------------------------------------------

def map_type(csv_type: str) -> str:
    """Map CSV type string to C++ type, or pass through if not a built-in."""
    mapping = {
        "int": "int",
        "double": "double",
        "bool": "bool",
        "string": "std::string",
        "vector<string>": "std::vector<std::string>",
        "vector<int>": "std::vector<int>",
        "vector<double>": "std::vector<double>",
    }
    return mapping.get(csv_type, csv_type)


def _parse_default(val: str, csv_type: str) -> object:
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
    csv_type = row["type"].strip()
    default = (row.get("default") or "").strip()

    if use_default:
        if default:
            return _parse_default(default, csv_type)
        return _example_value(csv_type)

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

def _preamble(has_optional: bool) -> str:
    inc_opt = "#include <optional>" if has_optional else ""
    return f"""#pragma once

/// Auto-generated config struct from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.

#include <light_config/light_config.hpp>
#include <string>
#include <vector>
{inc_opt}"""


def escape_default(val: str, cpp_type: str) -> str:
    if val is None or val.strip() == "":
        return ""
    val = val.strip()
    if cpp_type == "std::string":
        return f'"{val}"'
    return val


def _make_struct_body(struct_name: str,
                      regular_rows: list[dict],
                      nested_members: list[tuple[str, str]]) -> tuple[str, bool]:
    """Generate struct definition body.

    Args:
        struct_name: the C++ struct type name.
        regular_rows: rows with built-in types (int, string, etc.).
        nested_members: list of (member_name, nested_type_name).

    Returns (body_string, has_optional).
    """
    lines: list[str] = []
    has_optional = False

    for row in regular_rows:
        fname = row["field_name"].strip()
        ftype_cell = row["type"].strip()
        default_cell = (row.get("default") or "").strip()
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

    # Nested struct members
    for member_name, nested_type in nested_members:
        desc_for_nested = ""
        for row in regular_rows:  # we won't have desc for nested, skip
            pass
        lines.append(f"    {nested_type} {member_name};")

    body = "\n".join(lines)
    refl_fields = [r["field_name"].strip() for r in regular_rows]
    refl_fields.extend(m for m, _ in nested_members)
    refl_str = ", ".join(refl_fields)

    return f"""struct {struct_name} {{
{body}
}};
YLT_REFL({struct_name}, {refl_str});""", has_optional


def _make_validate_func(struct_name: str,
                        regular_rows: list[dict],
                        nested_members: list[tuple[str, str]]) -> str:
    """Generate validate_<StructName>() with range checks and recursion."""
    checks: list[str] = []
    has_validation = False

    for row in regular_rows:
        fname = row["field_name"].strip()
        default_cell = (row.get("default") or "").strip()
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

    # Recurse into nested struct members
    for member_name, nested_type in nested_members:
        recurse_block = f"""    {{
        auto r = validate_{nested_type}(cfg.{member_name});
        if (!r.ok()) {{
            errors.push_back("{member_name}: " + r.message);
        }}
    }}"""
        checks.append(recurse_block)
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
    return f"""/// Validate range constraints defined in the CSV schema.
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

def _build_sample_dict(group_regular: dict[str, list[dict]],
                       group_nested: dict[str, list[tuple[str, str]]],
                       all_groups: dict[str, list[dict]],
                       root: str,
                       use_default: bool, violate: bool) -> dict:
    """Recursively build a nested dict for JSON/YAML output."""

    def _build_for_group(group_name: str) -> dict:
        d: dict[str, object] = {}
        for row in group_regular.get(group_name, []):
            fname = row["field_name"].strip()
            d[fname] = _field_value(row, use_default=use_default, violate=violate)
        for member_name, nested_type in group_nested.get(group_name, []):
            d[member_name] = _build_for_group(nested_type)
        return d

    return _build_for_group(root)


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


def _has_range_constraints(rows: list[dict]) -> bool:
    for row in rows:
        if (row.get("min") or "").strip() or (row.get("max") or "").strip():
            return True
    return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate(input_path: str, output_path: str,
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
    missing = {"field_name", "group", "type"} - header
    if missing:
        print(f"Error: CSV missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)

    # Partition rows by group.
    all_groups: dict[str, list[dict]] = OrderedDict()
    for row in rows:
        group = (row.get("group") or "").strip()
        if group == "":
            print("Error: every row must have a non-empty 'group' value.",
                  file=sys.stderr)
            sys.exit(1)
        all_groups.setdefault(group, []).append(row)

    group_names = set(all_groups.keys())

    # Classify each group's rows:
    #   regular_rows: type is a built-in (not another group name)
    #   nested_members: type matches another group → (member_field_name, nested_group)
    group_regular: dict[str, list[dict]] = {}
    group_nested: dict[str, list[tuple[str, str]]] = {}

    for gname, grows in all_groups.items():
        regular: list[dict] = []
        nested: list[tuple[str, str]] = []
        for row in grows:
            csv_type = row["type"].strip()
            if csv_type in group_names:
                nested.append((row["field_name"].strip(), csv_type))
            else:
                regular.append(row)
        group_regular[gname] = regular
        group_nested[gname] = nested

    # Find root: the group not referenced as a member type by any other group.
    referenced: set[str] = set()
    for nested_list in group_nested.values():
        for _, nested_type in nested_list:
            referenced.add(nested_type)

    roots = [g for g in all_groups if g not in referenced]
    if len(roots) == 0:
        print("Error: circular containment detected — no root struct found.",
              file=sys.stderr)
        sys.exit(1)
    if len(roots) > 1:
        print(f"Warning: multiple root candidates {roots}; using '{roots[0]}'.",
              file=sys.stderr)
    root = roots[0]

    # Sort groups topologically: groups that are referenced by others come first.
    # Simple approach: all non-root groups first (they are referenced), root last.
    non_roots = [g for g in all_groups if g != root]
    ordered_groups = non_roots + [root]

    # Check for optional fields.
    all_has_optional = False
    for gname in ordered_groups:
        for row in group_regular[gname]:
            if not (row.get("default") or "").strip():
                all_has_optional = True
                break

    preamble = _preamble(all_has_optional)
    output_lines: list[str] = [preamble, ""]

    # Generate struct definitions (non-root first, root last).
    for gname in ordered_groups:
        body, _ = _make_struct_body(gname, group_regular[gname], group_nested[gname])
        output_lines.append(body)
        output_lines.append("")

    # Validation code.
    output_lines.append("#include <sstream>")
    output_lines.append("")

    for gname in ordered_groups:
        validate_fn = _make_validate_func(gname, group_regular[gname], group_nested[gname])
        output_lines.append(validate_fn)
        output_lines.append("")

    # Write output.
    outpath = Path(output_path)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    with open(outpath, "w") as f:
        f.write("\n".join(output_lines))

    print(f"Generated {output_path} "
          f"(root: {root}, "
          f"{len(ordered_groups)} struct(s), "
          f"{sum(len(v) for v in group_regular.values())} fields)")

    # Sample configs.
    if generate_samples:
        sdir = sample_dir if sample_dir else outpath.parent
        outdir = Path(sdir)
        outdir.mkdir(parents=True, exist_ok=True)

        valid_data = _build_sample_dict(group_regular, group_nested,
                                        all_groups, root,
                                        use_default=True, violate=False)
        invalid_data = _build_sample_dict(group_regular, group_nested,
                                          all_groups, root,
                                          use_default=False, violate=True)

        vj = outdir / "valid_config.json"
        vy = outdir / "valid_config.yaml"
        ij = outdir / "invalid_config.json"
        iy = outdir / "invalid_config.yaml"

        _write_json(valid_data, vj)
        _write_yaml(valid_data, vy)
        print(f"Generated {vj}")
        print(f"Generated {vy}")

        has_any_range = any(_has_range_constraints(rows)
                           for rows in group_regular.values())
        if has_any_range:
            _write_json(invalid_data, ij)
            _write_yaml(invalid_data, iy)
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
    parser.add_argument("--output", "-o", required=True,
                        help="Path to output header file.")
    parser.add_argument("--generate-samples", action="store_true",
                        help="Emit valid.json, valid.yaml, invalid.json, invalid.yaml "
                             "sample config files.")
    parser.add_argument("--sample-dir", default="",
                        help="Directory for sample configs (default: same as output).")
    args = parser.parse_args()
    generate(args.input, args.output,
             generate_samples=args.generate_samples,
             sample_dir=args.sample_dir)


if __name__ == "__main__":
    main()
