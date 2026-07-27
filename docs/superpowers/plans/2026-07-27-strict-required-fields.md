# Strict Required-Field Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in `bool require_all = false` to all loaders — when enabled, absent non-`std::optional` fields return `kMissingRequiredField` instead of silently default-constructing.

**Architecture:** For JSON, the existing DOM audit (`audit_json_recursive`) gains a `missing_required` + `require_all` branch. For YAML, a new rapidyaml-DOM audit (`audit_yaml_strict.hpp`) mirrors the JSON audit's recursion shape. A single `Result::missing_required` vector + `kMissingRequiredField = 32` error code carries the structured result. Default-false on every entry point keeps all existing call sites unchanged.

**Tech Stack:** C++17, yalantinglibs 0.6.1 (`YLT_REFL`, `for_each`, `iguana::jobject`), rapidyaml single-header (MIT), doctest.

## Global Constraints

- Library remains header-only — no compiled `.cpp` or library linking needed beyond `light_config` INTERFACE target
- No breaking changes — `require_all` defaults to `false` everywhere, existing tests pass unmodified
- No exceptions thrown from any `load*` function; all errors are `Result`
- Error code `kMissingRequiredField = 32` stays within the validation range [30, 39], guarded by `static_assert`
- Vendored rapidyaml is added as a SYSTEM INTERFACE include following the existing yalantinglibs pattern in `CMakeLists.txt`
- All new code is clang-formatted (Google-based, 4-space indent, 100 cols)
- Generated files (`examples/app_config.*`, `examples/network.*`) are never hand-edited

---

### Task 1: Vendor rapidyaml single-header + CMake wiring

**Files:**
- Create: `third_party/rapidyaml/include/ryml_all.hpp`
- Create: `third_party/rapidyaml/include/ryml_std.hpp`
- Modify: `CMakeLists.txt:46-61`

**Interfaces:**
- Produces: SYSTEM INTERFACE includes on `light_config` target at `${RYML_DIR}/include`

- [ ] **Step 1: Download rapidyaml single-header files**

```bash
export HTTP_PROXY=http://192.168.31.157:7890
export HTTPS_PROXY=http://192.168.31.157:7890
export http_proxy=http://192.168.31.157:7890
export https_proxy=http://192.168.31.157:7890

RYML_VERSION="0.7.2"
RYML_URL="https://github.com/biojppm/rapidyaml/releases/download/v${RYML_VERSION}/rapidyaml-${RYML_VERSION}-src.zip"
TEMP_DIR=$(mktemp -d)
curl -sL "$RYML_URL" -o "$TEMP_DIR/ryml.zip"
unzip -q "$TEMP_DIR/ryml.zip" -d "$TEMP_DIR"

mkdir -p third_party/rapidyaml/include
cp "$TEMP_DIR/rapidyaml-"*"/src/c4/yml/ryml_all.hpp" third_party/rapidyaml/include/
cp "$TEMP_DIR/rapidyaml-"*"/ext/c4core/src/c4/ext/std/ryml_std.hpp" third_party/rapidyaml/include/

rm -rf "$TEMP_DIR"
wc -l third_party/rapidyaml/include/ryml_all.hpp
wc -l third_party/rapidyaml/include/ryml_std.hpp
```

- [ ] **Step 2: Wire into CMake**

Edit `CMakeLists.txt`. After the yalantinglibs wiring block (~line 60), add:

```cmake
# ---- Vendored rapidyaml (third_party/rapidyaml) ----
set(RYML_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/rapidyaml")
target_include_directories(light_config SYSTEM INTERFACE
    ${RYML_DIR}/include
)
```

- [ ] **Step 3: Verify rapidyaml smoke test compiles & runs**

