#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <light_config/light_config.hpp>

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

#include <doctest/doctest.h>
#include <fstream>

/// Config struct exercising various types.
struct TestConfig {
    std::string name;
    int value = 0;
    bool flag = false;
    double ratio = 1.0;
    std::optional<std::string> opt_str;
    std::optional<int> opt_int;
    std::optional<double> opt_double;
    std::vector<int> numbers;
    std::vector<std::string> tags;
};
YLT_REFL(TestConfig, name, value, flag, ratio, opt_str, opt_int, opt_double, numbers, tags);

// A struct with all optional fields.
struct AllOptionalConfig {
    std::optional<std::string> opt_a;
    std::optional<int> opt_b;
};
YLT_REFL(AllOptionalConfig, opt_a, opt_b);

// A struct with no optional fields.
struct NoOptionalConfig {
    std::string a;
    int b = 0;
};
YLT_REFL(NoOptionalConfig, a, b);

// ---- Nested struct for recursive audit testing ----

struct InnerCfg {
    std::string host = "default";
    std::optional<int> port;
};
YLT_REFL(InnerCfg, host, port);

struct OuterCfg {
    std::string app_name;
    int version = 1;
    InnerCfg inner;
};
YLT_REFL(OuterCfg, app_name, version, inner);

// ---- Struct for schema version testing ----

struct InnerVec {
    std::optional<std::vector<std::string>> items;
};
YLT_REFL(InnerVec, items);

struct OuterVec {
    std::string name;
    InnerVec inner;
};
YLT_REFL(OuterVec, name, inner);

struct NestedOptionalVec {
    std::string label;
    std::optional<InnerVec> inner;
    std::optional<std::vector<int>> values;
};
YLT_REFL(NestedOptionalVec, label, inner, values);

struct VersionedConfig {
    std::string name;
    int value = 0;
};
YLT_REFL(VersionedConfig, name, value);
// Simulates what gen_config.py emits:
constexpr std::string_view kVersionedConfigSchemaVersion{"2.0.0"};

// ============================================================================
// JSON Tests
// ============================================================================

TEST_CASE("JSON all fields present") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "test",
        "value": 42,
        "flag": true,
        "ratio": 2.5,
        "opt_str": "hello",
        "opt_int": 99,
        "opt_double": 1.5,
        "numbers": [1, 2, 3],
        "tags": ["a", "b"]
    })");
    CHECK(r.ok());
    CHECK(r.code == light_config::ErrorCode::kOk);
    CHECK(cfg.name == "test");
    CHECK(cfg.value == 42);
    CHECK(cfg.flag);
    CHECK(cfg.ratio == 2.5);
    CHECK(cfg.opt_str.has_value());
    CHECK(cfg.opt_str.value() == "hello");
    CHECK(cfg.opt_int.has_value());
    CHECK(cfg.opt_int.value() == 99);
    CHECK(cfg.opt_double.has_value());
    CHECK(cfg.opt_double.value() == 1.5);
    CHECK(cfg.numbers.size() == 3);
    CHECK(cfg.tags.size() == 2);
    CHECK(r.absent_optionals.empty());
    CHECK(r.present_fields.size() == 9);
}

TEST_CASE("JSON some optionals absent") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "minimal",
        "value": 1,
        "flag": false
    })");
    CHECK(r.ok());
    CHECK(cfg.name == "minimal");
    CHECK(cfg.value == 1);
    CHECK(cfg.flag == false);
    CHECK(!cfg.opt_str.has_value());
    CHECK(!cfg.opt_int.has_value());
    CHECK(!cfg.opt_double.has_value());
    CHECK(r.absent_optionals.size() == 3);
    CHECK(r.present_fields.size() == 3);
}

TEST_CASE("JSON optional explicit null = present") {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "opt_a": null,
        "opt_b": 5
    })");
    CHECK(r.ok());
    CHECK(!cfg.opt_a.has_value());
    CHECK(cfg.opt_b.has_value());
    CHECK(cfg.opt_b.value() == 5);
    CHECK(r.present_fields.size() == 2);
    CHECK(r.absent_optionals.empty());
}

TEST_CASE("JSON empty object") {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({})");
    CHECK(r.ok());
    CHECK(!cfg.opt_a.has_value());
    CHECK(!cfg.opt_b.has_value());
    CHECK(r.absent_optionals.size() == 2);
    CHECK(r.present_fields.empty());
}

