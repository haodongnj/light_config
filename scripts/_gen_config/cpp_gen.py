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


def _cpp_int_literal(val: str, csv_type: str) -> str:
    """Emit a portable C++ integer literal for a CSV default/min/max cell.

    INT64_MIN (-2**63) is the one value that cannot be written as a positive
    decimal literal followed by unary minus: the magnitude (2**63) exceeds
    INT64_MAX, so the compiler interprets the literal as unsigned *before* the
    minus is applied, producing a -Wimplicitly-unsigned-literal diagnostic
    (a hard error under -Werror).  The portable spelling is (INT64_MAX - 1).

    int64/uint64 literals also get an explicit LL/ULL suffix so their type is
    unambiguous on every platform.  Narrower integer types are emitted as-is
    (their values are already range-checked by schema._validate_int_literals).
    """
    if csv_type == "int64":
        if val.lstrip("-") == "9223372036854775808":
            return "(-9223372036854775807LL - 1)"
        return f"{val}LL"
    if csv_type == "uint64":
        return f"{val}ULL"
    return val


def _escape_default(val: str, cpp_type: str,
                    csv_type: str = "",
                    enum_names: set[str] | None = None) -> str:
    """Escape a CSV default value to its C++ literal form."""
    if val is None or val.strip() == "":
        return ""
    val = val.strip()
    if cpp_type == "std::string":
        # Escape backslash first, then the quote, so the emitted literal is
        # valid C++ for any string default (e.g. Windows file paths, strings
        # containing quotes).  Without this, a default of `a"b\c` would emit
        # `"a"b\c"` — a premature string terminator and an invalid escape.
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if enum_names and cpp_type in enum_names:
        # Qualify enum literal: "info" -> "LogLevel::info"
        return f"{cpp_type}::{val}"
    # Fixed-width 64-bit integer literals need the portable spelling (see
    # _cpp_int_literal).  csv_type is passed by the caller; when it is
    # absent we fall back to inferring from cpp_type for back-compat.
    ct = csv_type or ({
        "int64_t": "int64",
        "uint64_t": "uint64",
    }.get(cpp_type, ""))
    if ct in ("int64", "uint64"):
        return _cpp_int_literal(val, ct)
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
    """Generate enum class definition (at file scope or inside its own namespace).

    The enum_value<T> specialization is emitted separately by
    _make_enum_specialization, outside the user's namespace.
    """
    items = ", ".join(f"{name} = {val}" for name, val in ed.enumerators)
    n = len(ed.enumerators)

    trace = (
        f"/*\n"
        f" * [{ed.hpp_file}:__enum__ row]\n"
        f" *   enum_name   : {ed.name}\n"
        f" *   enumerators : {n}\n"
        f" *   hpp_file    : {ed.hpp_file}\n"
    )
    if ed.namespace:
        trace += f" *   namespace   : {ed.namespace}\n"
    trace += f" */\n"
    trace += f"enum class {ed.name} {{ {items} }};"

    if ed.namespace:
        return (
            f"namespace {ed.namespace} {{\n"
            f"{trace}\n"
            f"}} // namespace {ed.namespace}"
        )
    return trace


def _make_enum_specialization(ed: EnumDef, user_namespace: str = "") -> str:
    """Generate iguana::enum_value<T> specialization (at global/namespace scope).

    Uses the enum's own namespace if set, otherwise falls back to *user_namespace*
    (the struct-level namespace from __metadata__).  The specialization is always
    emitted at file scope — it lives outside any enclosing namespace block.
    """
    vals = ", ".join(str(val) for _, val in ed.enumerators)
    n = len(ed.enumerators)
    ns = ed.namespace or user_namespace
    qualified = f"{ns}::{ed.name}" if ns else ed.name

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
        default_literal = _escape_default(
            default_cell, cpp_type, csv_type=ftype_cell, enum_names=enum_names
        )

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
light_config::Result validate_{struct_name}(const {struct_name}& cfg);"""


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

        # Range bounds for 64-bit integer fields must use the same portable
        # literal spelling as defaults (INT64_MIN in particular); otherwise the
        # emitted comparison would trip -Wimplicitly-unsigned-literal.
        min_lit = _cpp_int_literal(min_val, csv_type) if min_val else ""
        max_lit = _cpp_int_literal(max_val, csv_type) if max_val else ""

        cond_parts: list[str] = []
        msg_parts: list[str] = []

        if min_val and max_val:
            cond_parts.append(
                f"{field_expr} < {min_lit} || {field_expr} > {max_lit}"
            )
            msg_parts.append(
                f"\" << {field_expr} << \" out of range [{min_val}, {max_val}]"
            )
        elif min_val:
            cond_parts.append(f"{field_expr} < {min_lit}")
            msg_parts.append(
                f"\" << {field_expr} << \" below minimum {min_val}"
            )
        elif max_val:
            cond_parts.append(f"{field_expr} > {max_lit}")
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
        return f"""light_config::Result validate_{struct_name}(
    const {struct_name}& /*cfg*/) {{
    return light_config::Result::success();
}}
"""

    body = "\n".join(checks)
    return f"""light_config::Result validate_{struct_name}(
    const {struct_name}& cfg) {{
    std::vector<std::string> errors;
{body}
    if (errors.empty()) {{
        return light_config::Result::success();
    }}

    std::ostringstream summary;
    summary << errors.size() << " validation error(s)";
    for (const auto& e : errors) {{
        summary << "\\n  " << e;
    }}
    return light_config::Result::failure(
        light_config::ErrorCode::kValidationError, summary.str());
}}
"""
