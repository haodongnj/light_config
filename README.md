# light_config

A header-only C++17 library for loading JSON/YAML config files into structs with
zero hand-written parsing code. Built on [yalantinglibs](https://github.com/alibaba/yalantinglibs)
(vendored 0.6.1).

```cpp
struct MyConfig {
    std::string name;
    int port = 8080;
    std::optional<std::string> host;
};
YLT_REFL(MyConfig, name, port, host);

MyConfig cfg;
auto r = light_config::load(cfg, "config.json");
if (!r.ok()) { /* r.code, r.message */ }
// r.absent_optionals → {"host"}  (std::optional fields missing from file)
```

## Quick start

```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug
cmake --build build
./build/tests/test_basic                    # unit tests
./build/examples/example_json               # full example
```

CMake 3.16+, C++17 required. See [docs/setup-ubuntu-22.04.md](docs/setup-ubuntu-22.04.md) for Ubuntu setup.

## API

All functions return `Result` (`.code`, `.message`, `.absent_optionals`, `.present_fields`, `.ok()`).

### Loading

`light_config::load(cfg, path)` auto-detects format from extension (`.json`, `.yaml`, `.yml`).
Pass `Format::Json` or `Format::Yaml` to override. Also available:

| Function | Source |
|---|---|
| `load_from_json_file(cfg, path)` | File |
| `load_from_yaml_file(cfg, path)` | File |
| `load_from_json_string(cfg, str)` | String |
| `load_from_yaml_string(cfg, str)` | String |

All accept an optional `expected_schema_version` parameter — when non-empty, the `"$schema"`
key is checked and mismatches return `ErrorCode::kSchemaMismatch`. The convenience
`load_versioned()` combines format detection with schema enforcement.

### Serialization

| Function | Returns |
|---|---|
| `to_json(cfg, pretty=false)` | `std::optional<std::string>` |
| `to_yaml(cfg)` | `std::optional<std::string>` |
| `save_to_json_file(cfg, path, pretty=true)` | `Result` |
| `save_to_yaml_file(cfg, path)` | `Result` |

### Optional-field audit

`std::optional<T>` fields are tracked: which were present in the file, which were absent.
For JSON, `"key": null` is **present** (DOM-level check). YAML conflates explicit null with
absent — both produce `std::nullopt`. Nested fields get dot-separated paths (`"server.port"`).

### Error codes

`kOk` (0), `kFileReadError` (1), `kFileEmpty` (2), `kFileWriteError` (3),
`kJsonParseError` (10), `kJsonDeserializeError` (11), `kJsonSerializeError` (12),
`kYamlParseError` (20), `kYamlSerializeError` (21),
`kValidationError` (30), `kSchemaMismatch` (31), `kUnrecognizedFormat` (40).

Ranges enforced by `static_assert`: 1–9 file I/O, 10–19 JSON, 20–29 YAML, 30–39 validation/schema, 40–49 format.

## Supported types

Any type iguana can deserialize. Common:

| C++ type | CSV type |
|---|---|
| `int32_t` … `int64_t` | `int` / `int8`…`int64` |
| `uint8_t` … `uint64_t` | `uint8`…`uint64` |
| `double` | `double` |
| `bool` | `bool` |
| `std::string` | `string` |
| `std::vector<T>` | `vector<T>` |
| `std::optional<T>` | empty default |

## CSV code generator

Turns a CSV schema into `YLT_REFL`-annotated structs with validator functions.

```bash
python3 scripts/gen_config.py --input examples/sample_config.csv --output-dir examples/ --generate-samples
```

CSV columns: `field_name`, `group` (struct name), `type`, `default`, `min`, `max`, `description`, `hpp_file`.
Containment is expressed by setting `type` to another group's name. The root struct is auto-detected.

## Formatting

All C++ code is formatted with **clang-format** (Google-based, 4-space indent, 100 cols).
A pre-commit hook auto-formats staged files on commit:

```bash
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

## License

Apache 2.0 (matching yalantinglibs).