```bash
cat > /tmp/ryml_smoke.cpp << 'EOF'
#include <ryml_all.hpp>
#include <ryml_std.hpp>
#include <iostream>
#include <string>

int main() {
    std::string yaml =
        "name: test\n"
        "value: 42\n"
        "inner:\n"
        "  host: 10.0.0.1\n"
        "  port: 8080\n";
    ryml::Tree tree = ryml::parse_in_arena(ryml::to_csubstr(yaml));
    ryml::ConstNodeRef root = tree.rootref();
    if (!root.is_map()) { std::cerr << "FAIL: root not map\n"; return 1; }

    // find_child on a map returns the key-node index; value is at idx+1
    size_t name_idx = root.find_child(ryml::to_csubstr("name"));
    if (name_idx == ryml::NONE) { std::cerr << "FAIL: name not found\n"; return 1; }
    ryml::ConstNodeRef name_val = root[name_idx + 1];
    if (name_val.val() != "test") { std::cerr << "FAIL: wrong value\n"; return 1; }

    // Missing key returns NONE
    size_t nope = root.find_child(ryml::to_csubstr("nope"));
    if (nope != ryml::NONE) { std::cerr << "FAIL: nope should be NONE\n"; return 1; }

    // Nested map: inner -> host
    size_t inner_idx = root.find_child(ryml::to_csubstr("inner"));
    ryml::ConstNodeRef inner_val = root[inner_idx + 1];
    if (!inner_val.is_map()) { std::cerr << "FAIL: inner not map\n"; return 1; }
    size_t host_idx = inner_val.find_child(ryml::to_csubstr("host"));
    ryml::ConstNodeRef host_val = inner_val[host_idx + 1];
    if (host_val.val() != "10.0.0.1") { std::cerr << "FAIL: wrong host\n"; return 1; }

    // Explicit null is present (find_child succeeds)
    std::string ynull = "key1: val\nkey2: null\n";
    ryml::Tree t2 = ryml::parse_in_arena(ryml::to_csubstr(ynull));
    size_t k2 = t2.rootref().find_child(ryml::to_csubstr("key2"));
    if (k2 == ryml::NONE) { std::cerr << "FAIL: null key2 not present\n"; return 1; }

    // Root sequence is not a map
    std::string yseq = "- a\n- b\n";
    ryml::Tree t3 = ryml::parse_in_arena(ryml::to_csubstr(yseq));
    if (t3.rootref().is_map()) { std::cerr << "FAIL: seq should not be map\n"; return 1; }

    std::cout << "OK\n";
    return 0;
}
EOF

clang++ -std=c++17 -isystem third_party/rapidyaml/include /tmp/ryml_smoke.cpp -o /tmp/ryml_smoke
/tmp/ryml_smoke
```

Expected output: `OK`

- [ ] **Step 4: Confirm existing tests still pass**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
cd build && ctest --output-on-failure
```

- [ ] **Step 5: Commit**

```bash
git add third_party/rapidyaml/ CMakeLists.txt
git commit -m "build: vendor rapidyaml 0.7.2 single-header for YAML key-presence audit

rapidyaml (MIT) provides a YAML DOM tree used by the forthcoming
strict-mode required-field enforcement to detect which keys are
physically present in the source document.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Add `kMissingRequiredField` error code + `Result::missing_required`

**Files:**
- Modify: `include/light_config/result.hpp`

**Interfaces:**
- Produces: `ErrorCode::kMissingRequiredField = 32`, `error_code_message()` arm, range `static_assert`, `Result::missing_required`, `compose_missing_msg()`

- [ ] **Step 1: Add the new error code**

In `result.hpp`, inside `enum class ErrorCode`, after `kSchemaMismatch = 31,` add:

```cpp
    kMissingRequiredField = 32,  ///< A required (non-optional) field was absent
                                  ///< from the document when require_all=true.
```

- [ ] **Step 2: Add range static_assert**

After the last existing `static_assert` (the `kUnrecognizedFormat < 50` one), insert:

```cpp
static_assert(static_cast<int>(ErrorCode::kMissingRequiredField) < 40,
              "ErrorCode range violation: validation/schema errors must stay in [30, 39]");
```

- [ ] **Step 3: Add error_code_message arm**

In `error_code_message()`, after the `kSchemaMismatch` case:

```cpp
        case ErrorCode::kMissingRequiredField:
            return "missing required field";
```

- [ ] **Step 4: Add `missing_required` vector and helper to `Result`**

Inside `struct Result`, after the `present_fields` member, add:

```cpp
    /// Fields that were required (non-optional, not wrapped in std::optional)
    /// but absent from the source document when require_all was true.
    /// Empty unless code == kMissingRequiredField. Dot-joined paths
    /// (e.g. "server.host", "items[].name").
    std::vector<std::string> missing_required;
```

Before the closing `}  // namespace light_config`, add:

```cpp
/// Compose a human-readable message from a list of missing required field paths.
inline std::string compose_missing_msg(const std::vector<std::string>& missing) {
    std::string msg = "missing required field(s): ";
    for (size_t i = 0; i < missing.size(); ++i) {
        if (i > 0) msg += ", ";
        msg += missing[i];
    }
    return msg;
}
```

- [ ] **Step 5: Build & verify**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
cd build && ctest --output-on-failure
```

- [ ] **Step 6: Commit**

```bash
git add include/light_config/result.hpp
git commit -m "feat: add kMissingRequiredField error code and Result::missing_required

Add ErrorCode::kMissingRequiredField = 32 in validation range [30,39],
error_code_message arm, range static_assert, Result::missing_required
vector, and compose_missing_msg helper.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Extend `audit_json_recursive` for strict required tracking

**Files:**
- Modify: `include/light_config/detail/audit_json.hpp`