TEST_CASE("JSON no optional fields") {
    NoOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({"a": "x", "b": 10})");
    CHECK(r.ok());
    CHECK(cfg.a == "x");
    CHECK(cfg.b == 10);
    CHECK(r.absent_optionals.empty());
    CHECK(r.present_fields.size() == 2);
}

TEST_CASE("error_code_message for new save-related codes") {
    using EC = light_config::ErrorCode;
    CHECK(light_config::error_code_message(EC::kFileWriteError) == std::string("file write error"));
    CHECK(light_config::error_code_message(EC::kJsonSerializeError)
          == std::string("JSON serialize error"));
    CHECK(light_config::error_code_message(EC::kYamlSerializeError)
          == std::string("YAML serialize error"));
}

TEST_CASE("JSON parse error") {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, "{invalid");
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kJsonParseError);
    CHECK(!r.message.empty());
}

TEST_CASE("JSON missing file error") {
    TestConfig cfg;
    auto r = light_config::load_from_json_file(cfg, "/nonexistent/path.json");
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kFileReadError);
    CHECK(!r.message.empty());
}

TEST_CASE("save_to_json_file: write to directory path fails") {
    // Create a directory with a file-like name — opening it as an ofstream
    // must fail.
    namespace fs = std::filesystem;
    const auto dir = fs::temp_directory_path() / "light_config_test_save_dir";
    fs::create_directory(dir);

    TestConfig cfg;
    cfg.name = "test";
    auto r = light_config::save_to_json_file(cfg, dir.string(), false);

    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kFileWriteError);
    CHECK(!r.message.empty());

    fs::remove(dir);
}

TEST_CASE("save_to_yaml_file: write to directory path fails") {
    namespace fs = std::filesystem;
    const auto dir = fs::temp_directory_path() / "light_config_test_save_yaml_dir";
    fs::create_directory(dir);

    TestConfig cfg;
    cfg.name = "yaml_test";
    auto r = light_config::save_to_yaml_file(cfg, dir.string());

    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kFileWriteError);
    CHECK(!r.message.empty());

    fs::remove(dir);
}

TEST_CASE("save_to_json_file: write to read-only directory") {
    namespace fs = std::filesystem;
    // Skip if running as root (root can write anywhere).
    if (geteuid() == 0) {
        MESSAGE("Skipping read-only-directory test (running as root)");
        return;
    }
    const auto dir = fs::temp_directory_path() / "light_config_test_readonly_dir";
    fs::create_directory(dir);
    fs::permissions(dir, fs::perms::owner_read | fs::perms::owner_exec);

    const auto path = dir / "should_fail.json";
    TestConfig cfg;
    cfg.name = "test_ro";
    auto r = light_config::save_to_json_file(cfg, path.string(), false);

    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kFileWriteError);
    CHECK(!r.message.empty());

    fs::permissions(dir, fs::perms::owner_all);
    fs::remove_all(dir);
}

TEST_CASE("save_to_yaml_file: write to read-only directory") {
    namespace fs = std::filesystem;
    if (geteuid() == 0) {
        MESSAGE("Skipping read-only-directory test (running as root)");
        return;
    }
    const auto dir = fs::temp_directory_path() / "light_config_test_readonly_dir_yaml";
    fs::create_directory(dir);
    fs::permissions(dir, fs::perms::owner_read | fs::perms::owner_exec);

    const auto path = dir / "should_fail.yaml";
    TestConfig cfg;
    cfg.name = "yaml_ro_test";
    auto r = light_config::save_to_yaml_file(cfg, path.string());

    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kFileWriteError);
    CHECK(!r.message.empty());

    fs::permissions(dir, fs::perms::owner_all);
    fs::remove_all(dir);
}

TEST_CASE("JSON nested struct all present") {
    OuterCfg cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "app_name": "myapp",
        "version": 2,
        "inner": {
            "host": "10.0.0.1",
            "port": 9999
        }
    })");
    CHECK(r.ok());
    CHECK(cfg.app_name == "myapp");
    CHECK(cfg.version == 2);
    CHECK(cfg.inner.host == "10.0.0.1");
    CHECK(cfg.inner.port.has_value());
    CHECK(cfg.inner.port.value() == 9999);
    // Check dot-separated field paths for nested fields
    // present: app_name, version, inner, inner.host, inner.port
    CHECK(r.present_fields.size() == 5);
    CHECK(r.absent_optionals.empty());
}

