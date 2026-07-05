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
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug
cmake --build build

# Run all tests via CTest
cd build && ctest

# Or run the test binary directly
./build/tests/test_basic

# Build & run the example
cmake --build build --target example_json
./build/examples/example_json
```

The library is **header-only** (`light_config` is an `INTERFACE` CMake target). Tests and
examples link against it. CMake 3.16+, C++17 required.

## Formatting & static analysis

All C++ code is formatted with **clang-format** (Google-based, 4-space indent, 100 cols,
configured in `.clang-format`). VS Code auto-formats on save via the `xaver.clang-format`
extension (configured in `.vscode/settings.json`).

```bash
# CI-style dry-run (fail if anything would change)
find include examples tests -name '*.cpp' -o -name '*.hpp' -o -name '*.h' | xargs clang-format --dry-run --Werror

# Opt-in clang-tidy during compilation
cmake -B build -S . -DENABLE_CLANG_TIDY=ON
```

Generated files (`examples/app_config.*`, `examples/network.*`) are excluded from clang-tidy.

## Architecture

### Core library (`include/light_config/`)

Four header files, all in `namespace light_config`:

| File | What it exposes |
|---|---|
| `result.hpp` | `ErrorCode` enum, `Format` enum, `Result` struct, `error_code_message()`, `detail::is_optional` trait |
| `json_loader.hpp` | `load_from_json_file()`, `load_from_json_string()`, `to_json()`, `save_to_json_file()` |
| `yaml_loader.hpp` | `load_from_yaml_file()`, `load_from_yaml_string()`, `to_yaml()`, `save_to_yaml_file()` |
| `light_config.hpp` | `load()` (auto-detect format), `load_versioned()` (schema-version-gated) — plus re-exports everything above |

Three detail headers in `include/light_config/detail/`:

| File | What it does |
|---|---|
| `audit_json.hpp` | Recursive DOM walk via `iguana::jobject` — distinguishes absent keys from explicit null |
| `audit_yaml.hpp` | Recursive post-load check — `std::nullopt` fields are reported as absent (conflates null with missing) |
| `file_utils.hpp` | `read_file_into_string()` — shared between JSON and YAML file loaders |

**Error code ranges** (enforced by `static_assert`): 0=ok, 1–9=file I/O, 10–19=JSON,
20–29=YAML, 30–39=validation/schema, 40–49=format/compatibility.

**Loading flow**: read file → optionally check `$schema` key against expected version →
populate struct via iguana → recursive DOM audit to identify which `std::optional` fields
were absent vs. present (JSON only; YAML has no DOM audit).

**Serialization**: `to_json(config, pretty)`, `to_yaml(config)`,
`save_to_json_file(config, path, pretty)`, `save_to_yaml_file(config, path)`.

### Vendored dependency

yalantinglibs 0.6.1 lives at `third_party/yalantinglibs/` (header-only subset). The relevant
include paths are configured as SYSTEM includes on the `light_config` INTERFACE target.
Used libraries: `struct_json` (reader + writer via `iguana`), `struct_yaml` (reader + writer
via `iguana`), `reflection` (`YLT_REFL`, `for_each`).

### CSV code generator (`scripts/gen_config.py`)

Reads a CSV schema and generates C++ struct definitions with `YLT_REFL` + validation
functions. **Generated files in `examples/` (`app_config.*`, `network.*`) must never be
hand-edited** — always regenerate.

```bash
python3 scripts/gen_config.py --input examples/sample_config.csv --output-dir examples/ --generate-samples
```

Key CLI flags: `--input`, `--output-dir`, `--hpp-dir`, `--src-dir`, `--per-struct`,
`--namespace`, `--generate-samples`, `--schema-version`, `--struct-name`, `--hpp-name`.

Test suite: `scripts/test_gen_config.py`, `test_metadata.py`, `test_provenance.py`,
`test_provenance_build.py`, `test_stamp_emit.py`. Run with `python3 scripts/<test>.py`.

### Generated file format

- `.hpp`: struct definition, `YLT_REFL` macro, `constexpr` schema version constant,
  `validate_<Name>()` declaration — plus a provenance stamp (`///` comment block with
  schema version, source CSV, MD5, UTC timestamp, generator name).
- `.cpp`: `validate_<Name>()` implementation — recursive range checks that call into
  nested struct validators.

CSV columns: `field_name`, `group` (required, non-empty), `type`, `default`, `min`, `max`,
`description`, `hpp_file` (optional). The `group` column is the struct type name; containment
is expressed by setting `type` to another group's name. The root struct is auto-detected.

## Tests

- `tests/test_basic.cpp` — covers JSON/YAML loading, nested structs, format auto-detection,
  schema version matching/mismatch, and serialization round-trips.
- `scripts/test_gen_config.py` and companion scripts — test the CSV generator.

## Pre-commit hook

```bash
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

The hook clang-formats staged C++ files on commit. Soft enforcement (warns if clang-format
is missing, doesn't block).