**Interfaces:**
- Produces: `audit_json_recursive(T&, dom, absent_optionals, present_fields, missing_required, require_all, prefix)`

- [ ] **Step 1: Add parameters to signature**

In `audit_json.hpp`, change the function signature (line 17-20) from:

```cpp
template <typename T>
void audit_json_recursive(T& obj, const iguana::jobject& dom,
                          std::vector<std::string>& absent_optionals,
                          std::vector<std::string>& present_fields,
                          const std::string& prefix = "") {
```

to:

```cpp
template <typename T>
void audit_json_recursive(T& obj, const iguana::jobject& dom,
                          std::vector<std::string>& absent_optionals,
                          std::vector<std::string>& present_fields,
                          std::vector<std::string>& missing_required,
                          bool require_all,
                          const std::string& prefix = "") {
```

- [ ] **Step 2: Add required-field branch in absent-key handler**

The absent-key branch (lines 29-33) is:

```cpp
        if (it == dom.end()) {
            if constexpr (is_optional_v<field_t>) {
                absent_optionals.push_back(full_name);
                member = std::nullopt;
            }
```

Replace with:

```cpp
        if (it == dom.end()) {
            if constexpr (is_optional_v<field_t>) {
                absent_optionals.push_back(full_name);
                member = std::nullopt;
            } else if (require_all) {
                missing_required.push_back(full_name);
            }
            // non-optional, non-strict: unchanged — silent default
```

- [ ] **Step 3: Thread through all four recursive calls**

Each recursive `audit_json_recursive(...)` call needs `missing_required, require_all,` inserted after the `present_fields,` argument. Four call sites:
- Nested struct recursion (~line 42-43): add the two args
- Optional sub-struct recursion (~line 55-56): add the two args
- Optional-vector element recursion (~line 76-77): add the two args
- Vector-of-struct element recursion (~line 99-101): add the two args

- [ ] **Step 4: Build & verify**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
cd build && ctest --output-on-failure
```

- [ ] **Step 5: Commit**

```bash
git add include/light_config/detail/audit_json.hpp
git commit -m "feat: extend audit_json_recursive with strict required-field tracking

Add missing_required vector and require_all bool to the signature.
When require_all is true and a non-optional field key is absent from
the JSON DOM, the field path is recorded. All recursive call sites threaded.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Create `audit_yaml_strict.hpp` — rapidyaml-based YAML key-presence audit

**Files:**
- Create: `include/light_config/detail/audit_yaml_strict.hpp`

**Interfaces:**
- Produces: `audit_yaml_strict<T>(node, missing_required, require_all, prefix)` — mirrors `audit_json_recursive`'s recursion matrix on `ryml::ConstNodeRef`

- [ ] **Step 1: Write the header**

Create `include/light_config/detail/audit_yaml_strict.hpp`:

