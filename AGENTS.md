# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project overview

**light_config** — a header-only C++17 library that loads JSON/YAML config files into `YLT_REFL`-annotated structs with zero hand-written parsing code. Built on vendored [yalantinglibs](https://github.com/alibaba/yalantinglibs) 0.6.0 (`third_party/yalantinglibs/`, `YLT_VERSION 600`). Also includes a CSV-driven struct-and-validator code generator (`scripts/gen_config.py`).

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

The library is **header-only** (`light_config` is an `INTERFACE` CMake target). Tests and examples link against it. CMake 3.16+, C++17 required.

## Formatting & static analysis

All C++ code is formatted with **clang-format** (Google-based, 4-space indent, 100 cols, configured in
`.clang-format`). VS Code auto-formats on save via the `xaver.clang-format` extension (configured in
`.vscode/settings.json`).

```bash
# Format all hand-written sources in-place
cmake --build build --target format

# CI-style dry-run (fails if anything would change)
cmake --build build --target check-format

# Opt-in clang-tidy during compilation
cmake -B build -S . -DENABLE_CLANG_TIDY=ON
```

Generated files (`examples/app_config.*`, `examples/network.*`) are excluded from both format targets and clang-tidy.

## Architecture

### Core library (`include/light_config/`)

Four header files, all in `namespace light_config`:

| File | What it exposes |
|---|---|
| `load_result.hpp` | `ErrorCode` enum, `Format` enum, `LoadResult` struct, `error_code_message()`, `detail::is_optional` trait |
| `json_loader.hpp` | `load_from_json_file()`, `load_from_json_string()`, `to_json()`, `save_to_json_file()` |
| `yaml_loader.hpp` | `load_from_yaml_file()`, `load_from_yaml_string()`, `to_yaml()`, `save_to_yaml_file()` |
| `light_config.hpp` | `load()` (auto-detect format), `load_versioned()` (schema-version-gated) — plus re-exports everything above |

**Error code ranges** (enforced by `static_assert`): 0=ok, 1–9=file I/O, 10–19=JSON, 20–29=YAML, 30–39=validation/schema.

**Loading flow**: load functions read the file, optionally check a `$schema` key against an expected version, populate the struct via iguana, then run a recursive DOM audit to identify which `std::optional` fields were absent vs. present. YAML has no DOM audit — absent-vs-null is conflated.

**Serialization**: `to_json(config, pretty)`, `to_yaml(config)`, `save_to_json_file(config, path, pretty)`, `save_to_yaml_file(config, path)`.

### Vendored dependency

yalantinglibs 0.6.0 lives at `third_party/yalantinglibs/` (header-only subset). The relevant include paths are configured as SYSTEM includes on the `light_config` INTERFACE target. Used libraries: `struct_json` (reader + writer via `iguana`), `struct_yaml` (reader + writer via `iguana`), `reflection` (`YLT_REFL`, `for_each`).

### CSV code generator (`scripts/gen_config.py`)

Reads a CSV schema and generates C++ struct definitions with `YLT_REFL` + validation functions. **Generated files in `examples/` (`app_config.*`, `network.*`) must never be hand-edited** — always regenerate.

```bash
python3 scripts/gen_config.py --input examples/sample_config.csv --output-dir examples/ --generate-samples
```

Key CLI flags: `--input`, `--output-dir`, `--hpp-dir`, `--src-dir`, `--per-struct`, `--namespace`, `--generate-samples`, `--schema-version`, `--struct-name`, `--hpp-name`.

Test suite for the generator: `scripts/test_gen_config.py`, `test_metadata.py`, `test_provenance.py`, `test_provenance_build.py`, `test_stamp_emit.py`. Run with `python3 scripts/<test>.py`.

### Generated file format

- `.hpp`: struct definition, `YLT_REFL` macro, `constexpr` schema version constant, `validate_<Name>()` declaration — plus a provenance stamp (`///` comment block with schema version, source CSV, MD5, UTC timestamp, generator name).
- `.cpp`: `validate_<Name>()` implementation — recursive range checks that call into nested struct validators.

CSV columns: `field_name`, `group` (required, non-empty), `type`, `default`, `min`, `max`, `description`, `hpp_file` (optional). The `group` column is the struct type name; containment is expressed by setting `type` to another group's name. The root struct is auto-detected.

## Tests

- `tests/test_basic.cpp` — covers JSON/YAML loading, nested structs, format auto-detection, schema version matching/mismatch, and serialization round-trips.
- `scripts/test_gen_config.py` and companion scripts — test the CSV generator.

## Pre-commit hook

```bash
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

The hook clang-formats staged C++ files on commit. Soft enforcement (warns if clang-format is missing, doesn't block).
