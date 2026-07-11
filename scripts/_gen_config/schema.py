"""
CSV schema model — parsing, validation, root detection, ordering.
"""

import csv
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from .types import (
    _BUILTIN_TYPES,
    _VECTOR_TYPES,
    _is_optional,
    _int_range,
    _row_location,
    _struct_to_hpp_name,
    INT_TYPES,
)
from .exceptions import GeneratorError


# iguana's enum_value<T>::value is std::array<int, N>, so every enumerator
# value must fit in a C++ `int`.  Python ints are unbounded, so the parser
# must reject out-of-range values explicitly.
_INT32_MIN = -2147483648
_INT32_MAX = 2147483647


# ---------------------------------------------------------------------------
# Schema model
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Enum definition
# ---------------------------------------------------------------------------


@dataclass
class EnumDef:
    """Parsed enum declaration from a __enum__ metadata row."""

    name: str                       # "LogLevel"
    enumerators: list[tuple[str, int]]  # [("debug",0), ("info",1), ("warn",5)]
    hpp_file: str                   # "network.hpp" — required
    _csv_line: int                  # for error messages
    namespace: str = ""             # optional C++ namespace for this enum


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
    enums: dict[str, EnumDef] = field(default_factory=dict)

    @classmethod
    def from_csv(cls, input_path: str) -> "SchemaModel":
        inpath = Path(input_path)
        if not inpath.exists():
            raise GeneratorError(f"input file '{input_path}' not found.")

        # Read raw lines for traceability comments in generated code.
        with open(inpath, "r", encoding="utf-8") as f:
            raw_lines = [line.rstrip("\n\r") for line in f]

        with open(inpath, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            parsed = list(reader)

        # ---- Consume leading metadata rows before the column header ----
        metadata: dict[str, str] = {}
        enum_rows: list[list[str]] = []
        n_meta: int = 0
        while parsed and parsed[0] and (
            parsed[0][0].strip() == "__metadata__"
            or parsed[0][0].strip() == "__enum__"
        ):
            row = parsed.pop(0)
            row_type = row[0].strip()
            n_meta += 1

            if row_type == "__metadata__":
                for cell in row[1:]:
                    cell = (cell or "").strip()
                    if cell == "":
                        continue
                    if "=" not in cell:
                        raise GeneratorError(
                            f"malformed __metadata__ pair '{cell}' "
                            f"(expected key=value)."
                        )
                    k, _, v = cell.partition("=")
                    metadata[k.strip()] = v.strip()
            elif row_type == "__enum__":
                # Inject the CSV line number for error messages
                row[0] = str(n_meta + 1)
                enum_rows.append(row)

        if len(parsed) < 2:
            raise GeneratorError("CSV file is empty.")

        header = [h.strip() for h in parsed[0]]
        missing = {"field_name", "group", "type", "optional"} - set(header)
        if missing:
            raise GeneratorError(f"CSV missing required columns: {missing}")

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
        model.enums = cls._parse_enum_rows(enum_rows, inpath.name)
        model._partition_rows(rows)
        model._resolve_hpp_files()
        model._classify_groups()
        model._validate_types()
        model._validate_enum_references()
        model._detect_root()
        model._build_order()
        model._detect_optional()
        return model

    @staticmethod
    def _parse_enum_rows(raw_enum_rows: list[list[str]],
                         csv_name: str) -> dict[str, EnumDef]:
        """Parse __enum__ metadata rows; return dict keyed by enum name."""
        result: dict[str, EnumDef] = {}
        for row in raw_enum_rows:
            line_num = int(row[0]) if row[0] else 0
            kv: dict[str, str] = {}
            for cell in row[1:]:
                cell = (cell or "").strip()
                if cell == "":
                    continue
                if "=" not in cell:
                    raise GeneratorError(
                        f"[{csv_name}:{line_num}] malformed __enum__ pair "
                        f"'{cell}' (expected key=value)."
                    )
                k, _, v = cell.partition("=")
                kv[k.strip()] = v.strip()

            # Validate required keys
            enum_name = kv.get("enum_name", "")
            if not enum_name:
                raise GeneratorError(
                    f"[{csv_name}:{line_num}] __enum__ row missing required "
                    f"key 'enum_name'."
                )
            enum_def_str = kv.get("enum_def", "")
            if not enum_def_str:
                raise GeneratorError(
                    f"[{csv_name}:{line_num}] __enum__ row 'enum_name="
                    f"{enum_name}' has empty enum_def."
                )
            hpp_file = kv.get("hpp_file", "")
            if not hpp_file:
                raise GeneratorError(
                    f"[{csv_name}:{line_num}] __enum__ row 'enum_name="
                    f"{enum_name}' missing required key 'hpp_file'."
                )

            # Check for duplicate enum_name
            if enum_name in result:
                first_line = result[enum_name]._csv_line
                raise GeneratorError(
                    f"[{csv_name}:{line_num}] duplicate enum_name "
                    f"'{enum_name}' (first declared at [{csv_name}:"
                    f"{first_line}])."
                )

            # Parse enumerators (pipe-separated)
            enumerators: list[tuple[str, int]] = []
            claimed_ints: set[int] = set()
            entries = [e.strip() for e in enum_def_str.split("|") if e.strip()]
            if not entries:
                raise GeneratorError(
                    f"[{csv_name}:{line_num}] __enum__ row 'enum_name="
                    f"{enum_name}' has empty enum_def."
                )

            # First pass: collect explicit values
            auto_cursor = 0
            for entry in entries:
                if "=" in entry:
                    name, _, val_str = entry.partition("=")
                    name = name.strip()
                    val_str = val_str.strip()
                    if not name:
                        raise GeneratorError(
                            f"[{csv_name}:{line_num}] __enum__ row "
                            f"'enum_name={enum_name}' has empty enumerator "
                            f"name in entry '{entry}'."
                        )
                    try:
                        val = int(val_str, 10)
                    except ValueError:
                        raise GeneratorError(
                            f"[{csv_name}:{line_num}] __enum__ row "
                            f"'enum_name={enum_name}' enumerator '{name}' "
                            f"has non-integer value '{val_str}'."
                        )
                    # iguana's enum_value<T>::value is std::array<int, N>, so
                    # an explicit enumerator value must fit in a C++ `int`.
                    # A value >= 2**31 or < -2**31 would emit a narrowing
                    # error in both the enum definition and the specialization
                    # 
                    if not (_INT32_MIN <= val <= _INT32_MAX):
                        raise GeneratorError(
                            f"[{csv_name}:{line_num}] __enum__ row "
                            f"'enum_name={enum_name}' enumerator '{name}' "
                            f"has value {val} outside the C++ int range "
                            f"[{_INT32_MIN}, {_INT32_MAX}] (iguana stores "
                            f"enum values as int)."
                        )
                    claimed_ints.add(val)

            # Second pass: build list, auto-assign gaps
            seen_names: set[str] = set()
            for entry in entries:
                if "=" in entry:
                    name, _, val_str = entry.partition("=")
                    name = name.strip()
                    val = int(val_str.strip(), 10)
                else:
                    name = entry.strip()
                    # Find next available integer
                    while auto_cursor in claimed_ints:
                        auto_cursor += 1
                    val = auto_cursor
                    claimed_ints.add(val)

                if name in seen_names:
                    raise GeneratorError(
                        f"[{csv_name}:{line_num}] __enum__ row "
                        f"'enum_name={enum_name}' has duplicate enumerator "
                        f"'{name}'."
                    )
                seen_names.add(name)
                enumerators.append((name, val))

            namespace = kv.get("namespace", "")

            result[enum_name] = EnumDef(
                name=enum_name,
                enumerators=enumerators,
                hpp_file=hpp_file,
                namespace=namespace,
                _csv_line=line_num,
            )
        return result

    # -- internal helpers --------------------------------------------------

    def _partition_rows(self, rows: list[dict]) -> None:
        for row in rows:
            group = (row.get("group") or "").strip()
            if group == "":
                raise GeneratorError(
                    "every row must have a non-empty 'group' value."
                )
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
                raise GeneratorError(
                    f"group '{gname}' has conflicting hpp_file values: {vals}"
                )
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
                is_opt = _is_optional(row)
                # Reject type that is both an enum name and a group name
                if csv_type in self.enums and csv_type in group_names:
                    where = _row_location(row)
                    raise GeneratorError(
                        f"{where} type '{csv_type}' is both an enum and "
                        f"a struct group — names must be unique."
                    )
                if csv_type in group_names:
                    if is_opt:
                        where = _row_location(row)
                        raise GeneratorError(
                            f"{where} nested struct field "
                            f"'{row['field_name'].strip()}' cannot be optional."
                        )
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
                if csv_type not in _BUILTIN_TYPES and csv_type not in self.enums:
                    raise GeneratorError(
                        f"[{row.get('_csv_name','')}:{row.get('_csv_line','')}] "
                        f"field '{row['field_name'].strip()}' has unknown type "
                        f"'{csv_type}'."
                    )

                if csv_type in INT_TYPES:
                    self._validate_int_literals(row, csv_type)

                # Reject non-empty defaults on vector<*> fields.  The
                # generator has no C++ initializer syntax for vector literals
                # today — a non-empty default would be emitted verbatim and
                # produce non-compiling code (e.g. `std::vector<int> v = 1,2,3;`
                # or `= ["a","b"];`).  An empty/absent default is fine.
                if csv_type in _VECTOR_TYPES:
                    default = (row.get("default") or "").strip()
                    if default:
                        where = _row_location(row)
                        field = row["field_name"].strip()
                        raise GeneratorError(
                            f"{where} field '{field}' has a non-empty default "
                            f"'{default}' on vector type '{csv_type}' — vector "
                            f"defaults are not supported (leave the cell empty)."
                        )

                # Reject min/max on types where a C++ ordering comparison is
                # either meaningless or non-compiling:
                #   - enum   (original guard): range constraints on enums
                #     have no meaning; yalantinglibs rejects bad enumerators.
                #   - string: `cfg.s < 5` is `std::string` vs `int` —
                #     no implicit conversion → compile error.
                #   - bool: compiles but is semantically meaningless
                #     (bool promoted to int).
                #   - vector<*>: `cfg.v < 1` is `std::vector` vs `int` →
                #     compile error.  A length/size constraint would need its
                #     own codegen.
                is_unconstrainable = (
                    csv_type in self.enums
                    or csv_type == "string"
                    or csv_type == "bool"
                    or csv_type in _VECTOR_TYPES
                )
                if is_unconstrainable:
                    for col in ("min", "max"):
                        if (row.get(col) or "").strip():
                            where = _row_location(row)
                            field = row["field_name"].strip()
                            kind = "enum" if csv_type in self.enums else csv_type
                            raise GeneratorError(
                                f"{where} field '{field}' "
                                f"has '{col}' constraint on {kind} type "
                                f"'{csv_type}' — min/max are not supported on "
                                f"this type."
                            )
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
                raise GeneratorError(
                    f"{where} field '{row['field_name'].strip()}' has "
                    f"non-integer {col} '{cell}' for type '{csv_type}'."
                )
            if not (lo <= v <= hi):
                raise GeneratorError(
                    f"{where} field '{row['field_name'].strip()}' has "
                    f"{col} {v} out of range for type '{csv_type}' "
                    f"[{lo}, {hi}]."
                )

    def _validate_enum_references(self) -> None:
        """Ensure every enum referenced by a field exists in self.enums,
        and that enum defaults are valid enumerator names."""
        for gname in self.ordered_groups_actual():
            for row in self.group_regular[gname]:
                csv_type = row["type"].strip()
                if csv_type not in self.enums:
                    continue
                ed = self.enums[csv_type]
                default = (row.get("default") or "").strip()
                if default:
                    enames = {name for name, _ in ed.enumerators}
                    if default not in enames:
                        where = _row_location(row)
                        raise GeneratorError(
                            f"{where} field '{row['field_name'].strip()}' "
                            f"default '{default}' is not a valid enumerator "
                            f"of '{csv_type}' (valid: "
                            f"{', '.join(sorted(enames))})."
                        )

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
            raise GeneratorError(
                "circular containment detected — no root struct found."
            )
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
                if _is_optional(row):
                    self.has_optional = True
                    return

    @property
    def has_int_types(self) -> bool:
        """True when any group contains at least one integer-type field."""
        for gname in self.ordered_groups:
            if self.group_has_int_types(gname):
                return True
        return False

    def group_has_optional(self, gname: str) -> bool:
        """Check whether a specific group contains any optional fields."""
        for row in self.group_regular.get(gname, []):
            if _is_optional(row):
                return True
        return False

    def group_has_int_types(self, gname: str) -> bool:
        """Check whether a specific group contains any integer-type fields."""
        for row in self.group_regular.get(gname, []):
            csv_type = row["type"].strip()
            if csv_type in INT_TYPES:
                return True
        return False

    def hpp_file_for(self, gname: str) -> str:
        """The .hpp filename that contains struct *gname*."""
        return self.group_hpp_file.get(gname, _struct_to_hpp_name(gname))