```cpp
#pragma once

#include <ryml_all.hpp>
#include <ryml_std.hpp>

#include <ylt/reflection/user_reflect_macro.hpp>

#include <string>
#include <vector>

#include "light_config/result.hpp"

namespace light_config {
namespace detail {

/// Recursively audit required fields against a YAML DOM (rapidyaml tree node).
///
/// Mirrors audit_json_recursive's shape exactly — same recursion dispatch
/// on optional / vector / nested-struct — but walks ryml::ConstNodeRef
/// instead of iguana::jobject.
///
/// ryml map children alternate key,val pairs: find_child(name) returns the
/// key-node index; the value is at index+1.
///
/// \tparam T  A struct annotated with YLT_REFL.
template <typename T>
void audit_yaml_strict(const ryml::ConstNodeRef& node,
                       std::vector<std::string>& missing_required,
                       bool require_all,
                       const std::string& prefix = "") {
    if (!require_all) return;

    // If the current node is not a map, every non-optional field of T is absent.
    if (!node.is_map()) {
        T obj{};
        ylt::reflection::for_each(obj, [&](auto& member, std::string_view name, auto) {
            using field_t = std::decay_t<decltype(member)>;
            if constexpr (!is_optional_v<field_t>) {
                std::string full_name =
                    prefix.empty() ? std::string(name) : prefix + "." + std::string(name);
                missing_required.push_back(full_name);
            }
        });
        return;
    }

    T obj{};
    ylt::reflection::for_each(obj, [&](auto& member, std::string_view name, auto /*index*/) {
        std::string full_name =
            prefix.empty() ? std::string(name) : prefix + "." + std::string(name);

        using field_t = std::decay_t<decltype(member)>;

        ryml::csubstr key_cs = ryml::to_csubstr(std::string(name));
        size_t child_idx = node.find_child(key_cs);

        if (child_idx == ryml::NONE) {
            // Key absent from YAML document
            if constexpr (!is_optional_v<field_t>) {
                missing_required.push_back(full_name);
            }
        } else {
            // Key present — recurse via value node (key at child_idx, val at +1)
            ryml::ConstNodeRef value_node = node[child_idx + 1];

            // (a) Non-optional YLT_REFL struct
            if constexpr (ylt::reflection::is_ylt_refl_v<field_t>) {
                audit_yaml_strict<field_t>(value_node, missing_required,
                                            require_all, full_name);
            }
            // (b) optional<YLT_REFL T>
            else if constexpr (is_optional_v<field_t>) {
                using inner_t = typename field_t::value_type;
                if constexpr (ylt::reflection::is_ylt_refl_v<inner_t>) {
                    if (value_node.is_map()) {
                        audit_yaml_strict<inner_t>(value_node, missing_required,
                                                    require_all, full_name);
                    }
                }
                // (c) optional<vector<YLT_REFL T>>
                else if constexpr (is_range_v<inner_t>) {
                    using elem_t = typename inner_t::value_type;
                    if constexpr (ylt::reflection::is_ylt_refl_v<elem_t>) {
                        if (value_node.is_seq()) {
                            for (ryml::ConstNodeRef el : value_node.children()) {
                                if (el.is_map()) {
                                    audit_yaml_strict<elem_t>(
                                        el, missing_required, require_all,
                                        full_name + "[]");
                                }
                            }
                        }
                    }
                }
            }
            // (d) vector<YLT_REFL T> (non-optional)
            else if constexpr (is_range_v<field_t>) {
                using elem_t = typename field_t::value_type;
                if constexpr (ylt::reflection::is_ylt_refl_v<elem_t>) {
                    if (value_node.is_seq()) {
                        for (ryml::ConstNodeRef el : value_node.children()) {
                            if (el.is_map()) {
                                audit_yaml_strict<elem_t>(
                                    el, missing_required, require_all,
                                    full_name + "[]");
                            }
                        }
                    }
                }
            }
        }
    });
}

}  // namespace detail
}  // namespace light_config
```

- [ ] **Step 2: Verify compilation**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
```

If ryml API mismatches occur (e.g., `find_child` not available, `operator[]` / `children()` access differs), consult `ryml_all.hpp` for the exact API and adjust:
- `find_child` may be `child()` or require a key type wrapper.
- `node[i + 1]` for value access may need `node.child(i + 1)`.
- Verify against the smoke-test pattern from Task 1 Step 3.

- [ ] **Step 3: Commit (this header is standalone — not yet called by anyone)**

```bash
git add include/light_config/detail/audit_yaml_strict.hpp
git commit -m "feat: add YAML strict-required audit via rapidyaml DOM

New audit_yaml_strict.hpp mirrors audit_json_recursive's recursion shape
but walks ryml::ConstNodeRef instead of iguana::jobject. When require_all
is true, non-optional fields whose keys are absent from the YAML mapping
are collected into missing_required.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Thread `require_all` through JSON & YAML loaders + convenience layer

**Files:**
- Modify: `include/light_config/json_loader.hpp`
- Modify: `include/light_config/yaml_loader.hpp`
- Modify: `include/light_config/light_config.hpp`

**Interfaces:**
- Consumes: `audit_json_recursive` new signature (Task 3), `audit_yaml_strict.hpp` (Task 4), `kMissingRequiredField`, `compose_missing_msg()` (Task 2)
- Produces: All public loader signatures with `bool require_all = false`; early-return logic

- [ ] **Step 1: `load_from_json_file` — add param, thread audit, add early-return**

In `json_loader.hpp`, change the signature (line 34-35):

```cpp
[[nodiscard]] Result load_from_json_file(T& config, const std::string& path,
                                         std::string_view expected_schema_version = "",
                                         bool require_all = false) {
```

Update the audit call (~line 86):

```cpp
        detail::audit_json_recursive(audit_temp, dom, result.absent_optionals,
                                     result.present_fields, result.missing_required,
                                     require_all);
```

Insert early-return after the DOM audit `try` block and before `// ---- Actual struct population ----`:

```cpp
        if (require_all && !result.missing_required.empty()) {
            result.code = ErrorCode::kMissingRequiredField;
            result.message = compose_missing_msg(result.missing_required);
            return result;
        }
```

- [ ] **Step 2: `load_from_json_string` — same three changes**

Signature (~line 145):

```cpp
[[nodiscard]] Result load_from_json_string(T& config, const std::string& json_str,
                                           std::string_view expected_schema_version = "",
                                           bool require_all = false) {
```

Audit call (~line 181): same threading as Step 1. Early-return: same as Step 1.

- [ ] **Step 3: Thread through JSON `_and_validate` variants**

