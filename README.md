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
| `int32_t` (`int`)     | `8080`                | Fixed-width via `<cstdint>`. `int` is a synonym for `int32`. Numeric types support min/max range checks |
| `int8_t` … `int64_t`  | `0`                   | Explicit-width CSV types `int8`/`int16`/`int32`/`int64` |
| `uint8_t` … `uint64_t`| `0`                   | Explicit-width CSV types `uint8`/`uint16`/`uint32`/`uint64` |
| `double`              | `30.0`                | |
| `bool`                | `false`               | |
| `std::string`         | `"0.0.0.0"`           | Quoted in the config file |
| `std::vector<int32_t>`| (no default)          | CSV `vector<int>`; array of fixed-width ints |
| `std::vector<std::string>` | (no default)     | Array of strings |
| `std::optional<T>`    | —                     | Field that may be absent from the file |

Integer config fields are emitted as fixed-width `<cstdint>` typedefs
(`int32_t`, `uint16_t`, …) rather than the implementation-defined-width `int`,
so a calibration parameter's range is portable across ECU toolchains
(MISRA/AUTOSAR-friendly). `int` remains a valid CSV type and is a synonym for
`int32` → `int32_t`. The generator rejects `default`/`min`/`max` literals that
do not fit the declared width (e.g. `int8` with `default=300`).

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

The library loads and audits; validation is generated from CSV. Here is the
complete pattern using a generated compound config header:

```cpp
#include <light_config/light_config.hpp>
#include "app_config.hpp"  // generated from CSV
#include <iostream>

int main() {
    AppConfig cfg;
    auto r = light_config::load(cfg, "config.json");
    if (!r.ok()) {
        std::cerr << "Failed to load config: " << r.message << '\n';
        return 1;
    }

    // Warn about missing optional fields (including nested, dot-separated).
    for (auto& name : r.absent_optionals)
        std::cerr << "warning: '" << name << "' not set, using default\n";

    // Validate all range constraints — recurses into Server and Connection.
    auto v = validate_AppConfig(cfg);
    if (!v.ok()) {
        std::cerr << v.message << '\n';
        return 1;
    }

    std::cout << "Config loaded and validated successfully.\n";
}
```

## CSV code generator

`scripts/gen_config.py` automates struct definition and range checks.
Given a CSV schema, it produces a header with a `YLT_REFL`-annotated
struct and a `validate_<Name>()` function that returns a `LoadResult`.

### Usage

```bash
python3 scripts/gen_config.py \
  --input examples/sample_config.csv \
   MyConfig \
  --output include/my_config.hpp
```

### CSV columns

| Column | Description |
|---|---|
| `field_name` | C++ member name |
| `type` | `int` (→ `int32_t`), `int8`/`int16`/`int32`/`int64`/`uint8`/`uint16`/`uint32`/`uint64`, `double`, `bool`, `string`, `vector<string>`, `vector<int>`, `vector<double>` |
| `default` | Literal default value; **leave empty** for `std::optional<T>`. For integer width types the literal must fit the declared width or the generator errors out. |
| `min` | Inclusive lower bound (integer / double types; empty = no lower bound) |
| `max` | Inclusive upper bound (integer / double types; empty = no upper bound) |
| `description` | Emitted as a `//` comment in the generated header |
| `group` | The exact C++ struct type name (e.g. `ServerConfig`, `ConnectionConfig`). Every row must have a non-empty `group` value. |

### Nested structs

When rows share a non-empty `group` value, the generator creates a separate
nested struct for each group, each with its own `YLT_REFL` macro. The parent
struct includes the nested struct as a member named after the group.

Example CSV with containment expressed via the `type` column:

```csv
field_name,group,type,default,min,max,description
backend,AppConfig,ServerConfig,,,,Backend server config
host,ServerConfig,string,"localhost",,,Backend hostname
port,ServerConfig,int,8080,1,65535,Backend port
```

The row `backend,AppConfig,ServerConfig` means: "AppConfig contains a
member named `backend` of type `ServerConfig`".  The root struct is
auto-detected as the group that no other group references.

Generates:

```cpp
struct ServerConfig {
    std::string host = "localhost";
    int port = 8080;
};
YLT_REFL(ServerConfig, host, port);

struct AppConfig {
    // ... own fields ...
    ServerConfig backend;
};
YLT_REFL(AppConfig, ..., backend);
```

The `validate_AppConfig()` function automatically calls `validate_Server()`
to recurse into nested struct members.

When loading configs with nested structs, `absent_optionals` and
`present_fields` use dot-separated paths (e.g., `"server.port"`,
`"server.host"`) to identify nested fields.


### Workflow

1. Define your fields in a CSV (top-level and grouped):
   ```csv
   field_name,group,type,default,min,max,description
   debug,AppConfig,bool,false,,,Enable debug logging
   server,AppConfig,ServerConfig,,,,Backend server
   host,ServerConfig,string,"0.0.0.0",,,Bind address
   port,ServerConfig,int,8080,1024,65535,Listening port
   ```
2. Generate the header (root is auto-detected from containment):
   ```bash
   python3 scripts/gen_config.py -i schema.csv -o include/app_config.hpp
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


## License

Apache 2.0 (matching yalantinglibs).