TEST_CASE("JSON nested struct: inner.port absent") {
    OuterCfg cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "app_name": "myapp",
        "inner": {
            "host": "10.0.0.1"
        }
    })");
    CHECK(r.ok());
    CHECK(cfg.app_name == "myapp");
    CHECK(cfg.inner.host == "10.0.0.1");
    CHECK(!cfg.inner.port.has_value());
    // inner.port is absent from JSON
    bool has_port_absent = false;
    for (auto& name : r.absent_optionals) {
        if (name == "inner.port") {
            has_port_absent = true;
        }
    }
    CHECK(has_port_absent);
}

// ============================================================================
// Round-Trip Tests
// ============================================================================

TEST_CASE("Round-trip: JSON basic serialization + re-parse") {
    TestConfig original;
    original.name = "roundtrip";
    original.value = 42;
    original.flag = true;
    original.ratio = 3.14;
    original.opt_str = "hello";
    original.opt_int = 99;
    original.opt_double = 1.5;
    original.numbers = {1, 2, 3};
    original.tags = {"x", "y"};

    auto json_opt = light_config::to_json(original);
    REQUIRE(json_opt.has_value());

    TestConfig parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    CHECK(r.ok());

    CHECK(parsed.name == original.name);
    CHECK(parsed.value == original.value);
    CHECK(parsed.flag == original.flag);
    CHECK(parsed.ratio == original.ratio);
    CHECK(parsed.opt_str.has_value());
    CHECK(parsed.opt_str.value() == "hello");
    CHECK(parsed.opt_int.has_value());
    CHECK(parsed.opt_int.value() == 99);
    CHECK(parsed.opt_double.has_value());
    CHECK(parsed.opt_double.value() == 1.5);
    CHECK(parsed.numbers.size() == 3);
    CHECK(parsed.numbers[0] == 1);
    CHECK(parsed.numbers[1] == 2);
    CHECK(parsed.numbers[2] == 3);
    CHECK(parsed.tags.size() == 2);
    CHECK(parsed.tags[0] == "x");
    CHECK(parsed.tags[1] == "y");
}

TEST_CASE("Round-trip: JSON pretty-print survives re-parse") {
    TestConfig original;
    original.name = "pretty_test";
    original.value = 7;
    original.flag = false;
    original.ratio = 2.0;
    original.opt_str = "present";
    original.opt_int = 10;
    original.opt_double = 3.5;
    original.numbers = {1, 2};
    original.tags = {"x"};

    auto json_opt = light_config::to_json(original, true);
    REQUIRE(json_opt.has_value());

    // Pretty JSON should contain newlines.
    CHECK(json_opt.value().find('\n') != std::string::npos);

    TestConfig parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    CHECK(r.ok());
    CHECK(parsed.name == original.name);
    CHECK(parsed.value == original.value);
    CHECK(parsed.flag == original.flag);
    CHECK(parsed.ratio == original.ratio);
    CHECK(parsed.opt_str.has_value());
    CHECK(parsed.opt_str.value() == "present");
    CHECK(parsed.opt_int.has_value());
    CHECK(parsed.opt_int.value() == 10);
    CHECK(parsed.opt_double.has_value());
    CHECK(parsed.opt_double.value() == 3.5);
    CHECK(parsed.numbers.size() == 2);
    CHECK(parsed.tags.size() == 1);
}

TEST_CASE("Round-trip: JSON all-optional struct (filled + empty)") {
    // All optional fields populated.
    AllOptionalConfig original;
    original.opt_a = "alpha";
    original.opt_b = 100;

    auto json_opt = light_config::to_json(original);
    REQUIRE(json_opt.has_value());

    AllOptionalConfig parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    CHECK(r.ok());
    CHECK(parsed.opt_a.has_value());
    CHECK(parsed.opt_a.value() == "alpha");
    CHECK(parsed.opt_b.has_value());
    CHECK(parsed.opt_b.value() == 100);

    // All optional fields empty.
    AllOptionalConfig empty;
    json_opt = light_config::to_json(empty);
    REQUIRE(json_opt.has_value());

    AllOptionalConfig parsed_empty;
    r = light_config::load_from_json_string(parsed_empty, json_opt.value());
    CHECK(r.ok());
    CHECK(!parsed_empty.opt_a.has_value());
    CHECK(!parsed_empty.opt_b.has_value());
}