For `load_from_json_file_and_validate` (~line 119):
- Add `bool require_all = false` after `expected_schema_version = ""`
- Thread: `load_from_json_file(config, path, expected_schema_version, require_all)`

For `load_from_json_string_and_validate` (~line 214): same pattern.

- [ ] **Step 4: Wire YAML loaders — add `require_all` + strict audit path**

In `yaml_loader.hpp`, add at the top after existing includes:

```cpp
#include <ryml_all.hpp>
#include <ryml_std.hpp>
#include "light_config/detail/audit_yaml_strict.hpp"
```

For `load_from_yaml_file` (line 31, the no-schema-version overload), add `bool require_all = false` to the signature and insert the rapidyaml pre-check before `iguana::from_yaml`:

```cpp
    if (require_all) {
        ryml::Tree tree = ryml::parse_in_arena(ryml::to_csubstr(content));
        ryml::ConstNodeRef root = tree.rootref();
        auto result = Result::success();
        detail::audit_yaml_strict<T>(root, result.missing_required, require_all);
        if (!result.missing_required.empty()) {
            result.code = ErrorCode::kMissingRequiredField;
            result.message = compose_missing_msg(result.missing_required);
            return result;
        }
    }
```

Apply the same to `load_from_yaml_string` (line 92, no-schema-version overload).

For sche-ma-versioned overloads: the file overload (~line 265) delegates to the string overload, so only the string overload needs the param + strict path. Thread `require_all` through.

For `_and_validate` variants: add `require_all` and thread to inner call.

- [ ] **Step 5: Thread through convenience loaders in `light_config.hpp`**

Add `bool require_all = false` to:

- `load()` — thread to `load_from_yaml_file` / `load_from_json_file`:

```cpp
template <typename T>
[[nodiscard]] Result load(T& config, const std::string& path,
                          Format format = Format::Auto, bool require_all = false) {
    // ...detect format...
    if (format == Format::Yaml) {
        return load_from_yaml_file(config, path, "", require_all);
    }
    return load_from_json_file(config, path, "", require_all);
}
```

- `load_and_validate()` — thread to `load_from_*_and_validate` calls
- `load_versioned()` — thread to `load_from_*` calls
- `load_versioned_and_validate()` — thread similarly

- [ ] **Step 6: Build & verify all tests pass**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
cd build && ctest --output-on-failure
```

All existing tests must pass — `require_all` defaults to `false` everywhere.

- [ ] **Step 7: Commit**

```bash
git add include/light_config/json_loader.hpp include/light_config/yaml_loader.hpp include/light_config/light_config.hpp
git commit -m "feat: thread require_all flag through all loaders with strict enforcement

Add bool require_all=false to all 8 public loader signatures and 4
convenience wrappers. When true: JSON audit collects missing non-optional
fields from DOM; YAML uses rapidyaml DOM audit before from_yaml.
On missing-required → kMissingRequiredField returned before population.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Add basic strict-mode tests to `test_basic.cpp`

**Files:**
- Modify: `tests/test_basic.cpp`

**Interfaces:**
- None (test-only)

- [ ] **Step 1: Add JSON strict test cases**

After the existing JSON tests, add:

```cpp
TEST_CASE("JSON strict: required all present -> ok") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "test", "value": 42, "flag": true, "ratio": 2.5,
        "numbers": [1, 2], "tags": ["a"]
    })", "", true);
    CHECK(r.ok());
    CHECK(r.missing_required.empty());
}

TEST_CASE("JSON strict: single required field missing") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "value": 42, "flag": true, "ratio": 2.5,
        "numbers": [1], "tags": ["a"]
    })", "", true);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kMissingRequiredField);
    CHECK(r.missing_required.size() == 1);
    CHECK(r.missing_required[0] == "name");
}

TEST_CASE("JSON strict: multiple required fields missing") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({"name": "test"})", "", true);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kMissingRequiredField);
    CHECK(r.missing_required.size() >= 2);
}

TEST_CASE("JSON strict: config untouched on failure") {
    TestConfig cfg;
    cfg.name = "original";
    cfg.value = 999;
    auto r = light_config::load_from_json_string(cfg, R"({"value": 42})", "", true);
    CHECK(!r.ok());
    CHECK(cfg.name == "original");
    CHECK(cfg.value == 999);
}

TEST_CASE("JSON strict: require_all=false is lenient") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "test", "value": 42, "flag": true
    })", "", false);
    CHECK(r.ok());
    CHECK(cfg.ratio == 1.0);
    CHECK(cfg.numbers.empty());
    CHECK(r.missing_required.empty());
}

TEST_CASE("JSON strict: nested struct required subfield missing") {
    OuterCfg cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "app_name": "myapp", "version": 2,
        "inner": { "port": 8080 }
    })", "", true);
    CHECK(!r.ok());
    bool found = false;
    for (auto& f : r.missing_required) {
        if (f == "inner.host") found = true;
    }
    CHECK(found);
}

TEST_CASE("JSON strict: optional present is fine") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "test", "value": 42, "flag": true, "ratio": 2.5,
        "numbers": [1], "tags": ["a"], "opt_str": "hello"
    })", "", true);
    CHECK(r.ok());
    CHECK(r.missing_required.empty());
}

TEST_CASE("JSON strict: optional absent is fine") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "test", "value": 42, "flag": true, "ratio": 2.5,
        "numbers": [1], "tags": ["a"]
    })", "", true);
    CHECK(r.ok());
    CHECK(r.missing_required.empty());
}

TEST_CASE("JSON strict: explicit null on required = present (not missing)") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": null, "value": 42, "flag": true, "ratio": 2.5,
        "numbers": [1], "tags": ["a"]
    })", "", true);
    // Key is present; strict audit does not flag it missing.
    if (!r.ok()) {
        CHECK(r.code != light_config::ErrorCode::kMissingRequiredField);
    }
}
```

