#!/usr/bin/env python3
"""
CSV-driven config-header generator for light_config.

Takes a CSV with columns:
    field_name, group, type, default, min, max, description, hpp_file

Every row belongs to a struct via the 'group' column (the exact C++ struct
type name).  Containment is expressed in the CSV itself: when a row's 'type'
matches another group name, that struct becomes a nested member of the current
group.  The member field name comes from 'field_name'.

The root struct is auto-detected: the group that no other group references as
a member type.

File grouping (three modes, in order of precedence):

  1. CSV-driven  — when any row carries a non-empty 'hpp_file', every group
     is placed into the .hpp/.cpp pair named by its hpp_file column.  Groups
     sharing the same hpp_file are bundled into one file pair.  Cross-file
     #includes are emitted automatically.

  2. --per-struct — one .hpp/.cpp pair per struct group.

  3. Monolithic   — all structs in a single .hpp/.cpp pair (default).

Generated files:
    <hpp_dir>/<hpp_file>.hpp         — struct definitions + validation decls
    <src_dir>/<hpp_stem>.cpp         — validation implementations
    <output_dir>/valid_config.json   — (optional) sample valid config
    <output_dir>/valid_config.yaml   — (optional) sample valid config

Usage:
    python3 scripts/gen_config.py --input examples/sample_config.csv
    python3 scripts/gen_config.py --input examples/sample_config.csv \\
        --output-dir build/ --hpp-dir include/config/ --src-dir src/config/ \\
        --per-struct --generate-samples
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class GeneratorConfig:
    """All tunables for a generation run."""

    input_csv: str
    output_dir: str = "examples/"
    hpp_dir: Optional[str] = None
    src_dir: Optional[str] = None
    struct_name: str = ""
    hpp_name: Optional[str] = None
    namespace: str = ""
    per_struct: bool = False
    generate_samples: bool = False
    schema_version_override: Optional[str] = None

    # -- derived helpers ---------------------------------------------------

    @property
    def effective_hpp_dir(self) -> Path:
        return Path(self.hpp_dir) if self.hpp_dir else Path(self.output_dir)

    @property
    def effective_src_dir(self) -> Path:
        return Path(self.src_dir) if self.src_dir else Path(self.output_dir)

    @property
    def effective_samples_dir(self) -> Path:
        return Path(self.output_dir)

    @property
    def include_header(self) -> str:
        """Header file name to emit in `#include` directives of the source file."""
        return self.hpp_name or ""


# ---------------------------------------------------------------------------
# Provenance stamp for generated files
# ---------------------------------------------------------------------------


@dataclass
class Provenance:
    """Metadata recorded in every generated .hpp/.cpp file.

    Fields:
        schema_version: Human-readable version (from CSV __metadata__ or --schema-version).
        source_csv:     Bare basename of the input CSV.
        csv_md5:        32-char hex MD5 of the CSV's raw bytes.
        generated_at:   ISO-8601 UTC timestamp of the generation run.
        generator:      Name of the generator (CSV generator key or default).
    """

    schema_version: str
    source_csv: str
    csv_md5: str
    generated_at: str
    generator: str


def _provenance_block(prov: Provenance, indent: str = "") -> str:
    """Return a /// comment block recording schema provenance.

    Each line is prefixed with `indent` (used when the block is emitted
    inside an already-indented context; the common case is indent="").
    """
    lines = [
        f"{indent}///",
        f"{indent}/// --- Schema provenance ---",
        f"{indent}///   schema_version : {prov.schema_version}",
        f"{indent}///   source_csv     : {prov.source_csv}",
        f"{indent}///   csv_md5        : {prov.csv_md5}",
        f"{indent}///   generated_at   : {prov.generated_at}",
        f"{indent}///   generator      : {prov.generator}",
        f"{indent}/// -----------------------",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schema model
# ---------------------------------------------------------------------------

@dataclass
class SchemaModel:
    """Parsed CSV schema — groups, fields, containment, root detection."""

    groups: dict[str, list[dict]] = field(default_factory=dict)
    group_regular: dict[str, list[dict]] = field(default_factory=dict)
    group_nested: dict[str, list[tuple[str, str, dict]]] = field(default_factory=dict)
    group_hpp_file: dict[str, str] = field(default_factory=dict)
    has_explicit_hpp_file: bool = False
    root: str = ""
    ordered_groups: list[str] = field(default_factory=list)
    has_optional: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_csv(cls, input_path: str) -> "SchemaModel":
        inpath = Path(input_path)
        if not inpath.exists():
            print(f"Error: input file '{input_path}' not found.", file=sys.stderr)
            sys.exit(1)

        # Read raw lines for traceability comments in generated code.
        with open(inpath, "r", encoding="utf-8") as f:
            raw_lines = [line.rstrip("\n\r") for line in f]

        with open(inpath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            parsed = list(reader)

        # ---- Consume leading __metadata__ rows before the column header ----
        metadata: dict[str, str] = {}
        n_meta: int = 0
        while parsed and parsed[0] and parsed[0][0].strip() == "__metadata__":
            meta_row = parsed.pop(0)
            n_meta += 1
            for cell in meta_row[1:]:
                cell = (cell or "").strip()
                if cell == "":
                    continue
                if "=" not in cell:
                    print(
                        f"Error: malformed __metadata__ pair '{cell}' "
                        f"(expected key=value).",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                k, _, v = cell.partition("=")
                metadata[k.strip()] = v.strip()

        if len(parsed) < 2:
            print("Error: CSV file is empty.", file=sys.stderr)
            sys.exit(1)

        header = [h.strip() for h in parsed[0]]
        missing = {"field_name", "group", "type"} - set(header)
        if missing:
            print(f"Error: CSV missing required columns: {missing}", file=sys.stderr)
            sys.exit(1)

        rows: list[dict] = []
        for i, line in enumerate(parsed[1:], start=2 + n_meta):
            row = dict(zip(header, line))
            row["_csv_line"] = i
            row["_csv_name"] = inpath.name
            row["_csv_raw"] = (
                raw_lines[i - 1] if i - 1 < len(raw_lines) else ",".join(line)
            )
            rows.append(row)

        model = cls()
        model.metadata = metadata
        model._partition_rows(rows)
        model._resolve_hpp_files()
        model._classify_groups()
        model._validate_types()
        model._detect_root()
        model._build_order()
        model._detect_optional()
        return model

    # -- internal helpers --------------------------------------------------

    def _partition_rows(self, rows: list[dict]) -> None:
        for row in rows:
            group = (row.get("group") or "").strip()
            if group == "":
                print(
                    "Error: every row must have a non-empty 'group' value.",
                    file=sys.stderr,
                )
                sys.exit(1)
            self.groups.setdefault(group, []).append(row)

    def _resolve_hpp_files(self) -> None:
        """Extract hpp_file per group and detect CSV-driven mode."""
        for gname, grows in self.groups.items():
            vals = {
                (row.get("hpp_file") or "").strip()
                for row in grows
            }
            vals.discard("")
            if len(vals) > 1:
                print(
                    f"Error: group '{gname}' has conflicting hpp_file values: {vals}",
                    file=sys.stderr,
                )
                sys.exit(1)
            if len(vals) == 1:
                self.group_hpp_file[gname] = vals.pop()
                self.has_explicit_hpp_file = True
            else:
                self.group_hpp_file[gname] = _struct_to_hpp_name(gname)

    def _classify_groups(self) -> None:
        group_names = set(self.groups.keys())
        for gname, grows in self.groups.items():
            regular: list[dict] = []
            nested: list[tuple[str, str, dict]] = []
            for row in grows:
                csv_type = row["type"].strip()
                if csv_type in group_names:
                    nested.append((row["field_name"].strip(), csv_type, row))
                else:
                    regular.append(row)
            self.group_regular[gname] = regular
            self.group_nested[gname] = nested

    def _validate_types(self) -> None:
        """Reject unknown type cells and out-of-range integer literals.

        Runs after _classify_groups, which has already routed any row whose
        type names a *present* group into the nested-member lists.  So every
        regular row's type must be a built-in CSV type — a type cell naming a
        non-existent struct surfaces here as an unknown type.
        """
        for gname in self.ordered_groups_actual():
            for row in self.group_regular[gname]:
                csv_type = row["type"].strip()
                if csv_type not in _BUILTIN_TYPES:
                    print(
                        f"Error: [{row.get('_csv_name','')}:{row.get('_csv_line','')}] "
                        f"field '{row['field_name'].strip()}' has unknown type "
                        f"'{csv_type}'.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                if csv_type in INT_TYPES:
                    self._validate_int_literals(row, csv_type)

    def _validate_int_literals(self, row: dict, csv_type: str) -> None:
        """Reject default/min/max literals that don't fit the integer width."""
        lo, hi = _int_range(csv_type)
        where = f"[{row.get('_csv_name','')}:{row.get('_csv_line','')}]"
        for col in ("default", "min", "max"):
            cell = (row.get(col) or "").strip()
            if not cell:
                continue
            try:
                v = int(cell, 10)
            except ValueError:
                print(
                    f"Error: {where} field '{row['field_name'].strip()}' has "
                    f"non-integer {col} '{cell}' for type '{csv_type}'.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not (lo <= v <= hi):
                print(
                    f"Error: {where} field '{row['field_name'].strip()}' has "
                    f"{col} {v} out of range for type '{csv_type}' "
                    f"[{lo}, {hi}].",
                    file=sys.stderr,
                )
                sys.exit(1)

    def ordered_groups_actual(self) -> list[str]:
        """All groups in insertion order (used before root detection)."""
        return list(self.groups.keys())

    def _detect_root(self) -> None:
        referenced: set[str] = set()
        for nested_list in self.group_nested.values():
            for _, nested_type, _ in nested_list:
                referenced.add(nested_type)
        roots = [g for g in self.groups if g not in referenced]
        if len(roots) == 0:
            print(
                "Error: circular containment detected — no root struct found.",
                file=sys.stderr,
            )
            sys.exit(1)
        if len(roots) > 1:
            print(
                f"Warning: multiple root candidates {roots}; using '{roots[0]}'.",
                file=sys.stderr,
            )
        self.root = roots[0]

    def _build_order(self) -> None:
        non_roots = [g for g in self.groups if g != self.root]
        self.ordered_groups = non_roots + [self.root]

    def _detect_optional(self) -> None:
        for gname in self.ordered_groups:
            for row in self.group_regular[gname]:
                if not (row.get("default") or "").strip():
                    self.has_optional = True
                    return

    def group_has_optional(self, gname: str) -> bool:
        """Check whether a specific group contains any optional fields."""
        for row in self.group_regular.get(gname, []):
            if not (row.get("default") or "").strip():
                return True
        return False

    def hpp_file_for(self, gname: str) -> str:
        """The .hpp filename that contains struct *gname*."""
        return self.group_hpp_file.get(gname, _struct_to_hpp_name(gname))


# ---------------------------------------------------------------------------
# C++ type mapping and value helpers
# ---------------------------------------------------------------------------


# All CSV integer type names.  `int` is kept as a synonym for `int32` so
# existing CSVs regenerate unchanged; integer fields are always emitted as
# fixed-width <stdint.h> typedefs (e.g. int32_t) rather than the
# implementation-defined-width `int`, which matters for portable / MISRA
# automotive code.
INT_TYPES: set[str] = {
    "int", "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
}

# Built-in CSV type cells (excludes struct-name references, which are routed
# to nested-member lists by SchemaModel._classify_groups).
_BUILTIN_TYPES: set[str] = {
    "int", "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "double", "bool", "string",
    "vector<string>", "vector<int>", "vector<double>",
}


def map_type(csv_type: str) -> str:
    """Map CSV type string to C++ type, or pass through if not a built-in."""
    mapping = {
        "int": "int32_t",
        "int8": "int8_t",
        "int16": "int16_t",
        "int32": "int32_t",
        "int64": "int64_t",
        "uint8": "uint8_t",
        "uint16": "uint16_t",
        "uint32": "uint32_t",
        "uint64": "uint64_t",
        "double": "double",
        "bool": "bool",
        "string": "std::string",
        "vector<string>": "std::vector<std::string>",
        "vector<int>": "std::vector<int32_t>",
        "vector<double>": "std::vector<double>",
    }
    return mapping.get(csv_type, csv_type)


# Inclusive (lo, hi) representable range for each fixed-width integer CSV type.
# `int` is treated as int32.  Used to reject out-of-range default/min/max
# literals up front so the generator never emits a literal that would
# narrow-convert.
_INT_RANGES: dict[str, tuple[int, int]] = {
    "int8":   (-128, 127),
    "int16":  (-32768, 32767),
    "int32":  (-2147483648, 2147483647),
    "int64":  (-(2**63), 2**63 - 1),
    "uint8":  (0, 255),
    "uint16": (0, 65535),
    "uint32": (0, 4294967295),
    "uint64": (0, 2**64 - 1),
}


def _int_range(csv_type: str) -> tuple[int, int]:
    """Inclusive representable range for an integer CSV type (`int`==int32)."""
    return _INT_RANGES.get(csv_type, _INT_RANGES["int32"])


def _to_snake_case(camel: str) -> str:
    """Convert CamelCase to snake_case, e.g. AppConfig -> app_config."""
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', camel)
    s = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', s)
    return s.lower()


def _csv_trace_block(row: dict, indent: str = "") -> str:
    """Return a multi-line /* ... */ traceability block for a CSV row.

    Format:
        /*
         * [filename:line]
         *   field_name : value
         *   group      : value
         *   type       : value
         *   default    : value
         *   min        : value
         *   max        : value
         *   description: value
         *   hpp_file   : value      (when present)
         */
    """
    line_no = row.get("_csv_line", "")
    name = row.get("_csv_name", "")
    if not line_no:
        return ""

    columns = ["field_name", "group", "type", "default", "min", "max", "description"]
    if "hpp_file" in row:
        columns.append("hpp_file")

    max_w = max(len(c) for c in columns)

    lines = [f"{indent}/*"]
    lines.append(f"{indent} * [{name}:{line_no}]")
    for col in columns:
        val = (row.get(col) or "").strip()
        lines.append(f"{indent} *   {col:<{max_w}} : {val}")
    lines.append(f"{indent} */")
    return "\n".join(lines)


def _struct_to_hpp_name(struct_name: str) -> str:
    """Derive the .hpp filename for a given struct name."""
    return f"{_to_snake_case(struct_name)}.hpp"


def _struct_to_cpp_name(struct_name: str) -> str:
    """Derive the .cpp filename for a given struct name."""
    return f"{_to_snake_case(struct_name)}.cpp"


def _hpp_to_cpp_name(hpp_name: str) -> str:
    """Derive the .cpp filename from a .hpp filename."""
    return str(Path(hpp_name).with_suffix(".cpp"))


def _derive_filenames(config: GeneratorConfig, struct_name: str) -> tuple[str, str]:
    """Return (hpp_filename, cpp_filename) based on config and struct name.

    In per-struct mode each struct uses auto-derived names.  Otherwise,
    when config.hpp_name is set it acts as the canonical header name;
    the cpp stem is derived by replacing the last extension with .cpp.
    When config.hpp_name is unset, both names are derived from the snake-cased
    struct name.
    """
    if config.per_struct:
        return _struct_to_hpp_name(struct_name), _struct_to_cpp_name(struct_name)
    if config.hpp_name:
        hpp_stem = Path(config.hpp_name)
        cpp_stem = hpp_stem.with_suffix(".cpp")
        return str(hpp_stem), str(cpp_stem)
    snake = _to_snake_case(struct_name)
    return f"{snake}.hpp", f"{snake}.cpp"


def _parse_default(val: str, csv_type: str) -> object:
    val = val.strip()
    if csv_type in INT_TYPES:
        return int(val)
    if csv_type == "double":
        return float(val)
    if csv_type == "bool":
        return val.lower() == "true"
    if csv_type == "string":
        return val.strip('"')
    return val


def _example_value(csv_type: str) -> object:
    if csv_type in INT_TYPES:
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
    if csv_type in INT_TYPES:
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
    if violate and (csv_type in INT_TYPES or csv_type == "double") and (min_val or max_val):
        return _violating_value(min_val, max_val, csv_type)
    if default:
        return _parse_default(default, csv_type)
    return _example_value(csv_type)


# ---------------------------------------------------------------------------
# C++ code generation — header strings
# ---------------------------------------------------------------------------


def _cpp_include(header: str) -> str:
    return f'#include "{header}"' if header else ""


def _make_header_preamble(has_optional: bool,
                          extra_includes: Optional[list[str]] = None,
                          provenance: Optional[Provenance] = None) -> str:
    """Return the full set of #include directives for a header file."""
    inc_opt = "#include <optional>" if has_optional else ""
    extra = "\n".join(f'#include "{inc}"' for inc in (extra_includes or []))
    parts = [
        "#pragma once",
        "",
        "/// Auto-generated config struct from CSV schema.",
        "/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.",
    ]
    if provenance is not None:
        parts.append(_provenance_block(provenance))
    parts.extend([
        "",
        "#include <light_config/light_config.hpp>",
        "#include <cstdint>",
        "#include <string>",
        "#include <vector>",
    ])
    if inc_opt:
        parts.append(inc_opt)
    if extra:
        parts.append(extra)
    return "\n".join(parts)


def escape_default(val: str, cpp_type: str) -> str:
    if val is None or val.strip() == "":
        return ""
    val = val.strip()
    if cpp_type == "std::string":
        return f'"{val}"'
    return val


def _make_struct_body(
    struct_name: str,
    regular_rows: list[dict],
    nested_members: list[tuple[str, str, dict]],
) -> tuple[str, bool]:
    """Generate struct definition body.  Returns (body_string, has_optional)."""
    lines: list[str] = []
    has_optional = False

    for row in regular_rows:
        trace = _csv_trace_block(row, indent="    ")
        if trace:
            lines.append(trace)
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

    for member_name, nested_type, orig_row in nested_members:
        trace = _csv_trace_block(orig_row, indent="    ")
        if trace:
            lines.append(trace)
        lines.append(f"    {nested_type} {member_name};")

    body = "\n".join(lines)
    refl_fields = [r["field_name"].strip() for r in regular_rows]
    refl_fields.extend(m for m, _, _ in nested_members)
    refl_str = ", ".join(refl_fields)

    return f"""struct {struct_name} {{
{body}
}};
YLT_REFL({struct_name}, {refl_str});""", has_optional


def _make_validate_decl(struct_name: str) -> str:
    """Generate a forward declaration for validate_<StructName>()."""
    return f"""/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_{struct_name}(const {struct_name}& cfg);"""


def _make_schema_version_constant(struct_name: str, version: str) -> str:
    """Emit a constexpr schema version constant for the given struct.

    When the CSV has no schema_version metadata, the constant still exists
    but is set to the empty string so callers can always reference it.
    """
    if not version:
        version = ""
    return (
        f"/// Schema version declared in the CSV __metadata__ row.\n"
        f'constexpr std::string_view k{struct_name}SchemaVersion{{"{version}"}};'
    )


# ---------------------------------------------------------------------------
# C++ code generation — source strings
# ---------------------------------------------------------------------------


def _make_source_preamble(include_header: str,
                          provenance: Optional[Provenance] = None) -> str:
    inc = _cpp_include(include_header)
    base = [
        "/// Auto-generated validation implementations from CSV schema.",
        "/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.",
    ]
    if provenance is not None:
        base.append(_provenance_block(provenance))
    if not inc:
        return "\n".join(base) + "\n"
    return "\n".join(base + [
        "",
        inc,
        "",
        "#include <sstream>",
    ])


def _make_validate_impl(
    struct_name: str,
    regular_rows: list[dict],
    nested_members: list[tuple[str, str, dict]],
) -> str:
    """Generate validate_<StructName>() body with range checks and recursion."""
    checks: list[str] = []
    has_validation = False

    for row in regular_rows:
        trace = _csv_trace_block(row, indent="    ")
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
            cond_parts.append(
                f"{field_expr} < {min_val} || {field_expr} > {max_val}"
            )
            msg_parts.append(
                f"\" << {field_expr} << \" out of range [{min_val}, {max_val}]"
            )
        elif min_val:
            cond_parts.append(f"{field_expr} < {min_val}")
            msg_parts.append(
                f"\" << {field_expr} << \" below minimum {min_val}"
            )
        elif max_val:
            cond_parts.append(f"{field_expr} > {max_val}")
            msg_parts.append(
                f"\" << {field_expr} << \" above maximum {max_val}"
            )

        cond_str = " || ".join(cond_parts)
        msg_str = "; ".join(msg_parts)

        check_block = f"""    if ({cond_str}) {{
        std::ostringstream oss;
        oss << "{fname} = {msg_str}";
        errors.push_back(oss.str());
    }}"""

        if trace:
            check_block = f"{trace}\n{check_block}"

        if is_optional:
            check_block = f"""    if (cfg.{fname}.has_value()) {{
{check_block}
    }}"""

        checks.append(check_block)
        has_validation = True

    # Recurse into nested struct members
    for member_name, nested_type, _ in nested_members:
        recurse_block = f"""    {{
        auto r = validate_{nested_type}(cfg.{member_name});
        if (!r.ok()) {{
            errors.push_back("{member_name}: " + r.message);
        }}
    }}"""
        checks.append(recurse_block)
        has_validation = True

    if not has_validation:
        return f"""light_config::LoadResult validate_{struct_name}(
    const {struct_name}& /*cfg*/) {{
    return light_config::LoadResult::success();
}}
"""

    body = "\n".join(checks)
    return f"""light_config::LoadResult validate_{struct_name}(
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
# Code generator
# ---------------------------------------------------------------------------


class CodeGenerator:
    """Orchestrates C++ code generation from a schema model + config."""

    def __init__(self, model: SchemaModel, config: GeneratorConfig,
                 provenance: Provenance) -> None:
        self.model = model
        self.config = config
        self.provenance = provenance
        self._struct_name = config.struct_name or model.root
        # Root filenames (used in monolithic mode only)
        self._root_hpp_name, self._root_cpp_name = _derive_filenames(
            config, self._struct_name
        )
        self._include_header = config.include_header or self._root_hpp_name
        # Resolve namespace: CLI flag > __metadata__ > empty (back-compat)
        self._namespace = (
            config.namespace
            or model.metadata.get("namespace", "")
        )

    # -- namespace helpers --------------------------------------------------

    def _ns_open(self) -> list[str]:
        """Opening lines wrapping generated content in the resolved namespace."""
        if not self._namespace:
            return []
        return ["", f"namespace {self._namespace} {{"]

    def _ns_close(self) -> list[str]:
        """Closing line(s) for the resolved namespace block."""
        if not self._namespace:
            return []
        return [f"}} // namespace {self._namespace}"]

    # -- public API --------------------------------------------------------

    def generate_all(self) -> None:
        """Generate all output files in one shot."""
        if self.model.has_explicit_hpp_file:
            self._generate_csv_driven()
        elif self.config.per_struct:
            self._generate_per_struct()
        else:
            self.generate_header()
            self.generate_source()
        if self.config.generate_samples:
            self.generate_samples()
        n_fields = sum(len(v) for v in self.model.group_regular.values())
        print(
            f"  (root: {self.model.root}, "
            f"{len(self.model.ordered_groups)} struct(s), {n_fields} fields)"
        )

    def generate_header(self) -> Path:
        """Generate the single monolithic header file."""
        outdir = self.config.effective_hpp_dir
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / self._root_hpp_name
        content = self._build_monolithic_header_content()
        path.write_text(content)
        print(f"Generated {path}")
        return path

    def generate_source(self) -> Path:
        """Generate the single monolithic source file."""
        outdir = self.config.effective_src_dir
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / self._root_cpp_name
        content = self._build_monolithic_source_content()
        path.write_text(content)
        print(f"Generated {path}")
        return path

    def generate_samples(self) -> list[Path]:
        outdir = self.config.effective_samples_dir
        outdir.mkdir(parents=True, exist_ok=True)
        valid_data = _build_sample_dict(
            self.model.group_regular,
            self.model.group_nested,
            self.model.root,
            use_default=True,
            violate=False,
        )
        vj = outdir / "valid_config.json"
        vy = outdir / "valid_config.yaml"
        _write_json(valid_data, vj)
        _write_yaml(valid_data, vy)
        print(f"Generated {vj}")
        print(f"Generated {vy}")
        return [vj, vy]

    # -- file group helpers -----------------------------------------------

    def _build_file_groups(self) -> OrderedDict[str, list[str]]:
        """Return {hpp_name: [group_names]} preserving topological order."""
        result: OrderedDict[str, list[str]] = OrderedDict()
        for gname in self.model.ordered_groups:
            hpp_name = self.model.hpp_file_for(gname)
            result.setdefault(hpp_name, []).append(gname)
        return result

    def _cross_file_includes(self, hpp_name: str, groups: list[str]) -> list[str]:
        """Headers from *other* files that groups in this file depend on."""
        includes: set[str] = set()
        for gname in groups:
            for _, nested_type, _ in self.model.group_nested.get(gname, []):
                nested_hpp = self.model.hpp_file_for(nested_type)
                if nested_hpp != hpp_name:
                    includes.add(nested_hpp)
        return sorted(includes)

    # -- CSV-driven generation --------------------------------------------

    def _generate_csv_driven(self) -> None:
        """Generate .hpp/.cpp pairs according to the CSV hpp_file column."""
        hpp_dir = self.config.effective_hpp_dir
        src_dir = self.config.effective_src_dir
        hpp_dir.mkdir(parents=True, exist_ok=True)
        src_dir.mkdir(parents=True, exist_ok=True)

        file_groups = self._build_file_groups()

        for hpp_name, groups in file_groups.items():
            hpp_content = self._build_file_group_header(hpp_name, groups)
            hpp_path = hpp_dir / hpp_name
            hpp_path.write_text(hpp_content)
            print(f"Generated {hpp_path}")

            cpp_name = _hpp_to_cpp_name(hpp_name)
            cpp_content = self._build_file_group_source(hpp_name, groups)
            cpp_path = src_dir / cpp_name
            cpp_path.write_text(cpp_content)
            print(f"Generated {cpp_path}")

    def _build_file_group_header(self, hpp_name: str,
                                 groups: list[str]) -> str:
        """Build the .hpp content for a file group containing one or more structs."""
        extra_includes = self._cross_file_includes(hpp_name, groups)
        has_opt = any(
            self.model.group_has_optional(g) for g in groups
        )

        lines: list[str] = [_make_header_preamble(has_opt, extra_includes,
                                                  self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            body, _ = _make_struct_body(
                struct_name,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(body)
            lines.append("")
        schema_ver = self.model.metadata.get("schema_version", "")
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            lines.append(_make_schema_version_constant(struct_name, schema_ver))
            lines.append("")
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            lines.append(_make_validate_decl(struct_name))
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    def _build_file_group_source(self, hpp_name: str,
                                 groups: list[str]) -> str:
        """Build the .cpp content for a file group."""
        lines: list[str] = [_make_source_preamble(hpp_name, self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            impl = _make_validate_impl(
                struct_name,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(impl)
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    # -- per-struct generation --------------------------------------------

    def _generate_per_struct(self) -> None:
        """Generate one .hpp/.cpp pair per struct group."""
        hpp_dir = self.config.effective_hpp_dir
        src_dir = self.config.effective_src_dir
        hpp_dir.mkdir(parents=True, exist_ok=True)
        src_dir.mkdir(parents=True, exist_ok=True)

        for gname in self.model.ordered_groups:
            is_root = (gname == self.model.root)
            if is_root and self.config.hpp_name:
                hpp_name = self.config.hpp_name
                cpp_name = _hpp_to_cpp_name(hpp_name)
            elif is_root and self.config.struct_name:
                snake = _to_snake_case(self.config.struct_name)
                hpp_name = f"{snake}.hpp"
                cpp_name = f"{snake}.cpp"
            else:
                hpp_name = _struct_to_hpp_name(gname)
                cpp_name = _struct_to_cpp_name(gname)

            hpp_content = self._build_struct_header_content(gname)
            hpp_path = hpp_dir / hpp_name
            hpp_path.write_text(hpp_content)
            print(f"Generated {hpp_path}")

            cpp_content = self._build_struct_source_content(gname, hpp_name)
            cpp_path = src_dir / cpp_name
            cpp_path.write_text(cpp_content)
            print(f"Generated {cpp_path}")

    # -- monolithic content builders --------------------------------------

    def _build_monolithic_header_content(self) -> str:
        lines: list[str] = [
            _make_header_preamble(self.model.has_optional,
                                  provenance=self.provenance)
        ]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in self.model.ordered_groups:
            body, _ = _make_struct_body(
                gname,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(body)
            lines.append("")
        schema_ver = self.model.metadata.get("schema_version", "")
        for gname in self.model.ordered_groups:
            lines.append(_make_schema_version_constant(gname, schema_ver))
            lines.append("")
        for gname in self.model.ordered_groups:
            lines.append(_make_validate_decl(gname))
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    def _build_monolithic_source_content(self) -> str:
        lines: list[str] = [_make_source_preamble(self._include_header,
                                                  self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in self.model.ordered_groups:
            impl = _make_validate_impl(
                gname,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(impl)
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    # -- per-struct content builders --------------------------------------

    def _build_struct_header_content(self, gname: str) -> str:
        """Build the .hpp content for a single struct group."""
        struct_name = self._struct_name if gname == self.model.root else gname
        nested_types = [
            nt for _, nt, _ in self.model.group_nested.get(gname, [])
        ]
        extra_includes = [_struct_to_hpp_name(nt) for nt in nested_types]
        has_opt = self.model.group_has_optional(gname)

        lines: list[str] = [_make_header_preamble(has_opt, extra_includes,
                                                  self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        body, _ = _make_struct_body(
            struct_name,
            self.model.group_regular[gname],
            self.model.group_nested[gname],
        )
        lines.append(body)
        lines.append("")
        schema_ver = self.model.metadata.get("schema_version", "")
        lines.append(_make_schema_version_constant(struct_name, schema_ver))
        lines.append("")
        lines.append(_make_validate_decl(struct_name))
        lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    def _build_struct_source_content(self, gname: str, hpp_name: str) -> str:
        """Build the .cpp content for a single struct group."""
        struct_name = self._struct_name if gname == self.model.root else gname
        lines: list[str] = [_make_source_preamble(hpp_name, self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        impl = _make_validate_impl(
            struct_name,
            self.model.group_regular[gname],
            self.model.group_nested[gname],
        )
        lines.append(impl)
        lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sample config generation helpers (JSON + YAML)
# ---------------------------------------------------------------------------


def _build_sample_dict(
    group_regular: dict[str, list[dict]],
    group_nested: dict[str, list[tuple[str, str, dict]]],
    root: str,
    use_default: bool,
    violate: bool,
) -> dict:
    """Recursively build a nested dict for JSON/YAML output."""

    def _build_for_group(group_name: str) -> dict:
        d: dict[str, object] = {}
        for row in group_regular.get(group_name, []):
            fname = row["field_name"].strip()
            d[fname] = _field_value(
                row, use_default=use_default, violate=violate
            )
        for member_name, nested_type, _ in group_nested.get(group_name, []):
            d[member_name] = _build_for_group(nested_type)
        return d

    return _build_for_group(root)


def _write_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write_yaml(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _build_provenance(
    config: GeneratorConfig,
    model: SchemaModel,
    input_path: str,
) -> Provenance:
    """Resolve schema version, CSV MD5 and timestamp for the stamp."""
    version = (
        config.schema_version_override
        or model.metadata.get("schema_version")
        or "unknown"
    )
    csv_md5 = hashlib.md5(Path(input_path).read_bytes()).hexdigest()
    generated_at = datetime.now(timezone.utc).isoformat()
    generator = model.metadata.get("generator") or "light_config / scripts/gen_config.py"
    return Provenance(
        schema_version=version,
        source_csv=Path(input_path).name,
        csv_md5=csv_md5,
        generated_at=generated_at,
        generator=generator,
    )


def generate(config: GeneratorConfig) -> None:
    model = SchemaModel.from_csv(config.input_csv)
    prov = _build_provenance(config, model, config.input_csv)
    gen = CodeGenerator(model, config, prov)
    gen.generate_all()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate light_config struct + validation code from a CSV schema."
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Path to CSV schema file."
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default="examples/",
        help="Base directory for generated files, used as fallback for "
        "--hpp-dir, --src-dir, and sample files (default: examples/).",
    )
    parser.add_argument(
        "--hpp-dir",
        default=None,
        help="Directory for the generated .hpp file(s). Falls back to --output-dir "
        "when not set.",
    )
    parser.add_argument(
        "--src-dir",
        default=None,
        help="Directory for the generated .cpp file(s). Falls back to --output-dir "
        "when not set.",
    )
    parser.add_argument(
        "--struct-name",
        default="",
        help="Override root struct name for file naming "
        "(default: auto-detected from CSV root group).",
    )
    parser.add_argument(
        "--hpp-name",
        default=None,
        help="Explicit .hpp filename (e.g. 'app_config.hpp').  Only used in "
        "monolithic or --per-struct mode; ignored when CSV hpp_file column "
        "is present.  When set, this name is used for the generated header, "
        "the corresponding .cpp stem, and the #include directive in the source "
        "file.",
    )
    parser.add_argument(
        "--per-struct",
        action="store_true",
        help="Generate one .hpp/.cpp pair per struct group instead of a single "
        "monolithic pair.  Ignored when the CSV carries an hpp_file column.",
    )
    parser.add_argument(
        "--namespace",
        default="",
        help="C++ namespace to wrap all generated structs and validation "
        "functions in (e.g. 'myapp' or 'myapp::net').  Overrides any "
        "__metadata__ namespace= value in the CSV.  Empty or absent = "
        "global scope (back-compat).",
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        help="Emit valid_config.json and valid_config.yaml into --output-dir.",
    )
    parser.add_argument(
        "--schema-version",
        default=None,
        help="Override the schema version recorded in the generated provenance "
        "stamp (default: read from CSV __metadata__ 'schema_version' key, or "
        "'unknown' when absent).",
    )
    args = parser.parse_args()

    config = GeneratorConfig(
        input_csv=args.input,
        output_dir=args.output_dir,
        hpp_dir=args.hpp_dir,
        src_dir=args.src_dir,
        struct_name=args.struct_name,
        hpp_name=args.hpp_name,
        namespace=args.namespace,
        per_struct=args.per_struct,
        generate_samples=args.generate_samples,
        schema_version_override=args.schema_version,
    )
    generate(config)


if __name__ == "__main__":
    main()
