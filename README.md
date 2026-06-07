# light_config

A header-only C++17 library for loading configuration files directly into
structs. Built on [yalantinglibs](https://github.com/alibaba/yalantinglibs)
(vendored at 0.6.1), it uses compile-time reflection (`YLT_REFL`) so you
never write a line of hand-rolled JSON/YAML parsing.

## Features

- **JSON and YAML support** — same struct, either format.
- **Automatic format detection** — `.json`, `.yaml`, `.yml`; defaults to JSON.
- **Optional-field audit** — know which `std::optional<T>` fields were
  actually present in the config file (JSON: precise DOM-level check;
  YAML: post-load nullopt check).
- **Structured error codes** — machine-readable `ErrorCode` enum with
  numeric ranges for file I/O (1–), JSON errors (10–), YAML errors
  (20–), and validation errors (30–). A `constexpr error_code_message()`
  helper provides human-readable labels.
- **Exception-free public API** — all loader functions catch underlying
  iguana parse exceptions at the boundary and translate them into error
  codes. No exceptions escape the public interface.
- **CSV code generator** — `scripts/gen_config.py` reads a CSV schema,
  emits a `YLT_REFL`-annotated struct plus a `validate_<Name>()` function
  with range checks, and (optionally) generates matching JSON/YAML sample
  configs — valid (defaults) and invalid (out-of-range) — from the same CSV.
  emits a `YLT_REFL`-annotated struct plus a `validate_<Name>()` function
  that checks min/max range constraints and returns a `LoadResult`.
- **Zero external dependencies** — only standard library + vendored headers.
- **Debug-friendly** — built-in VS Code `launch.json` and `tasks.json` for
  lldb-based debugging.

## Supported config field types

Any type that iguana can deserialize from JSON/YAML is supported. Common types:

| C++ type              | Example default       | Notes |
|-----------------------|-----------------------|-------|
| `int`                 | `8080`                | Numeric types support min/max range checks |
| `double`              | `30.0`                | |
| `bool`                | `false`               | |
| `std::string`         | `"0.0.0.0"`           | Quoted in the config file |
| `std::vector<int>`    | (no default)          | Array of values |
| `std::vector<std::string>` | (no default)     | Array of strings |
| `std::optional<T>`    | —                     | Field that may be absent from the file |

A field without a default (`std::optional<T>` or plain `T` with no `= value`)
will be `std::nullopt` / zero-initialized when the key is missing from the
config file.

## Quick start

```cpp
#include <light_config/light_config.hpp>

struct AppConfig {
    std::string host = "0.0.0.0";
    int port          = 8080;
    bool debug        = false;
    std::optional<std::string> log_file;
    std::optional<int>         max_connections;
};
YLT_REFL(AppConfig, host, port, debug, log_file, max_connections);

int main() {
    AppConfig cfg;
    auto r = light_config::load(cfg, "config.json");

    if (!r.ok()) {
        std::cerr << "Config error [" << static_cast<int>(r.code)
                  << "]: " << r.message << '\n';
        return 1;
    }

    // Check which optional fields were missing from the file.
    for (auto& name : r.absent_optionals)
        std::cout << "Using default for: " << name << '\n';
}
```

## Build

```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug
cmake --build build --target example_json    # run the example
cmake --build build --target test_basic      # build tests
./build/tests/test_basic                     # run 13 unit tests
```

CMake requires 3.16+. C++17 toolchain required (Apple Clang 15+, GCC 9+,
MSVC 2019 16.8+).

## API reference

### Loader functions

| Function | Description |
|---|---|
| `load(cfg, path, fmt=Auto)` | Load file; auto-detect format from extension |
| `load_from_json_file(cfg, path)` | Load a JSON file |
| `load_from_yaml_file(cfg, path)` | Load a YAML file |
| `load_from_json_string(cfg, content)` | Load from an in-memory JSON string |
| `load_from_yaml_string(cfg, content)` | Load from an in-memory YAML string |

All functions return a `LoadResult` (exception-free — failures appear as
error codes, never as thrown exceptions).

### ErrorCode

```cpp
enum class ErrorCode {
    kOk = 0,                      // Success.

    // File I/O errors (1–9)
    kFileReadError = 1,           // Cannot access or stat the file.
    kFileEmpty = 2,               // File exists but is empty.

    // JSON errors (10–19)
    kJsonParseError = 10,         // JSON syntax or structural error.
    kJsonDeserializeError = 11,   // JSON parsed OK, but struct population failed.

    // YAML errors (20–29)
    kYamlParseError = 20,         // YAML syntax or structural error.

    // Validation errors (30–)
    kValidationError = 30,        // Config values out of allowed range.
};

// Human-readable label for an ErrorCode (constexpr, noexcept).
constexpr const char* error_code_message(ErrorCode code) noexcept;
```

`error_code_message()` returns an empty string for `kOk` and `"file read
error"` / `"JSON parse error"` / etc. for failure codes. Suitable for
logging or diagnostics.

### LoadResult

```cpp
struct LoadResult {
    ErrorCode code = ErrorCode::kOk;
    std::string message;                       // detail when code != kOk
    std::vector<std::string> absent_optionals; // optional fields missing from the file
    std::vector<std::string> present_fields;   // every field that was found

    bool ok() const noexcept;                  // true when code == kOk
    static LoadResult success();
    static LoadResult failure(ErrorCode c, std::string msg = "");
};
```

When `ok()` returns true, `absent_optionals` and `present_fields` are
populated. When false, `message` carries the reason. Both vectors are
cleared on failure.

### Optional-field audit

Fields declared as `std::optional<T>` but absent from the config file
appear in `absent_optionals` and are set to `std::nullopt`. Fields present
in the file appear in `present_fields`.

The JSON loader parses the file into a DOM first, so `"key": null` is
correctly treated as *present* (not absent). The YAML loader cannot
distinguish absent from explicit null — both cases produce `std::nullopt`
and are reported as absent.

### Format enum

```cpp
enum class Format {
    Auto,   // Detect from file extension (.json / .yaml / .yml); default = JSON.
    Json,   // Force JSON parsing.
    Yaml    // Force YAML parsing.
};
```

Pass `Format::Json` or `Format::Yaml` to `load()` to override auto-detection.

## Config field rules

A field's presence in the config file interacts with its C++ declaration:

| Declaration | Key in file | Behavior |
|---|---|---|
| `T f = v;` | present | `f` = parsed value |
| `T f = v;` | absent | `f` = `v` (default preserved) |
| `T f;` | present | `f` = parsed value |
| `T f;` | absent | `f` = value-initialized (0, empty string, etc.) |
| `std::optional<T> f;` | present | `f` = parsed value |
| `std::optional<T> f;` | absent | `f` = `std::nullopt`, reported in `absent_optionals` |
| `std::optional<T> f;` | key is null (JSON) | `f` = `std::nullopt`, reported in `present_fields` |

## End-to-end validation

The library loads and audits. Range validation can be hand-written or
generated from a CSV schema. Here is a complete pattern combining both:

```cpp
#include <light_config/light_config.hpp>
#include <sstream>
#include <iostream>

struct ServerConfig {
    std::string host = "0.0.0.0";
    int port          = 8080;
    std::optional<int> max_connections;
};
YLT_REFL(ServerConfig, host, port, max_connections);

int main() {
    ServerConfig cfg;
    auto r = light_config::load(cfg, "server.json");
    if (!r.ok()) {
        std::cerr << "Failed to load config: " << r.message << '\n';
        return 1;
    }

    // Warn about missing optional fields.
    for (auto& name : r.absent_optionals)
        std::cerr << "warning: '" << name << "' not set, using default\n";

    // Validate value ranges.
    if (cfg.port < 1024 || cfg.port > 65535) {
        std::cerr << "port out of range [1024, 65535]\n";
        return 1;
    }
    if (cfg.max_connections.has_value()) {
        int v = cfg.max_connections.value();
        if (v < 1 || v > 100000) {
            std::cerr << "max_connections = " << v
                      << " out of range [1, 100000]\n";
            return 1;
        }
    }

    std::cout << "Config loaded successfully.\n";
}
```

## CSV code generator

`scripts/gen_config.py` automates struct definition and range checks.
Given a CSV schema, it produces a header with a `YLT_REFL`-annotated
struct and a `validate_<Name>()` function that returns a `LoadResult`.

### Usage

```bash
python3 scripts/gen_config.py \
  --input scripts/sample_config.csv \
  --struct-name MyConfig \
  --output include/my_config.hpp
```

### CSV columns

| Column | Description |
|---|---|
| `field_name` | C++ member name |
| `type` | `int`, `double`, `bool`, `string`, `vector<string>`, `vector<int>`, `vector<double>` |
| `default` | Literal default value; **leave empty** for `std::optional<T>` |
| `min` | Inclusive lower bound (int/double only; empty = no lower bound) |
| `max` | Inclusive upper bound (int/double only; empty = no upper bound) |
| `description` | Emitted as a `//` comment in the generated header |

### Workflow

1. Define your fields in a CSV:
   ```
   field_name,type,default,min,max,description
   host,string,"0.0.0.0",,,Bind address
   port,int,8080,1024,65535,Listening port
   timeout,double,30.0,0.5,86400,Timeout in seconds
   ```
2. Generate the header:
   ```bash
   python3 scripts/gen_config.py -i schema.csv -s AppConfig -o include/app_config.hpp
   ```
3. Include and use in your application:
   ```cpp
   #include "app_config.hpp"

   AppConfig cfg;
   auto load_r = light_config::load(cfg, "config.json");
   if (!load_r.ok()) return 1;

   auto val_r = validate_AppConfig(cfg);
   if (!val_r.ok()) {
       std::cerr << val_r.message << '\n';
       return 1;
   }
   ```

The generated `validate_<Name>()` function checks all fields that have
`min`/`max` constraints and returns `ErrorCode::kValidationError` with a
multi-line summary of every violated constraint.

## Project layout

```
light_config/
├── CMakeLists.txt
├── scripts/
│   ├── gen_config.py          # CSV → config header generator
│   ├── sample_config.csv      # example CSV schema
│   ├── valid_config.json      # generated: valid config from defaults
│   ├── valid_config.yaml
│   ├── invalid_config.json    # generated: out-of-range values
│   └── invalid_config.yaml
├── include/light_config/
│   ├── light_config.hpp       # public header (auto-detect, all loaders)
│   ├── load_result.hpp        # ErrorCode, LoadResult, Format, type traits
│   ├── json_loader.hpp        # JSON loader + DOM-based optional audit
│   └── yaml_loader.hpp        # YAML loader + post-load optional audit
├── third_party/
│   ├── yalantinglibs/         # vendored yalantinglibs 0.6.1
│   └── versions.txt           # vendored dependency tracking
├── examples/
│   └── example.cpp            # JSON, YAML, auto-detect, error codes, range checks
├── tests/
│   └── test_basic.cpp         # 13 unit tests
└── .vscode/
    ├── launch.json            # lldb debug config for example_json
    └── tasks.json             # pre-launch CMake build task
```

## License

Apache 2.0 (matching yalantinglibs).