- [ ] **Step 2: Add YAML strict test cases**

```cpp
TEST_CASE("YAML strict: required all present -> ok") {
    TestConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
name: test
value: 42
flag: true
ratio: 2.5
numbers:
  - 1
  - 2
tags:
  - "a"
)", "", true);
    CHECK(r.ok());
    CHECK(r.missing_required.empty());
}

TEST_CASE("YAML strict: single required field missing") {
    TestConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
value: 42
flag: true
ratio: 2.5
numbers:
  - 1
tags:
  - "a"
)", "", true);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kMissingRequiredField);
    CHECK(r.missing_required.size() == 1);
    CHECK(r.missing_required[0] == "name");
}

TEST_CASE("YAML strict: require_all=false is lenient") {
    TestConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
name: test
value: 42
flag: true
)", "", false);
    CHECK(r.ok());
    CHECK(r.missing_required.empty());
}
```

- [ ] **Step 3: Build & run tests**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
cd build && ./tests/test_basic
```

All tests must pass (both existing and new strict-mode cases).

- [ ] **Step 4: Commit**

```bash
git add tests/test_basic.cpp
git commit -m "test: add basic strict-mode required-field tests for JSON and YAML

Cover: all-present ok, single/multiple required missing, nested subfield
missing, config untouched on failure, require_all=false lenient,
optional fine, explicit null is present.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Create dedicated `test_strict_required.cpp` and YAML edge probes

**Files:**
- Create: `tests/test_strict_required.cpp`
- Modify: `tests/test_edge_probes.cpp`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- Produces: New CTest target `test_strict_required`

- [ ] **Step 1: Create `tests/test_strict_required.cpp`**

Create a new test file with ~30 test cases covering the full recursion matrix, both formats, all entry-point families, and the convenience wrappers. Key test categories:

| Category | Representative assertions |
|---|---|
| all-present (JSON + YAML) | `r.ok()`, `missing_required.empty()` |
| single/multiple missing | `kMissingRequiredField`, exact field names in `missing_required` |
| nested struct subfield | dotted paths like `"inner.host"` |
| deep nesting (3 levels) | `"middle.leaf.tag"` |
| vector\<struct\> element subfields | `"items[].name"`, `"items[].qty"` |
| optional\<struct\> present→enforced | `"extra.host"` when extra present |
| optional\<struct\> absent→fine | `r.ok()` |
| optional\<vector\<struct\>\> | recurse when present |
| config untouched on failure | out-param holds pre-call values |
| load_and_validate strict | strict runs before validator |
| require_all=false no-op | `r.ok()`, `missing_required.empty()` |
| load_from_json_file strict | file-based entry point |
| load_from_yaml_file strict | file-based entry point |
| load() convenience | `Format::Json`/`Format::Yaml` + `require_all=true` |
| load_versioned() convenience | JSON path + `require_all=true` |

The file uses the same `DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN` pattern as `test_basic.cpp` and defines local test structs (`StrictTestCfg { string name; int port=0; bool enabled=false; optional<string> desc; }`, `Outer { string app; Inner inner; optional<Inner> extra; }`, `VecWrapper { string label; vector<VecItem> items; optional<vector<VecItem>> opt_items; }`, deep nesting structs).

- [ ] **Step 2: Add YAML edge-probe cases to `test_edge_probes.cpp`**

After the existing edge-probe cases, add:

