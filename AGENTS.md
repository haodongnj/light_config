# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project overview

**light_config** — a header-only C++17 library that loads JSON/YAML config files into
`YLT_REFL`-annotated structs with zero hand-written parsing code. Built on vendored
[yalantinglibs](https://github.com/alibaba/yalantinglibs) 0.6.1 (`third_party/yalantinglibs/`,
`YLT_VERSION 600`). Also includes a CSV-driven struct-and-validator code generator
(`scripts/gen_config.py`).

## Build & test

```bash
# Configure & build
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTS=ON
cmake --build build

# Run all tests via CTest
cd build && ctest

# Or run the test binary directly
./build/tests/test_basic

# Build & run the example
cmake --build build --target example
./build/examples/example
```

The library is **header-only** (`light_config` is an `INTERFACE` CMake target). Tests and
examples link against it. CMake 3.16+, C++17 required.

## Formatting & static analysis

All C++ code is formatted with **clang-format** (Google-based, 4-space indent, 100 cols,
configured in `.clang-format`). VS Code auto-formats on save via the `xaver.clang-format`
extension (configured in `.vscode/settings.json`).

```bash
# CI-style dry-run (fail if anything would change)
find include examples tests \( -name '*.cpp' -o -name '*.hpp' -o -name '*.h' \) -print \
    | xargs clang-format --dry-run --Werror

# Opt-in clang-tidy during compilation
cmake -B build -S . -DENABLE_CLANG_TIDY=ON
```

Generated files (`examples/app_config.*`, `examples/network.*`) are excluded from clang-tidy.

## Architecture

### Core library (`include/light_config/`)

All public API lives in `namespace light_config`. Four headers:

| File | Exposes |
|---|---|
| `result.hpp` | `ErrorCode`, `Format`, `Result`, `error_code_message()` |
| `json_loader.hpp` | JSON load/save functions |
| `yaml_loader.hpp` | YAML load/save functions |
| `light_config.hpp` | `load()` (auto-detect format), `load_versioned()` (schema-gated), re-exports everything |

Three detail headers in `include/light_config/detail/`:

| File | Purpose |
|---|---|
| `audit_json.hpp` | Recursive DOM walk — distinguishes absent keys from explicit null |
| `audit_yaml.hpp` | Post-load check — `std::nullopt` fields reported as absent (conflates null with missing) |
| `file_utils.hpp` | `read_file_into_string()` — shared by both loaders |

**Error code ranges** (enforced by `static_assert`): 0=ok, 1–9=file I/O, 10–19=JSON,
20–29=YAML, 30–39=validation/schema, 40–49=format/compatibility.

**Loading flow**: read file → optionally check `"$schema"` key against expected version →
populate struct via iguana → recursive DOM audit for optional-field tracking (JSON only;
YAML skips DOM audit).

### Vendored dependency

yalantinglibs 0.6.1 lives at `third_party/yalantinglibs/` (header-only subset). Its include
paths are SYSTEM includes on the `light_config` INTERFACE target. Key libraries used:
`struct_json`, `struct_yaml`, `reflection` (`YLT_REFL`, `for_each`).

### CSV code generator (`scripts/gen_config.py`)

Reads a CSV schema and generates C++ struct definitions with `YLT_REFL` + validation
functions.

```bash
python3 scripts/gen_config.py --input examples/sample_config.csv --output-dir examples/ --generate-samples
```

**Generated files (`examples/app_config.*`, `examples/network.*`) must never be hand-edited**
— always regenerate from the CSV source.

Key CLI flags: `--input`, `--output-dir`, `--hpp-dir`, `--src-dir`, `--per-struct`,
`--namespace`, `--generate-samples`, `--schema-version`, `--struct-name`, `--hpp-name`.

CSV columns: `field_name`, `group` (struct name), `type`, `default`, `min`, `max`,
`description`, `hpp_file` (optional). Containment is expressed by setting `type` to another
group's name. The root struct is auto-detected.

Test suite: `scripts/test_gen_config.py`, `test_metadata.py`, `test_provenance.py`,
`test_provenance_build.py`, `test_stamp_emit.py`. Run with `python3 scripts/<test>.py`.

## Tests

- `tests/test_basic.cpp` — JSON/YAML loading, nested structs, format auto-detection,
  schema version matching/mismatch, serialization round-trips.
- `scripts/test_gen_config.py` and companion scripts — test the CSV generator.

## Pre-commit hook

```bash
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

The hook clang-formats staged C++ files on commit. Soft enforcement (warns if clang-format
is missing, doesn't block).
