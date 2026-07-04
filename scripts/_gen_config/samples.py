"""
Sample config generation — JSON and YAML output.
"""

import json
from pathlib import Path

from .types import _field_value


def _build_sample_dict(
    group_regular: dict[str, list[dict]],
    group_nested: dict[str, list[tuple[str, str, dict]]],
    root: str,
    use_default: bool,
    violate: bool,
    enum_registry: dict | None = None,
) -> dict:
    """Recursively build a nested dict for JSON/YAML output."""

    def _build_for_group(group_name: str) -> dict:
        d: dict[str, object] = {}
        for row in group_regular.get(group_name, []):
            fname = row["field_name"].strip()
            d[fname] = _field_value(
                row, use_default=use_default, violate=violate,
                enum_registry=enum_registry,
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