```cpp
TEST_CASE("YAML strict: explicit null on required field is present") {
    StrictTestCfg cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
name: null
port: 80
enabled: true
)", "", true);
    if (!r.ok()) {
        CHECK(r.code != light_config::ErrorCode::kMissingRequiredField);
    } else {
        CHECK(r.missing_required.empty());
    }
}

TEST_CASE("YAML strict: flow-style mapping required present") {
    StrictTestCfg cfg;
    auto r = light_config::load_from_yaml_string(cfg,
        R"({name: flowsrv, port: 8080, enabled: true})", "", true);
    CHECK(r.ok());
    CHECK(r.missing_required.empty());
}

TEST_CASE("YAML strict: flow-style mapping required missing") {
    StrictTestCfg cfg;
    auto r = light_config::load_from_yaml_string(cfg,
        R"({name: flowsrv, enabled: true})", "", true);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kMissingRequiredField);
    CHECK(r.missing_required[0] == "port");
}

TEST_CASE("YAML strict: root sequence -> all required missing") {
    DeepL1 cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
- item1
- item2
)", "", true);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kMissingRequiredField);
}
```

- [ ] **Step 3: Wire the new target in `tests/CMakeLists.txt`**

After the `test_edge_probes` block:

```cmake
add_executable(test_strict_required test_strict_required.cpp)
target_include_directories(test_strict_required PRIVATE ${CMAKE_SOURCE_DIR}/third_party/doctest)
target_link_libraries(test_strict_required PRIVATE light_config)
add_test(NAME light_config_strict_required COMMAND test_strict_required)
```

- [ ] **Step 4: Build & run all tests**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
cd build && ctest --output-on-failure
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_strict_required.cpp tests/test_edge_probes.cpp tests/CMakeLists.txt
git commit -m "test: add dedicated strict-required test suite and YAML edge probes

New tests/test_strict_required.cpp with ~30 cases covering the full
recursion matrix, both formats, all entry-point families, and
convenience wrappers. YAML edge probes: null-as-present, flow-style,
root-sequence→all-missing. Wired as CTest target test_strict_required.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Generator integration probe + example update + docs

**Files:**
- Create: `tests/edge_probes/strict_required.csv`
- Create: `scripts/test_strict_required_build.py`
- Modify: `tests/CMakeLists.txt`
- Modify: `examples/example.cpp`
- Modify: `CLAUDE.md`

**Interfaces:**
- Produces: CTest target `gen_config_strict_required`; example snippet; doc update

- [ ] **Step 1: Create generator probe CSV**

Create `tests/edge_probes/strict_required.csv`:

```csv
field_name,group,type,default,min,max,description
app_name,AppConfig,string,,,,"required — no default → non-optional std::string"
port,AppConfig,int,,1,65535,"required — no default → non-optional int"
timeout,AppConfig,int,30,0,300,"optional — has default → std::optional<int>"
```

- [ ] **Step 2: Create generator integration test**

Create `scripts/test_strict_required_build.py`:

