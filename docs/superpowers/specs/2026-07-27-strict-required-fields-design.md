# Strict required-field enforcement design

**Date:** 2026-07-27
**Status:** approved

## Overview

Add an **opt-in** strict mode to the light_config loaders: when enabled, a
non-`std::optional` struct field that is physically absent from the source document
causes the load to return a failure `Result` with `ErrorCode::kMissingRequiredField`
instead of silently leaving the field at its default-constructed value.

The feature is gated behind a `bool require_all = false` parameter on every public
loader. Default-`false` means all existing call sites are unchanged — no breaking
semantic shift, no test update needed.

For JSON, enforcement piggybacks on the existing DOM audit (`audit_json.hpp`), which
already knows per-field whether a key was present. For YAML, which currently has no
DOM (iguana's YAML reader is a direct-to-struct parser), we vendor the rapidyaml
single-header to build a key-presence tree before `from_yaml` runs, achieving format
parity.

## 1. What "required" means

A field is **required** iff its C++ type is **not** `std::optional<T>`. No other
distinction — member-initializer defaults (e.g. `int value = 0;`), nested structs,
and `std::vector<T>` are all required when not wrapped in `std::optional`. The
recursion rules mirror the existing audit's:

| Field type | Required at parent? | Sub-fields enforced? |
|---|---|---|
| `std::optional<T>` | No (absent/null both allowed) | Recurse when present (existing behavior) |
| `T` (non-optional, `YLT_REFL`-annotated) | Yes | Yes — own non-optional subfields are recursively required |
| `std::vector<T>` / `std::array<T,N>` | Yes (key must exist; empty array is present) | Scalar elements: no (the vector field itself is required; element subfields not enforced) |
| `std::vector<YLT_REFL T>` | Yes | Yes — element subfields recursively enforced via `[]` path |
| `std::optional<std::vector<T>>` | No | Recurse when present |
| maps (`std::map`, `std::unordered_map`) | N/A | Maps are not recursed into by the audit, same as today |

When `require_all` is true and the audit finds missing required fields anywhere in
the tree, **all** missing fields are collected in a single pass before returning —
one failure surfaces every gap, not just the first.

## 2. Public API

One `bool require_all = false` appended as the new last parameter on every public
loader (before the `Format` parameter where one already exists):

```cpp
// Core loaders
Result load_from_json_file(T& config, const std::string& path,
                            std::string_view expected_schema_version = "",
                            bool require_all = false);

Result load_from_json_string(T& config, const std::string& json_str,
                              std::string_view expected_schema_version = "",
                              bool require_all = false);

Result load_from_yaml_file(T& config, const std::string& path,
                            std::string_view expected_schema_version = "",
                            bool require_all = false);

Result load_from_yaml_string(T& config, const std::string& yaml_str,
                              std::string_view expected_schema_version = "",
                              bool require_all = false);

// *_and_validate variants — same pattern
Result load_from_json_file_and_validate(T& config, const std::string& path,
                                         Validator&& validator,
                                         std::string_view expected_schema_version = "",
                                         bool require_all = false);
// ... load_from_json_string_and_validate, load_from_yaml_file_and_validate,
//     load_from_yaml_string_and_validate ...

// Convenience loaders in light_config.hpp thread through
Result load(T& config, const std::string& path,
            Format format = Format::Auto, bool require_all = false);

Result load_versioned(T& config, const std::string& path,
                      std::string_view expected_schema_version,
                      Format format = Format::Auto, bool require_all = false);

Result load_and_validate(T& config, const std::string& path,
                          Validator&& validator,
                          Format format = Format::Auto, bool require_all = false);

Result load_versioned_and_validate(T& config, const std::string& path,
                                    std::string_view expected_schema_version,
                                    Validator&& validator,
                                    Format format = Format::Auto, bool require_all = false);
```

Default `false` preserves existing behavior for every call site. When `require_all`
is true and a required field is missing, the load returns:

```cpp
Result{ code = ErrorCode::kMissingRequiredField,
        message = "missing required field(s): name, port at root; host at server" }
```

The `missing_required` vector (see § 3) carries the structured list; `message` gives
a human-readable summary for logging.

**Ordering semantics:** when `require_all` is true, the required-field audit runs
**before** `from_json`/`from_yaml`. If it finds missing required fields, the loader
returns the failure and does **not** populate the output config struct — the
out-parameter is left untouched. This is the correct contract for a failed load and
needs tests asserting it.

When `require_all` is true **and** a validator is supplied (via `load_and_validate`
etc.), the required-field check runs first; a `kMissingRequiredField` supersedes any
validator call. If all required fields are present, the validator runs as usual.

## 3. Error code & Result extension

### New error code

```cpp
// result.hpp — inside enum class ErrorCode, validation range (30–39)
kMissingRequiredField = 32,  ///< A required (non-optional) field was absent
                              ///< from the document when require_all=true.
```

A new `static_assert` pins it in the validation range:

```cpp
static_assert(static_cast<int>(ErrorCode::kMissingRequiredField) < 40,
              "ErrorCode range violation: validation errors must stay in [30, 39]");
```

`error_code_message()` gains a `"missing required field"` arm.

### Result struct addition

```cpp
struct Result {
    // ... existing members unchanged ...

    /// Fields that were required (non-optional, not wrapped in std::optional)
    /// but absent from the source document when require_all was true.
    /// Empty unless code == kMissingRequiredField.  Dot-joined paths
    /// matching the convention of present_fields / absent_optionals
    /// (e.g. "server.host", "items[].name").
    std::vector<std::string> missing_required;
};
```

Populated only when `require_all` is true (for both JSON and YAML; for non-strict
mode the vector is always empty, maintaining parity expectation between formats).

## 4. Mechanism — JSON

The existing audit (`audit_json_recursive` in [detail/audit_json.hpp](include/light_config/detail/audit_json.hpp))
already walks the `iguana::jobject` DOM and knows per-field whether `it == dom.end()`
(key absent in the document). Currently the absent branch only records optional
fields; the change adds the non-optional case:

```cpp
void audit_json_recursive(T& obj, const iguana::jobject& dom,
                          std::vector<std::string>& absent_optionals,
                          std::vector<std::string>& present_fields,
                          std::vector<std::string>& missing_required,  // NEW
                          bool require_all,                            // NEW
                          const std::string& prefix = "") {
    ylt::reflection::for_each(obj, [&](auto& member, std::string_view name, auto) {
        std::string key(name);
        std::string full_name = prefix.empty() ? std::string(name)
                                               : prefix + "." + std::string(name);
        auto it = dom.find(key);
        using field_t = std::decay_t<decltype(member)>;

        if (it == dom.end()) {
            if constexpr (is_optional_v<field_t>) {
                absent_optionals.push_back(full_name);
                member = std::nullopt;
            } else if (require_all) {
                missing_required.push_back(full_name);
            }
            // non-optional, non-strict: unchanged — silent default
        } else {
            present_fields.push_back(full_name);
            // ... existing recursion into nested/optional/vector branches unchanged ...
        }
    });
}
```

The recursion into nested structs, optional sub-structs, and vector elements passes
the same `missing_required` vector and `require_all` flag through — so a single call
collects all missing required fields across the entire tree.

After the audit returns, `load_from_json_file` / `load_from_json_string` check:

```cpp
if (require_all && !result.missing_required.empty()) {
    result.code = ErrorCode::kMissingRequiredField;
    result.message = compose_missing_msg(result.missing_required);
    return result;  // skip from_json; config out-param untouched
}
```

**Key invariant:** the audit already runs on a default-constructed temporary struct
and inspects the DOM — it never populates the caller's config. Returning early leaves
the caller's config in whatever state it was before the call. This is the correct
"failed load" contract and matches the existing `kSchemaMismatch` / `kJsonParseError`
early-returns.

## 5. Mechanism — YAML

Today YAML has no DOM — the existing `audit_yaml_recursive` ([detail/audit_yaml.hpp](include/light_config/detail/audit_yaml.hpp))
runs **after** `from_yaml` and only distinguishes `std::optional` fields by checking
`has_value()`. It cannot tell a missing required field from one populated with its
default value.

For strict-required enforcement we need key-presence information, so we vendor a
YAML DOM library.

### 5.1 Vendored dependency: rapidyaml (single-header, MIT)

Two files dropped into `third_party/rapidyaml/include/`:

| File | Size (approx.) | Purpose |
|---|---|---|
| `ryml_all.hpp` | single-header (~45k lines) | YAML parse/tree API (`Tree`, `NodeRef`, `ConstNodeRef`) |
| `ryml_std.hpp` | single-header (~200 lines) | `std::string` interop glue (`csubstr`, `to_csubstr`) |

**CMake wiring** (mirrors the existing yalantinglibs SYSTEM INTERFACE pattern):

```cmake
# ---- Vendored rapidyaml (third_party/rapidyaml) ----
set(RYML_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/rapidyaml")
target_include_directories(light_config SYSTEM INTERFACE
    ${RYML_DIR}/include
)
```

No separate library target to compile — single-header, no `.cpp` files. The project
remains header-only.

### 5.2 New internal header: `detail/audit_yaml_strict.hpp`

A new audit function mirrors the JSON audit's recursion shape but walks a
`ryml::ConstNodeRef` tree instead of an `iguana::jobject`. Function signature:

```cpp
namespace light_config {
namespace detail {

void audit_yaml_strict(const ryml::ConstNodeRef& root,
                       std::vector<std::string>& missing_required,
                       const std::string& prefix = "");

}  // namespace detail
}  // namespace light_config
```

The walk:
1. Root must be a YAML mapping (`ryml::NodeType::MAP`) — a scalar or sequence root
   means every required top-level field is absent.
2. For each struct member (via `ylt::reflection::for_each`), look up the field name
   in the node's children.
3. Absent + non-optional → `missing_required.push_back(full_name)`.
4. Present → recurse into nested `YLT_REFL` struct nodes, optional sub-structs, and
   vector-of-struct elements (mirroring `audit_json`'s recursion matrix — the full
   same dispatch table as § 4's switch).
5. `ryml::ConstNodeRef` handles flow-style (`{a: 1, b: 2}`) and anchor/alias
   transparently (tree is normalized).

The function is a free template instantiated by `load_from_yaml_file` /
`load_from_yaml_string` only when `require_all` is true (the `ryml` include is
conditional or guarded — see § 5.3).

### 5.3 Loader integration

```cpp
// yaml_loader.hpp — load_from_yaml_file, strict path
if (require_all) {
    ryml::Tree tree = ryml::parse_in_arena(ryml::to_csubstr(content));
    ryml::ConstNodeRef root = tree.rootref();
    detail::audit_yaml_strict<T>(root, result.missing_required);
    if (!result.missing_required.empty()) {
        result.code = ErrorCode::kMissingRequiredField;
        result.message = compose_missing_msg(result.missing_required);
        return result;  // skip from_yaml
    }
}
// ... existing non-strict path (iguana::from_yaml + audit_yaml_recursive) ...
```

`parse_in_arena` gives the tree its own memory independent of the source buffer, so
the tree is self-contained after the call and `content` can be released safely.
(The implementation verifies this during the plan stage — if the vendored rapidyaml
release uses `parse_in_place` semantics, `content` is simply kept alive across the
audit, matching the JSON path.)

### 5.4 YAML behaviors pinned by the spec

Each of these becomes a test case:

- **Explicit `null` vs absent:** A key present with `null` value is **present**
  (rapidyaml reports `"key": <val: null>` as a child of the map). Matches JSON's
  explicit-null-is-present rule exactly. This also means the strict-audit is the
  **first** YAML path in this library that can distinguish absent from explicit
  null for optional fields — but that improvement is not the goal of this feature
  and is kept as a bonus side-effect.
- **Flow-style mappings (`{a: 1, b: 2}`):** Handled transparently by rapidyaml.
  No special-case needed.
- **Anchors/aliases:** Resolved by rapidyaml; keys at the resolved target count as
  present. No special-case needed.
- **Root is scalar/sequence:** A struct-typed root expects a mapping. If the root
  is a scalar or sequence, every required top-level field is missing.
- **Empty document / `kFileEmpty`:** The existing file-empty check runs first;
  empty documents never reach the audit.

## 6. CSV generator integration

Required-field enforcement is a **type-level** property (non-`std::optional` →
required), not an annotation the generator needs to emit. The generator already
decides which fields are `std::optional` (fields without a `default` column); the
strict mode catches absent non-optional fields automatically. **No generator source
changes are required** for the core feature.

**Optional enhancement (deferred):** a `--strict-load` flag on `gen_config.py` that
emits a `require_all = true` wrapper in the generated `main()` snippet, so generated
programs demonstrate strict mode end-to-end. The tests (§ 7) cover this by generating
from a probe CSV and running the strict-load path against the output.

## 7. Testing

### 7.1 New dedicated suite: `tests/test_strict_required.cpp`

A new C++/doctest file covering all entry-point families × both formats:

| Category | Cases |
|---|---|
| **baseline (strict off)** | `require_all=false` is a no-op; existing lenient tests pass unchanged |
| **all-present** | strict mode with full config → `kOk`, `missing_required` empty |
| **single root missing** | one required field omitted → `kMissingRequiredField`, field in `missing_required` |
| **multiple root missing** | N > 1 required fields omitted → all collected in one failure |
| **nested struct** | `server.host` missing → `kMissingRequiredField`, dotted path |
| **deep nesting** | `cluster.middle.leaf.tag` missing → full dot-path |
| **vector present but empty** | `"items": []` with required vector → `kOk` (key present) |
| **required vector missing** | no `items` key → `kMissingRequiredField` |
| **vector\<struct\> element fields** | each element's non-optional subfields enforced via `items[].name` paths |
| **optional\<struct\> wrapper** | outer optional absent → not required; present → inner required fields enforced |
| **optional\<vector\<struct\>\>** | present → element subfields enforced; absent → fine |
| **explicit null on required** | `"name": null` → **present** (null value is a value), `kOk` |
| **config untouched on failure** | caller sets `.name = "before"`, strict load fails → `.name` still `"before"` |
| **load_and_validate strict** | strict + validator compose; strict failure runs before validator |
| **load_from_json/load_versioned threading** | convenience wrappers pass `require_all=true` through to inner loader |

### 7.2 Additions to existing test files

`tests/test_basic.cpp`:
- `load_from_json_string` strict mode basic exercise (root required missing → failure)
- `load_from_json_file` strict, using temp file
- `load_from_yaml_string` / `load_from_yaml_file` strict
- Confirms existing lenient tests still pass unmodified (the non-breaking guarantee)

`tests/test_edge_probes.cpp`:
- YAML explicit-null on a required field is not a miss
- YAML flow-style mapping with required field present
- Anchor/alias with required field via the aliased key
- YAML root scalar/sequence is missing-all

### 7.3 Generator integration probe

A new CSV (`tests/edge_probes/strict_required.csv`) with one required struct field
(no `default` — non-optional) and one optional field:

```csv
field_name,group,type,default,min,max,description
name,AppConfig,string,,,,"required — no default → std::string, not optional"
timeout,AppConfig,int,30,1,300,"optional — has default → std::optional<int>"
```

A new Python script `scripts/test_strict_required_build.py`:
- Runs `gen_config.py` on the CSV → generates C++
- Compiles a small driver calling `load_from_json_file_and_validate(..., require_all=true)`
  with a trimmed config (name omitted)
- Asserts the driver exits with `kMissingRequiredField` / `missing_required` contains "name"
- Also asserts a full config passes

### 7.4 Expected test count

~30–40 new cases across the new file and additions to existing files.

## 8. File change map

| File | Nature | Summary |
|---|---|---|
| `include/light_config/result.hpp` | Edit | + `kMissingRequiredField = 32`, range static_assert, `error_code_message` arm, `missing_required` vector |
| `include/light_config/detail/audit_json.hpp` | Edit | Add `missing_required` vector + `require_all` flag to signature; absent-non-optional branch populates |
| `include/light_config/detail/audit_yaml_strict.hpp` | **New** | rapidyaml-DOM walk matching audit_json's recursion |
| `include/light_config/json_loader.hpp` | Edit | Thread `require_all`; early-return on non-empty `missing_required` |
| `include/light_config/yaml_loader.hpp` | Edit | Thread `require_all`; strict path calls `audit_yaml_strict`, early-returns |
| `include/light_config/light_config.hpp` | Edit | Thread `require_all` through `load`, `load_versioned`, `*_and_validate` |
| `CMakeLists.txt` | Edit | Vendor `third_party/rapidyaml/include` as SYSTEM INTERFACE include |
| `third_party/rapidyaml/include/ryml_all.hpp` | **New** | Vendored single-header (MIT) |
| `third_party/rapidyaml/include/ryml_std.hpp` | **New** | Vendored std::string interop |
| `tests/test_strict_required.cpp` | **New** | Dedicated strict suite |
| `tests/test_basic.cpp` | Edit | Strict-mode basic exercise + lenient non-breaking confirmation |
| `tests/test_edge_probes.cpp` | Edit | YAML DOM-edge cases (null/flow/anchor/root-type) |
| `tests/edge_probes/strict_required.csv` | **New** | Generator probe CSV |
| `scripts/test_strict_required_build.py` | **New** | Generator integration test |
| `CLAUDE.md` | Edit | Document `require_all` flag, `kMissingRequiredField`, rapidyaml dep |

## 9. Non-goals

- **No required-field annotation DSL** — a field is required iff not `std::optional`.
  No additional macro or CSV column.
- **No changes to `audit_yaml_recursive`** — the existing non-strict YAML audit is
  untouched. The strict audit is a separate pass. This avoids regressing the H11
  behaviors documented in the test suite.
- **No change to `absent_optionals` / `present_fields`** — these remain exactly as
  they are today. Only the new `missing_required` vector adds strict-mode data.
- **No per-element required enforcement inside vectors** — a required vector field
  whose element is a struct does enforce the element subfields (mirroring `audit_json`'s
  existing recursion into vector-of-struct elements via `[]` paths), but scalar-element
  vectors do not enforce presence of each element.
