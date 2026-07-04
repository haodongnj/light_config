"""
C++ code generation — header and source string builders.
"""

from typing import Optional

from .provenance import Provenance, _provenance_block
from .schema import EnumDef
from .types import (
    _csv_trace_block,
    _is_optional,
    _row_location,
    map_type,
)
from .exceptions import GeneratorError


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cpp_include(header: str) -> str:
    return f'#include "{header}"' if header else ""


def _escape_default(val: str, cpp_type: str,
                    enum_names: set[str] | None = None) -> str:
    """Escape a CSV default value to its C++ literal form."""
    if val is None or val.strip() == "":
        return ""
    val = val.strip()
    if cpp_type == "std::string":
        return f'"{val}"'
    if enum_names and cpp_type in enum_names:
        # Qualify enum literal: "info" -> "LogLevel::info"
        return f"{cpp_type}::{val}"
    return val


# ---------------------------------------------------------------------------
# Header builders
# ---------------------------------------------------------------------------


def _make_header_preamble(has_optional: bool,
                          extra_includes: Optional[list[str]] = None,
                          provenance: Optional[Provenance] = None,
                          has_int_types: bool = True,
                          has_enums: bool = False) -> str:
    """Return the full set of #include directives for a header file."""
    inc_opt = "#include <optional>" if has_optional else ""
    inc_cstdint = "#include <cstdint>" if has_int_types else ""
    inc_array = "#include <array>" if has_enums else ""
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
        "#include <string>",
        "#include <vector>",
    ])
    if inc_cstdint:
        parts.append(inc_cstdint)
    if inc_opt:
        parts.append(inc_opt)
    if inc_array:
        parts.append(inc_array)
    if extra:
        parts.append(extra)
    return "\n".join(parts)


def _make_enum_def(ed: EnumDef) -> str:
    """Generate enum class definition (inside namespace).

    The enum_value<T> specialization is emitted separately by
    _make_enum_specialization, outside the user's namespace.
    """
    items = ", ".join(f"{name} = {val}" for name, val in ed.enumerators)
    n = len(ed.enumerators)

    return (
        f"/*\n"
        f" * [{ed.hpp_file}:__enum__ row]\n"
        f" *   enum_name   : {ed.name}\n"
        f" *   enumerators : {n}\n"
        f" *   hpp_file    : {ed.hpp_file}\n"
        f" */\n"
        f"enum class {ed.name} {{ {items} }};"
    )


def _make_enum_specialization(ed: EnumDef, namespace: str = "") -> str:
    """Generate iguana::enum_value<T> specialization (at global/namespace scope).

    When *namespace* is non-empty the enum type is qualified (e.g. app::LogLevel).
    """
    vals = ", ".join(str(val) for _, val in ed.enumerators)
    n = len(ed.enumerators)
    qualified = f"{namespace}::{ed.name}" if namespace else ed.name

    return (
        f"template <>\n"
        f"struct iguana::enum_value<{qualified}> {{\n"
        f"    constexpr static std::array<int, {n}> value = {{{vals}}};\n"
        f"}};"
    )


def _make_struct_body(
    struct_name: str,
    regular_rows: list[dict],
    nested_members: list[tuple[str, str, dict]],
    enum_names: set[str] | None = None,
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
        is_opt = _is_optional(row)
        default_literal = _escape_default(default_cell, cpp_type, enum_names=enum_names)

        desc = (row.get("description") or "").strip()
        if desc:
            lines.append(f"    // {desc}")

        if is_opt:
            if default_cell:
                lines.append(
                    f"    std::optional<{cpp_type}> {fname} = {default_literal};"
                )
            else:
                lines.append(f"    std::optional<{cpp_type}> {fname};")
            has_optional = True
        else:
            if not default_cell:
                where = _row_location(row)
                raise GeneratorError(
                    f"{where} required field '{fname}' must have a default value."
                )
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
    The sentinel "unknown" (from provenance resolution when no version is
    provided) is also normalised to "".
    """
    if not version or version == "unknown":
        version = ""
    return (
        f"/// Schema version declared in the CSV __metadata__ row.\n"
        f'constexpr std::string_view k{struct_name}SchemaVersion{{"{version}"}};'
    )


# ---------------------------------------------------------------------------
# Source builders
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
    enum_names: set[str] | None = None,
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
        csv_type = row["type"].strip()

        # Enum fields: skip range validation (yalantinglibs handles parse-time rejection)
        if enum_names and csv_type in enum_names:
            continue

        if not min_val and not max_val:
            continue

        is_optional = _is_optional(row)
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
