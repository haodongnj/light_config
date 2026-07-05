"""
C++ type mapping, value helpers, CSV row inspection, and filename derivation.
"""

import re
from pathlib import Path

from .config import GeneratorConfig


# ---------------------------------------------------------------------------
# Type tables
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


# ---------------------------------------------------------------------------
# CSV row helpers
# ---------------------------------------------------------------------------


def _is_optional(row: dict) -> bool:
    """Return True when the 'optional' column is truthy."""
    return (row.get("optional") or "").strip().lower() in ("true", "1", "yes")


def _row_location(row: dict) -> str:
    """Return '[filename:line]' for a parsed CSV row, for error messages."""
    name = row.get("_csv_name", "")
    line = row.get("_csv_line", "")
    return f"[{name}:{line}]" if name and line else ""


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

    columns = ["field_name", "group", "type", "default", "min", "max", "optional", "description"]
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


# ---------------------------------------------------------------------------
# Filename derivation
# ---------------------------------------------------------------------------


def _to_snake_case(camel: str) -> str:
    """Convert CamelCase to snake_case, e.g. AppConfig -> app_config."""
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', camel)
    s = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', s)
    return s.lower()


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
    both names are derived from the snake-cased struct name.
    """
    if config.per_struct:
        return _struct_to_hpp_name(struct_name), _struct_to_cpp_name(struct_name)
    snake = _to_snake_case(struct_name)
    return f"{snake}.hpp", f"{snake}.cpp"


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _parse_default(val: str, csv_type: str,
                   enum_names: set[str] | None = None) -> object:
    val = val.strip()
    if csv_type in INT_TYPES:
        return int(val)
    if csv_type == "double":
        return float(val)
    if csv_type == "bool":
        return val.lower() == "true"
    if csv_type == "string":
        return val.strip('"')
    if enum_names and csv_type in enum_names:
        # enum default — return the raw enumerator name for sample generation
        return val
    return val


def _example_value(csv_type: str,
                   enum_registry: dict | None = None) -> object:
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
    if enum_registry and csv_type in enum_registry:
        # Return the first enumerator name
        ed = enum_registry[csv_type]
        return ed.enumerators[0][0] if ed.enumerators else ""
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


def _field_value(row: dict, use_default: bool = True, violate: bool = False,
                 enum_registry: dict | None = None) -> object:
    csv_type = row["type"].strip()
    default = (row.get("default") or "").strip()
    is_opt = _is_optional(row)

    if use_default:
        if default:
            return _parse_default(default, csv_type,
                                  enum_names=set(enum_registry.keys()) if enum_registry else None)
        if is_opt:
            return None
        return _example_value(csv_type, enum_registry=enum_registry)

    min_val = (row.get("min") or "").strip()
    max_val = (row.get("max") or "").strip()
    if violate and (csv_type in INT_TYPES or csv_type == "double") and (min_val or max_val):
        return _violating_value(min_val, max_val, csv_type)
    if default:
        return _parse_default(default, csv_type,
                              enum_names=set(enum_registry.keys()) if enum_registry else None)
    return _example_value(csv_type, enum_registry=enum_registry)