TEST_CASE("Round-trip: JSON nested struct survives re-parse") {
    OuterCfg original;
    original.app_name = "nested_app";
    original.version = 3;
    original.inner.host = "192.168.1.1";
    original.inner.port = 8080;

    auto json_opt = light_config::to_json(original);
    REQUIRE(json_opt.has_value());

    OuterCfg parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    CHECK(r.ok());
    CHECK(parsed.app_name == original.app_name);
    CHECK(parsed.version == original.version);
    CHECK(parsed.inner.host == original.inner.host);
    CHECK(parsed.inner.port.has_value());
    CHECK(parsed.inner.port.value() == 8080);
}

TEST_CASE("Round-trip: YAML serialization + re-parse") {
    TestConfig original;
    original.name = "yaml_rt";
    original.value = 99;
    original.flag = true;
    original.ratio = 1.0;
    original.opt_str = "yamltest";
    original.numbers = {10, 20};
    original.tags = {"a", "b", "c"};

    auto yaml_opt = light_config::to_yaml(original);
    REQUIRE(yaml_opt.has_value());

    TestConfig parsed;
    auto r = light_config::load_from_yaml_string(parsed, yaml_opt.value());
    CHECK(r.ok());
    CHECK(parsed.name == original.name);
    CHECK(parsed.value == original.value);
    CHECK(parsed.flag == original.flag);
    CHECK(parsed.ratio == original.ratio);
    CHECK(parsed.opt_str.has_value());
    CHECK(parsed.opt_str.value() == "yamltest");
    CHECK(parsed.numbers.size() == 2);
    CHECK(parsed.tags.size() == 3);
}

TEST_CASE("Round-trip: JSON file save + load") {
    const std::string path =
        (std::filesystem::temp_directory_path() / "light_config_test_rt.json").string();

    TestConfig original;
    original.name = "file_rt";
    original.value = 55;
    original.flag = true;

    auto r_save = light_config::save_to_json_file(original, path, false);
    CHECK(r_save.ok());

    TestConfig parsed;
    auto r = light_config::load_from_json_file(parsed, path);
    CHECK(r.ok());
    CHECK(parsed.name == original.name);
    CHECK(parsed.value == original.value);
    CHECK(parsed.flag == original.flag);
}

TEST_CASE("Round-trip: YAML file save + load") {
    const std::string path =
        (std::filesystem::temp_directory_path() / "light_config_test_rt.yaml").string();

    TestConfig original;
    original.name = "yaml_file_rt";
    original.value = 123;
    original.flag = false;

    auto r_save = light_config::save_to_yaml_file(original, path);
    CHECK(r_save.ok());

    TestConfig parsed;
    auto r = light_config::load_from_yaml_file(parsed, path);
    CHECK(r.ok());
    CHECK(parsed.name == original.name);
    CHECK(parsed.value == original.value);
    CHECK(parsed.flag == original.flag);
}

// ============================================================================
// YAML Tests
// ============================================================================

TEST_CASE("YAML basic load") {
    TestConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
name: yaml_test
value: 100
flag: true
ratio: 3.14
opt_str: "present"
numbers:
  - 1
  - 2
tags:
  - "tag1"
  - "tag2"
)");
    CHECK(r.ok());
    CHECK(cfg.name == "yaml_test");
    CHECK(cfg.value == 100);
    CHECK(cfg.opt_str.has_value());
    CHECK(cfg.opt_str.value() == "present");
    CHECK(cfg.numbers.size() == 2);
    CHECK(r.present_fields.size() == 7);
    CHECK(r.absent_optionals.size() == 2);
}

TEST_CASE("YAML empty document") {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, "");
    CHECK(r.ok());
    CHECK(r.absent_optionals.size() == 2);
}

// ============================================================================
// Format Auto-Detection
// ============================================================================

