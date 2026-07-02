# light_config

A header-only C++17 library for loading configuration files directly into
structs. Built on [yalantinglibs](https://github.com/alibaba/yalantinglibs)
(vendored at 0.6.0), it uses compile-time reflection (`YLT_REFL`) so you
never write a line of hand-rolled JSON/YAML parsing.

## Features

- **JSON and YAML support** — same struct, either format.
- **Automatic format detection** — `.json`, `.yaml`, `.yml`; defaults to JSON.
- **Optional-field audit** — `std::optional<T>` fields are tracked: which were
  present in the file, which were absent (JSON: precise DOM-level check;
  YAML: post-load nullopt check). Results reported via `LoadResult`.
- **Structured error codes** — `ErrorCode` enum with numeric ranges for file
  I/O (1–9), JSON (10–19), YAML (20–29), and validation/schema (30–39).
  Ranges enforced by `static_assert`. `constexpr error_code_message()` for
  logging.
- **Schema versioning** — optional `$schema` key enforcement via
  `load_versioned()` or the `expected_schema_version` parameter on all
  loader functions. Mismatches return `kSchemaMismatch`.
- **Serialization** — `to_json()`, `to_yaml()`, `save_to_json_file()`,
  `save_to_yaml_file()` round-trip config structs back to strings or files.
- **Exception-free public API** — exceptions from the underlying iguana
  parser are caught at the boundary and translated to error codes.
- **CSV code generator** — `scripts/gen_config.py` turns a CSV schema into
  `YLT_REFL`-annotated structs + `validate_<Name>()` functions with range
  checks, plus optional sample JSON/YAML configs.
- **Provenance stamp** — every generated file records schema version, source
  CSV, MD5 hash, and UTC timestamp in a `///` comment block.
- **Zero external dependencies** — only standard library + vendored headers.
- **Auto-formatted** — pre-commit hook and PostToolUse hook keep code
  formatted; `check-format` CMake target for CI enforcement.

## Quick start

Annotate your struct with `YLT_REFL`, then call `light_config::load()` with a
file path. Errors are returned via `LoadResult` rather than thrown. See
[examples/example.cpp](examples/example.cpp) and
[examples/sample_config.csv](examples/sample_config.csv) for a complete
demonstration.

## Build

```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug
cmake --build build --target test_basic      # build tests
./build/tests/test_basic                     # run all unit tests
cmake --build build --target example_json    # build and run the example
```

CMake 3.16+, C++17 toolchain required (Apple Clang 15+, GCC 9+, MSVC 2019 16.8+).
See [docs/setup-ubuntu-22.04.md](docs/setup-ubuntu-22.04.md) for Ubuntu setup.

## API overview

### Loader functions

All loader functions return `LoadResult` and accept an optional
`expected_schema_version` parameter (empty = permissive, no version check):

| Function | Description |
|---|---|
| `load(cfg, path, fmt=Auto)` | Auto-detect format from extension |
| `load_versioned(cfg, path, expected_schema_version, fmt=Auto)` | Load with `$schema` enforcement |
| `load_from_json_file(cfg, path)` | Load a JSON file |
| `load_from_yaml_file(cfg, path)` | Load a YAML file |
| `load_from_json_string(cfg, json_str)` | Parse an in-memory JSON string |
| `load_from_yaml_string(cfg, yaml_str)` | Parse an in-memory YAML string |

### Serialization

| Function | Returns |
|---|---|
| `to_json(cfg, pretty=false)` | `std::optional<std::string>` |
| `to_yaml(cfg)` | `std::optional<std::string>` |
| `save_to_json_file(cfg, path, pretty=true)` | `bool` |
| `save_to_yaml_file(cfg, path)` | `bool` |

### ErrorCode (excerpt)

`kOk` (0), `kFileReadError` (1), `kFileEmpty` (2), `kJsonParseError` (10),
`kJsonDeserializeError` (11), `kYamlParseError` (20),
`kValidationError` (30), `kSchemaMismatch` (31). See `error_code_message()`
for human-readable labels.

### LoadResult

Return type for all loader and validation functions:
- `code` — `ErrorCode::kOk` on success.
- `message` — detail when `code != kOk`.
- `absent_optionals` — `std::optional` fields missing from the file.
- `present_fields` — every field that was found.
- `ok()` — shorthand for `code == kOk`.

Factory: `LoadResult::success()`, `LoadResult::failure(code, msg)`.

### Format detection

`Format::Auto` detects from extension; `Format::Json` / `Format::Yaml` force
a specific parser. Pass to `load()` to override.

### Optional-field audit

`"key": null` in JSON is treated as *present* (DOM-level check). The YAML
loader conflates explicit null with absent — both produce `std::nullopt`.
Nested struct fields get dot-separated paths (e.g. `"server.port"`).

## Supported field types

Any type iguana can deserialize. Common:

| C++ type | CSV type | Notes |
|---|---|---|
| `int32_t` … `int64_t` | `int`/`int8`…`int64` | Fixed-width; CSV `int` → `int32_t` |
| `uint8_t` … `uint64_t` | `uint8`…`uint64` | Fixed-width |
| `double` | `double` | |
| `bool` | `bool` | |
| `std::string` | `string` | |
| `std::vector<int32_t>` | `vector<int>` | |
| `std::vector<std::string>` | `vector<string>` | |
| `std::optional<T>` | (empty default) | Absence tracked in `absent_optionals` |

Integer defaults/min/max are validated at generation time — out-of-range
literals (e.g. `int8` `default=300`) cause the generator to error.

## CSV code generator

`scripts/gen_config.py` reads a CSV schema and emits `YLT_REFL`-annotated
structs + `validate_<Name>()` functions with range checks.

```bash
python3 scripts/gen_config.py --input examples/sample_config.csv --output-dir examples/
```

### CSV columns

| Column | Purpose |
|---|---|
| `field_name` | C++ member name |
| `group` | C++ struct type name **(required, non-empty)** |
| `type` | Built-in type name, or another group name for containment |
| `default` | C++ literal; leave empty for `std::optional<T>` |
| `min` | Inclusive lower bound (integer/double) |
| `max` | Inclusive upper bound (integer/double) |
| `description` | Emitted as a `//` comment |
| `hpp_file` | (optional) Output file name for CSV-driven grouping |

### Containment and nested structs

Set a row's `type` to another group's name to nest that struct as a member.
Example: a row `server, AppConfig, ServerConfig` means "AppConfig has a
`ServerConfig server` member". The root struct is auto-detected.

### Top-level metadata (`__metadata__` rows)

Optional rows before the column header configure global settings:

| Key | Sets |
|---|---|
| `schema_version` | `constexpr k<Name>SchemaVersion` constant + provenance stamp |
| `namespace` | C++ namespace for all generated code |
| `generator` | Name in the provenance stamp |

CLI flags `--namespace` and `--schema-version` override metadata values.

### Output modes

1. **CSV-driven** (highest priority) — groups placed by `hpp_file` column
2. **`--per-struct`** — one `.hpp`/`.cpp` pair per struct
3. **Monolithic** (default) — all structs in one pair

## Formatting

```bash
cmake --build build --target format        # format all hand-written sources
cmake --build build --target check-format  # CI dry-run check
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit  # install hook
```

## License

Apache 2.0 (matching yalantinglibs).
