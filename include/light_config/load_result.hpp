#pragma once

#include <optional>
#include <string>
#include <vector>

namespace light_config {

/// Machine-readable error codes for config loading failures.
///
/// The numeric values are stable — integrations may depend on them.
/// Always check code != kOk, never check specific integer values.
///
/// Range allocation policy (documented, enforced by static_assert below):
///   0    — Success
///   1–9  — File I/O errors
///   10–19 — JSON errors
///   20–29 — YAML errors
///   30–39 — Validation errors
///   40–49 — Schema / compatibility errors
enum class ErrorCode {
    kOk = 0,  ///< Success.

    // ---- File I/O errors (range 1–9) ----
    kFileReadError = 1,   ///< Cannot access or stat the file.
    kFileEmpty = 2,       ///< File exists but is empty.
    kFileWriteError = 3,  ///< Cannot open or write to the file.

    // ---- Parse errors ----
    // JSON errors (range 10–19)
    kJsonParseError = 10,        ///< JSON syntax or structural error.
    kJsonDeserializeError = 11,  ///< JSON parsed OK but struct population failed.
    kJsonSerializeError = 12,    ///< Failed to serialize struct to JSON.
    // YAML errors (range 20–29)
    kYamlParseError = 20,      ///< YAML syntax or structural error.
    kYamlSerializeError = 21,  ///< Failed to serialize struct to YAML.

    // ---- Validation errors (range 30–39) ----
    kValidationError = 30,  ///< Config values out of allowed range.
    kSchemaMismatch = 31,   ///< Config file schema version does not match expected.

    // ---- Format / compatibility errors (range 40–49) ----
    kUnrecognizedFormat = 40,  ///< File extension is not a recognized format.
};

// Verify range boundaries — catches accidental drift when new error codes are
// added beyond the allocated range for that category.
static_assert(static_cast<int>(ErrorCode::kFileWriteError) < 10,
              "ErrorCode range violation: File I/O errors must stay in [1, 9]");
static_assert(static_cast<int>(ErrorCode::kJsonSerializeError) < 20,
              "ErrorCode range violation: JSON errors must stay in [10, 19]");
static_assert(static_cast<int>(ErrorCode::kYamlSerializeError) < 30,
              "ErrorCode range violation: YAML errors must stay in [20, 29]");
static_assert(static_cast<int>(ErrorCode::kUnrecognizedFormat) < 50,
              "ErrorCode range violation: Format errors must stay in [40, 49]");

/// Human-readable description for an ErrorCode.
/// Returns empty string for kOk.
constexpr const char* error_code_message(ErrorCode code) noexcept {
    switch (code) {
        case ErrorCode::kOk:
            return "";
        case ErrorCode::kFileReadError:
            return "file read error";
        case ErrorCode::kFileEmpty:
            return "file is empty";
        case ErrorCode::kFileWriteError:
            return "file write error";
        case ErrorCode::kJsonParseError:
            return "JSON parse error";
        case ErrorCode::kJsonDeserializeError:
            return "JSON deserialize error";
        case ErrorCode::kJsonSerializeError:
            return "JSON serialize error";
        case ErrorCode::kYamlParseError:
            return "YAML parse error";
        case ErrorCode::kYamlSerializeError:
            return "YAML serialize error";
        case ErrorCode::kValidationError:
            return "validation error";
        case ErrorCode::kSchemaMismatch:
            return "schema version mismatch";
        case ErrorCode::kUnrecognizedFormat:
            return "unrecognized file format";
    }
    // Fallback for future error codes not yet added to the switch.
    return "unknown error";
}

/// Format of the config file.
enum class Format {
    Auto,  ///< Detect from file extension.
    Json,  ///< JSON format (uses iguana::from_json).
    Yaml   ///< YAML format (uses iguana::from_yaml).
};

/// Result of loading a config file.
///
/// On success: code == kOk, absent_optionals and present_fields are populated.
/// On failure: code != kOk, message carries detail suitable for logging.
struct LoadResult {
    ErrorCode code = ErrorCode::kOk;

    /// Human-readable detail. Set when code != kOk; may be empty.
    std::string message;

    /// Shortcut: true when code == kOk.
    bool ok() const noexcept {
        return code == ErrorCode::kOk;
    }

    /// std::optional fields that were NOT present in the config file.
    ///
    /// JSON: accurate (DOM-level key check).
    /// YAML: fields that were std::nullopt after loading (conflates
    ///       explicit null with missing key).
    std::vector<std::string> absent_optionals;

    /// Fields found in the config file.
    std::vector<std::string> present_fields;

    /// Factory: success result.
    static LoadResult success() {
        return LoadResult{};
    }

    /// Factory: failure with an error code and optional message.
    static LoadResult failure(ErrorCode c, std::string msg = "") {
        LoadResult r;
        r.code = c;
        r.message = std::move(msg);
        return r;
    }
};

// ---- Shared type traits ----

namespace detail {

template <typename T>
struct is_optional : std::false_type {};

template <typename T>
struct is_optional<std::optional<T>> : std::true_type {};

template <typename T>
inline constexpr bool is_optional_v = is_optional<T>::value;

}  // namespace detail

}  // namespace light_config