TEST_CASE("Auto-detect JSON (.json)") {
    const std::string path =
        (std::filesystem::temp_directory_path() / "light_config_test_auto.json").string();
    {
        std::ofstream f(path);
        f << R"({"name": "auto", "value": 1, "flag": false})";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    CHECK(r.ok());
    CHECK(cfg.name == "auto");
}

TEST_CASE("Auto-detect YAML (.yaml)") {
    const std::string path =
        (std::filesystem::temp_directory_path() / "light_config_test_auto.yaml").string();
    {
        std::ofstream f(path);
        f << "name: auto_yaml\nvalue: 2\nflag: true\n";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    CHECK(r.ok());
    CHECK(cfg.name == "auto_yaml");
}

TEST_CASE("Auto-detect YAML (.yml)") {
    const std::string path =
        (std::filesystem::temp_directory_path() / "light_config_test_auto.yml").string();
    {
        std::ofstream f(path);
        f << "name: auto_yml\nvalue: 3\nflag: false\n";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    CHECK(r.ok());
    CHECK(cfg.name == "auto_yml");
}

TEST_CASE("Auto-detect no extension -> JSON") {
    const std::string path =
        (std::filesystem::temp_directory_path() / "light_config_test_auto_noext").string();
    {
        std::ofstream f(path);
        f << R"({"name": "noext", "value": 4, "flag": true})";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    CHECK(r.ok());
    CHECK(cfg.name == "noext");
}

// ============================================================================
// Schema Version Tests
// ============================================================================

TEST_CASE("Schema version: JSON match succeeds") {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": "2.0.0",
        "name": "test",
        "value": 42
    })",
                                                 kVersionedConfigSchemaVersion);
    CHECK(r.ok());
    CHECK(r.code == light_config::ErrorCode::kOk);
    CHECK(cfg.name == "test");
    CHECK(cfg.value == 42);
}

TEST_CASE("Schema version: JSON mismatch rejected") {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": "1.0.0",
        "name": "test",
        "value": 42
    })",
                                                 kVersionedConfigSchemaVersion);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kSchemaMismatch);
    CHECK(!r.message.empty());
    // Message should mention both versions.
    CHECK(r.message.find("2.0.0") != std::string::npos);
    CHECK(r.message.find("1.0.0") != std::string::npos);
}

TEST_CASE("Schema version: missing $schema key proceeds (permissive)") {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "no_schema",
        "value": 99
    })",
                                                 kVersionedConfigSchemaVersion);
    CHECK(r.ok());
    CHECK(cfg.name == "no_schema");
    CHECK(cfg.value == 99);
}

TEST_CASE("Schema version: empty expected skips check") {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": "anything",
        "name": "test",
        "value": 1
    })");  // default: expected_schema_version = ""
    CHECK(r.ok());
}

TEST_CASE("Schema version: non-string $schema ignored") {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": 42,
        "name": "test",
        "value": 1
    })",
                                                 kVersionedConfigSchemaVersion);
    // $schema is a number, not a string → is_string() check skips it.
    CHECK(r.ok());
}

TEST_CASE("Schema version: YAML match succeeds") {
    VersionedConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
$schema: 2.0.0
name: yaml_test
value: 7
)",
                                                 kVersionedConfigSchemaVersion);
    CHECK(r.ok());
    CHECK(cfg.name == "yaml_test");
    CHECK(cfg.value == 7);
}

TEST_CASE("Schema version: YAML mismatch rejected") {
    VersionedConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
$schema: 9.9.9
name: yaml_test
value: 7
)",
                                                 kVersionedConfigSchemaVersion);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kSchemaMismatch);
}

TEST_CASE("Schema version: load_versioned JSON match") {
    const std::string path =
        (std::filesystem::temp_directory_path() / "light_config_test_schema.json").string();
    {
        std::ofstream f(path);
        f << R"({"$schema": "2.0.0", "name": "file_test", "value": 5})";
    }
    VersionedConfig cfg;
    auto r = light_config::load_versioned(cfg, path, kVersionedConfigSchemaVersion);
    CHECK(r.ok());
    CHECK(cfg.value == 5);
}

// ============================================================================
// Nested optional-with-vector tests
// ============================================================================

TEST_CASE("Nested optional vector: all fields present") {
    OuterVec cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "outer",
        "inner": {
            "items": ["a", "b", "c"]
        }
    })");
    CHECK(r.ok());
    CHECK(cfg.name == "outer");
    CHECK(cfg.inner.items.has_value());
    CHECK(cfg.inner.items.value().size() == 3);
    CHECK(cfg.inner.items.value()[0] == "a");
    CHECK(cfg.inner.items.value()[1] == "b");
    CHECK(cfg.inner.items.value()[2] == "c");
    // present: name, inner, inner.items
    CHECK(r.present_fields.size() == 3);
    CHECK(r.absent_optionals.empty());
}

