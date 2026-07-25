"""
C++ type mapping, value helpers, CSV row inspection, and filename derivation.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from .config import GeneratorConfig


# ---------------------------------------------------------------------------
# Type descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CsvTypeInfo:
    """Describes one known CSV type cell and its C++ mapping.

    Every scalar type (int, double, bool, string) has one instance.
    Vector types (``vector<string>``, ``vector<vector<int>>``) are auto-derived
    from their scalar element types — they reference the element's
    ``CsvTypeInfo`` via ``element_type``.
    """

    csv_name: str                       # e.g. "int32", "vector<string>"
    cpp_name: str                       # e.g. "int32_t", "std::vector<std::string>"
    is_integer: bool = False
    is_floating: bool = False
    is_bool: bool = False
    is_string: bool = False
    is_vector: bool = False
    element_type: "CsvTypeInfo | None" = None   # element type for vector<…>
    int_range: tuple[int, int] | None = None     # (lo, hi) inclusive; only for integers

    # -- derived properties ---------------------------------------------------

    @property
    def is_numeric(self) -> bool:
        """True for types that support <, > comparisons (int and double)."""
        return self.is_integer or self.is_floating

    # -- value helpers (methods so logic lives next to the type data) --------

    def parse_default(self, val: str) -> object:
        """Parse a CSV default cell into a Python value for this type."""
        if self.is_integer:
            return int(val)
        if self.is_floating:
            return float(val)
        if self.is_bool:
            return val.lower() == "true"
        if self.is_string:
            return val.strip('"')
        return val

    def example_value(self) -> object:
        """Return a representative default / sample value for this type."""
        if self.is_integer:
            return 0
        if self.is_floating:
            return 0.0
        if self.is_bool:
            return False
        if self.is_string:
            return ""
        if self.is_vector:
            inner = self.element_type.example_value() if self.element_type else ""
            return [inner, inner]
        return ""

    def violating_value(self, min_val: str, max_val: str) -> object:
        """Return a value deliberately outside [min_val, max_val] for testing."""
        if self.is_integer:
            if max_val:
                return int(max_val) + 1
            return int(min_val) - 1
        if self.is_floating:
            if max_val:
                return float(max_val) + 1.0
            return float(min_val) - 1.0
        return 0


# ---------------------------------------------------------------------------
# Type registry — the single source of truth for all known CSV→C++ types
# ---------------------------------------------------------------------------


def _build_type_registry() -> dict[str, CsvTypeInfo]:
    """Build the complete type registry.

    Starts from scalar primitives and auto-derives ``vector<T>`` and
    ``vector<vector<T>>`` variants so they never need to be listed by hand.
    """

    # fmt: off
    _INT_RANGE_DEFS: dict[str, tuple[int, int]] = {
        "int8":   (-128, 127),
        "int16":  (-32768, 32767),
        "int32":  (-2147483648, 2147483647),
        "int64":  (-(2**63), 2**63 - 1),
        "uint8":  (0, 255),
        "uint16": (0, 65535),
        "uint32": (0, 4294967295),
        "uint64": (0, 2**64 - 1),
    }
    # fmt: on

    _SCALAR_TYPES: list[CsvTypeInfo] = [
        # -- signed integers --------------------------------------------------
        CsvTypeInfo("int",     "int32_t",  is_integer=True,
                    int_range=_INT_RANGE_DEFS["int32"]),
        CsvTypeInfo("int8",    "int8_t",   is_integer=True,
                    int_range=_INT_RANGE_DEFS["int8"]),
        CsvTypeInfo("int16",   "int16_t",  is_integer=True,
                    int_range=_INT_RANGE_DEFS["int16"]),
        CsvTypeInfo("int32",   "int32_t",  is_integer=True,
                    int_range=_INT_RANGE_DEFS["int32"]),
        CsvTypeInfo("int64",   "int64_t",  is_integer=True,
                    int_range=_INT_RANGE_DEFS["int64"]),
        # -- unsigned integers ------------------------------------------------
        CsvTypeInfo("uint8",   "uint8_t",  is_integer=True,
                    int_range=_INT_RANGE_DEFS["uint8"]),
        CsvTypeInfo("uint16",  "uint16_t", is_integer=True,
                    int_range=_INT_RANGE_DEFS["uint16"]),
        CsvTypeInfo("uint32",  "uint32_t", is_integer=True,
                    int_range=_INT_RANGE_DEFS["uint32"]),
        CsvTypeInfo("uint64",  "uint64_t", is_integer=True,
                    int_range=_INT_RANGE_DEFS["uint64"]),
        # -- other scalars ----------------------------------------------------
        CsvTypeInfo("double",  "double",        is_floating=True),
        CsvTypeInfo("bool",    "bool",        is_bool=True),
        CsvTypeInfo("string",  "std::string", is_string=True),
    ]

    registry: dict[str, CsvTypeInfo] = {}
    for scalar in _SCALAR_TYPES:
        registry[scalar.csv_name] = scalar
        # vector<T>
        vec = CsvTypeInfo(
            f"vector<{scalar.csv_name}>",
            f"std::vector<{scalar.cpp_name}>",
            is_vector=True,
            element_type=scalar,
        )
        registry[vec.csv_name] = vec
        # vector<vector<T>>
        nested = CsvTypeInfo(
            f"vector<vector<{scalar.csv_name}>>",
            f"std::vector<std::vector<{scalar.cpp_name}>>",
            is_vector=True,
            element_type=vec,
        )
        registry[nested.csv_name] = nested

    return registry


_TYPE_REGISTRY: dict[str, CsvTypeInfo] = _build_type_registry()


# ---------------------------------------------------------------------------
# Derived type sets (backward-compatible with code that does ``in`` checks)
# ---------------------------------------------------------------------------

# All CSV integer type names.  `int` is kept as a synonym for `int32` so
# existing CSVs regenerate unchanged; integer fields are always emitted as
# fixed-width <stdint.h> typedefs (e.g. int32_t) rather than the
# implementation-defined-width `int`, which matters for portable / MISRA
# automotive code.
INT_TYPES: set[str] = {
    ti.csv_name for ti in _TYPE_REGISTRY.values() if ti.is_integer
}


# ---------------------------------------------------------------------------
# Public mapping helpers (delegate to _TYPE_REGISTRY)
# ---------------------------------------------------------------------------


def map_type(csv_type: str) -> str:
    """Map CSV type string to C++ type, or pass through if not a known terminal type.

    Struct/enum names are passed through unchanged so they serve as their own
    C++ type names in generated code.
    """
    ti = _TYPE_REGISTRY.get(csv_type)
    return ti.cpp_name if ti is not None else csv_type


def _int_range(csv_type: str) -> tuple[int, int]:
    """Inclusive representable range for an integer CSV type (``int`` → int32)."""
    ti = _TYPE_REGISTRY.get(csv_type)
    if ti is not None and ti.int_range is not None:
        return ti.int_range
    # Fallback: treat unknown types as int32 (backward compat).
    fallback = _TYPE_REGISTRY["int32"]
    assert fallback.int_range is not None
    return fallback.int_range


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
    """Parse a CSV default cell into a Python value.

    Enum defaults are returned as the raw enumerator name (unparsed).
    All other known types delegate to :class:`CsvTypeInfo.parse_default`.
    """
    val = val.strip()
    if enum_names and csv_type in enum_names:
        # enum default — return the raw enumerator name for sample generation
        return val
    ti = _TYPE_REGISTRY.get(csv_type)
    if ti is not None:
        return ti.parse_default(val)
    return val


def _example_value(csv_type: str,
                   enum_registry: dict | None = None) -> object:
    """Return a representative default / sample value for *csv_type*.

    Enum types return the first enumerator name.  Known terminal types
    delegate to :class:`CsvTypeInfo.example_value`.
    """
    if enum_registry and csv_type in enum_registry:
        # Return the first enumerator name
        ed = enum_registry[csv_type]
        return ed.enumerators[0][0] if ed.enumerators else ""
    ti = _TYPE_REGISTRY.get(csv_type)
    if ti is not None:
        return ti.example_value()
    return ""


def _violating_value(min_val: str, max_val: str, csv_type: str) -> object:
    """Return a value deliberately outside [*min_val*, *max_val*] for testing."""
    ti = _TYPE_REGISTRY.get(csv_type)
    if ti is not None:
        return ti.violating_value(min_val, max_val)
    return 0


def _field_value(row: dict, use_default: bool = True, violate: bool = False,
                 enum_registry: dict | None = None) -> object:
    """Resolve the Python value for a CSV field row.

    Used by the sample-file generator to produce JSON/YAML output.
    """
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
    ti = _TYPE_REGISTRY.get(csv_type)
    if violate and ti is not None and ti.is_numeric and (min_val or max_val):
        return _violating_value(min_val, max_val, csv_type)
    if default:
        return _parse_default(default, csv_type,
                              enum_names=set(enum_registry.keys()) if enum_registry else None)
    return _example_value(csv_type, enum_registry=enum_registry)