```python
#!/usr/bin/env python3
"""Integration test: generated config + strict required-field enforcement.

Generates C++ from strict_required.csv, compiles a small driver that loads
a trimmed config with require_all=true, and asserts kMissingRequiredField.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
GEN_CONFIG = SCRIPT_DIR / "gen_config.py"
CSV_FILE = PROJECT_DIR / "tests" / "edge_probes" / "strict_required.csv"
BUILD_DIR = Path(tempfile.mkdtemp(prefix="strict_required_test_"))


def run(cmd, **kwargs):
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout, result.stderr


def main():
    # 1. Generate C++ from CSV
    out_dir = BUILD_DIR / "gen"
    out_dir.mkdir(parents=True)
    rc, stdout, stderr = run([
        sys.executable, str(GEN_CONFIG),
        "--input", str(CSV_FILE),
        "--output-dir", str(out_dir),
        "--generate-samples",
    ])
    if rc != 0:
        print(f"FAIL: gen_config.py failed\n{stderr}")
        return 1

    hpp = out_dir / "app_config.hpp"
    src = out_dir / "app_config.cpp"
    if not hpp.exists() or not src.exists():
        print(f"FAIL: generated files missing")
        return 1

    # 2. Build a driver that tests strict loading
    driver_path = BUILD_DIR / "driver.cpp"
    driver_path.write_text('''
#include "app_config.hpp"
#include <light_config/light_config.hpp>
#include <iostream>

int main() {
    using namespace light_config;

    // Trimmed config: missing "port" (required, no default → non-optional)
    std::string json = R"({"app_name": "testapp", "timeout": 60})";

    AppConfig cfg;
    auto r = load_from_json_string_and_validate(
        cfg, json, validate_AppConfig, "", /*require_all=*/true);

    if (r.code == ErrorCode::kMissingRequiredField) {
        bool found_port = false;
        for (auto& f : r.missing_required) {
            if (f == "port") found_port = true;
        }
        if (!found_port) {
            std::cerr << "FAIL: port not in missing_required\\n";
            return 1;
        }
        std::cout << "OK: kMissingRequiredField with port\\n";
        return 0;
    }

    std::cerr << "FAIL: expected kMissingRequiredField, got code="
              << static_cast<int>(r.code) << "\\n";
    return 1;
}
''')

    # 3. Compile
    ylt_dir = PROJECT_DIR / "third_party" / "yalantinglibs" / "include"
    ryml_dir = PROJECT_DIR / "third_party" / "rapidyaml" / "include"

    binary = BUILD_DIR / "driver"
    rc, stdout, stderr = run([
        "clang++", "-std=c++17",
        "-I", str(PROJECT_DIR / "include"),
        "-I", str(out_dir),
        "-isystem", str(ylt_dir),
        "-isystem", str(ylt_dir / "ylt" / "standalone"),
        "-isystem", str(ylt_dir / "ylt" / "thirdparty"),
        "-isystem", str(ryml_dir),
        str(driver_path), str(src),
        "-o", str(binary),
    ])
    if rc != 0:
        print(f"FAIL: compilation failed\n{stdout}\n{stderr}")
        return 1

    # 4. Run
    rc, stdout, stderr = run([str(binary)])
    print(stdout, end="")
    if stderr:
        print(stderr, end="")
    return rc


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Wire generator test into CTest**

In `tests/CMakeLists.txt`, inside the `if(PYTHON3_EXE)` block, after the `gen_config_edge_probes` test:

```cmake
    add_test(NAME gen_config_strict_required
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_strict_required_build.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
```

- [ ] **Step 4: Add strict-mode snippet to `examples/example.cpp`**

Near the end of `main()`, before the return:

```cpp
    // ---- Strict required-field enforcement ----
    {
        std::cout << "\n=== Strict required-field enforcement ===\n";
        TestConfig cfg;
        auto r = light_config::load_from_json_string(cfg, R"({"name": "strict_test"})",
                                                      "", /*require_all=*/true);
        if (!r.ok()) {
            std::cout << "Strict load rejected: " << r.message << "\n";
            for (auto& f : r.missing_required) {
                std::cout << "  missing required: " << f << "\n";
            }
        }
        TestConfig cfg2;
        auto r2 = light_config::load_from_json_string(cfg2, R"({"name": "lenient"})");
        std::cout << "Lenient load: " << (r2.ok() ? "ok" : "FAIL") << "\n";
    }
```

- [ ] **Step 5: Update CLAUDE.md**

Under the error code range description, add:

```markdown
**New error code:** `kMissingRequiredField` (32) — returned when `require_all=true`
and a non-`std::optional` field is absent from the source document.
```

Under dependencies, add:

```markdown
- rapidyaml (MIT, single-header) — `third_party/rapidyaml/` — used for YAML
  strict required-field audit; not needed for JSON-only consumers.
```

- [ ] **Step 6: Build, test, run example**

```bash
cmake --build build -j$(sysctl -n hw.logicalcpu)
cd build && ctest --output-on-failure
./examples/example
```

All tests pass, example runs without crash.

- [ ] **Step 7: Commit**

```bash
git add tests/edge_probes/strict_required.csv \
        scripts/test_strict_required_build.py \
        tests/CMakeLists.txt examples/example.cpp CLAUDE.md
git commit -m "test: add generator strict-required probe, example snippet, docs

Generator integration test: generates config from CSV, compiles a
strict-load driver, asserts kMissingRequiredField when a required
field is absent. Example snippet in example.cpp. CLAUDE.md updated.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Final integration — full CI-like run

**Files:**
- None (verification only)

- [ ] **Step 1: Full rebuild from scratch**

```bash
cd /Users/hao/work/light_config
rm -rf build
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTS=ON
cmake --build build -j$(sysctl -n hw.logicalcpu)
```

Confirm zero compile errors from project code.

- [ ] **Step 2: Run full CTest suite**

```bash
cd build && ctest --output-on-failure
```

Expected: all tests pass — `test_basic`, `test_edge_probes`, `test_strict_required`, `gen_config_*`, `gen_config_strict_required`.

- [ ] **Step 3: Clang-format dry-run**

```bash
find include examples tests \( -name '*.cpp' -o -name '*.hpp' -o -name '*.h' \) -print \
    | xargs clang-format --dry-run --Werror
```

Expected: no formatting errors.

- [ ] **Step 4: Run example binary**

```bash
./build/examples/example
```

Expected: all sections output including strict-mode demo, no crashes.

- [ ] **Step 5: Commit any formatting fixes if needed**

```bash
git status
# Only commit if clang-format or rebuild produced changes
```