TEST_CASE("Nested optional vector: inner.items absent") {
    OuterVec cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "outer",
        "inner": {}
    })");
    CHECK(r.ok());
    CHECK(cfg.name == "outer");
    CHECK(!cfg.inner.items.has_value());
    // absent: inner.items
    CHECK(r.absent_optionals.size() == 1);
    CHECK(r.absent_optionals[0] == "inner.items");
}

TEST_CASE("Nested optional vector: inner.items is empty array") {
    OuterVec cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "outer",
        "inner": {
            "items": []
        }
    })");
    CHECK(r.ok());
    CHECK(cfg.inner.items.has_value());
    CHECK(cfg.inner.items.value().empty());
    CHECK(r.present_fields.size() == 3);
    CHECK(r.absent_optionals.empty());
}

TEST_CASE("Nested optional vector: optional inner entirely absent") {
    NestedOptionalVec cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "label": "test",
        "values": [1, 2, 3]
    })");
    CHECK(r.ok());
    CHECK(cfg.label == "test");
    CHECK(!cfg.inner.has_value());
    CHECK(cfg.values.has_value());
    CHECK(cfg.values.value().size() == 3);
    // absent: inner (the optional<InnerVec> itself)
    bool has_inner_absent = false;
    for (auto& name : r.absent_optionals) {
        if (name == "inner")
            has_inner_absent = true;
    }
    CHECK(has_inner_absent);
    // present: label, values
    CHECK(r.present_fields.size() == 2);
}

TEST_CASE("Nested optional vector: all absent") {
    NestedOptionalVec cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "label": "bare"
    })");
    CHECK(r.ok());
    CHECK(cfg.label == "bare");
    CHECK(!cfg.inner.has_value());
    CHECK(!cfg.values.has_value());
    // absent: inner, values
    CHECK(r.absent_optionals.size() == 2);
    CHECK(r.present_fields.size() == 1);
}

// ============================================================================
// Enum Tests
// ============================================================================

// ---- Enum types for testing ----

enum class TestPriority { low, normal, high, critical };
template <>
struct iguana::enum_value<TestPriority> {
    constexpr static std::array<int, 4> value = {0, 1, 2, 3};
};

struct EnumConfig {
    TestPriority priority = TestPriority::normal;
    int retries = 3;
};
YLT_REFL(EnumConfig, priority, retries);

TEST_CASE("enums: JSON load with valid enum value") {
    EnumConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({"priority": "high", "retries": 5})");
    CHECK(r.ok());
    CHECK(cfg.priority == TestPriority::high);
    CHECK(cfg.retries == 5);
    CHECK(r.present_fields.size() == 2);
}

TEST_CASE("enums: JSON load with invalid enum value fails") {
    EnumConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({"priority": "unknown", "retries": 5})");
    CHECK(!r.ok());
}

TEST_CASE("enums: YAML load with valid enum value") {
    EnumConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, "priority: critical\nretries: 10");
    CHECK(r.ok());
    CHECK(cfg.priority == TestPriority::critical);
    CHECK(cfg.retries == 10);
}

TEST_CASE("enums: JSON round-trip preserves enum as string") {
    EnumConfig cfg;
    cfg.priority = TestPriority::low;
    cfg.retries = 1;
    auto json = light_config::to_json(cfg).value();
    CHECK(json.find("\"low\"") != std::string::npos);
    EnumConfig cfg2;
    auto r = light_config::load_from_json_string(cfg2, json);
    CHECK(r.ok());
    CHECK(cfg2.priority == TestPriority::low);
    CHECK(cfg2.retries == 1);
}

TEST_CASE("enums: YAML round-trip preserves enum as string") {
    EnumConfig cfg;
    cfg.priority = TestPriority::critical;
    cfg.retries = 7;
    auto yaml = light_config::to_yaml(cfg).value();
    CHECK(yaml.find("critical") != std::string::npos);
    EnumConfig cfg2;
    auto r = light_config::load_from_yaml_string(cfg2, yaml);
    CHECK(r.ok());
    CHECK(cfg2.priority == TestPriority::critical);
    CHECK(cfg2.retries == 7);
}
