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
    _is_optional,
    _int_range,
    _row_location,
    _struct_to_hpp_name,
    INT_TYPES,
)


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
        missing = {"field_name", "group", "type", "optional"} - set(header)
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
                is_opt = _is_optional(row)
                if csv_type in group_names:
                    if is_opt:
                        where = _row_location(row)
                        print(
                            f"Error: {where} nested struct field "
                            f"'{row['field_name'].strip()}' cannot be optional.",
                            file=sys.stderr,
                        )
                        sys.exit(1)
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
                if _is_optional(row):
                    self.has_optional = True
                    return

    def group_has_optional(self, gname: str) -> bool:
        """Check whether a specific group contains any optional fields."""
        for row in self.group_regular.get(gname, []):
            if _is_optional(row):
                return True
        return False

    def hpp_file_for(self, gname: str) -> str:
        """The .hpp filename that contains struct *gname*."""
        return self.group_hpp_file.get(gname, _struct_to_hpp_name(gname))
