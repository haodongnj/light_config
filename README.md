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
./build/examples/example                  # full example
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

All accept an optional `expected_schema_version` — when non-empty, the `"$schema"` key is
checked and mismatches return `ErrorCode::kSchemaMismatch`. The convenience `load_versioned()`
combines format detection with schema enforcement.

### Serialization

| Function | Returns |
|---|---|
| `to_json(cfg, pretty=false)` | `std::optional<std::string>` |
| `to_yaml(cfg)` | `std::optional<std::string>` |
| `save_to_json_file(cfg, path, pretty=true)` | `Result` |
| `save_to_yaml_file(cfg, path)` | `Result` |

### Optional-field audit

`std::optional<T>` fields are tracked: `Result::absent_optionals` lists which were missing
from the file, `Result::present_fields` lists which were found. For JSON, `"key": null` is
**present** (DOM-level check). YAML conflates explicit null with absent. Nested fields get
dot-separated paths (`"server.port"`).

### Error codes

| Code | Name |
|---|---|
| 0 | `kOk` |
| 1–3 | `kFileReadError`, `kFileEmpty`, `kFileWriteError` |
| 10–12 | `kJsonParseError`, `kJsonDeserializeError`, `kJsonSerializeError` |
| 20–21 | `kYamlParseError`, `kYamlSerializeError` |
| 30–31 | `kValidationError`, `kSchemaMismatch` |
| 40 | `kUnrecognizedFormat` |

Ranges enforced by `static_assert`: 1–9 file I/O, 10–19 JSON, 20–29 YAML, 30–39 validation,
40–49 format.

## Supported types

Any type iguana can deserialize: `int32_t`…`int64_t`, `uint8_t`…`uint64_t`, `double`, `bool`,
`std::string`, `std::vector<T>`, `std::optional<T>`, and nested structs annotated with `YLT_REFL`.

## CSV code generator

A Python script that turns a CSV schema into `YLT_REFL`-annotated structs with built-in
validator functions. See [AGENTS.md](AGENTS.md) for details.

## Formatting

C++ code is formatted with **clang-format** (Google-based, 4-space indent, 100 cols).
A pre-commit hook auto-formats staged files on commit:

```bash
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

## License

Apache 2.0 (matching yalantinglibs).
