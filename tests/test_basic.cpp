#include <cassert>
#include <iostream>
#include <optional>
#include <string>
#include <vector>
#include <fstream>

#include <light_config/light_config.hpp>

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
YLT_REFL(TestConfig, name, value, flag, ratio,
         opt_str, opt_int, opt_double, numbers, tags);

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

// ---- JSON Tests ----

void test_json_all_fields_present() {
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
    assert(r.ok());
    assert(r.code == light_config::ErrorCode::kOk);
    assert(cfg.name == "test");
    assert(cfg.value == 42);
    assert(cfg.flag == true);
    assert(cfg.ratio == 2.5);
    assert(cfg.opt_str.has_value() && cfg.opt_str.value() == "hello");
    assert(cfg.opt_int.has_value() && cfg.opt_int.value() == 99);
    assert(cfg.opt_double.has_value() && cfg.opt_double.value() == 1.5);
    assert(cfg.numbers.size() == 3);
    assert(cfg.tags.size() == 2);
    assert(r.absent_optionals.empty());
    assert(r.present_fields.size() == 9);
    std::cout << "[PASS] JSON all fields present.\n";
}

void test_json_some_optionals_absent() {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "minimal",
        "value": 1,
        "flag": false
    })");
    assert(r.ok());
    assert(cfg.name == "minimal");
    assert(cfg.value == 1);
    assert(cfg.flag == false);
    assert(!cfg.opt_str.has_value());
    assert(!cfg.opt_int.has_value());
    assert(!cfg.opt_double.has_value());
    assert(r.absent_optionals.size() == 3);
    assert(r.present_fields.size() == 3);
    std::cout << "[PASS] JSON optional fields absent.\n";
}

void test_json_optional_explicit_null() {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "opt_a": null,
        "opt_b": 5
    })");
    assert(r.ok());
    assert(!cfg.opt_a.has_value());
    assert(cfg.opt_b.has_value() && cfg.opt_b.value() == 5);
    assert(r.present_fields.size() == 2);
    assert(r.absent_optionals.empty());
    std::cout << "[PASS] JSON optional explicit null = present.\n";
}

void test_json_all_optional() {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({})");
    assert(r.ok());
    assert(!cfg.opt_a.has_value());
    assert(!cfg.opt_b.has_value());
    assert(r.absent_optionals.size() == 2);
    assert(r.present_fields.empty());
    std::cout << "[PASS] JSON empty object.\n";
}

void test_json_no_optionals() {
    NoOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({"a": "x", "b": 10})");
    assert(r.ok());
    assert(cfg.a == "x");
    assert(cfg.b == 10);
    assert(r.absent_optionals.empty());
    assert(r.present_fields.size() == 2);
    std::cout << "[PASS] JSON no optional fields.\n";
}

void test_json_parse_error() {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, "{invalid");
    assert(!r.ok());
    assert(r.code == light_config::ErrorCode::kJsonParseError);
    assert(!r.message.empty());
    std::cout << "[PASS] JSON parse error reported: " << r.message << "\n";
}

void test_json_missing_file() {
    TestConfig cfg;
    auto r = light_config::load_from_json_file(cfg, "/nonexistent/path.json");
    assert(!r.ok());
    assert(r.code == light_config::ErrorCode::kFileReadError);
    assert(!r.message.empty());
    std::cout << "[PASS] JSON missing file error reported.\n";
}

// ---- Nested struct tests ----

void test_json_nested_all_present() {
    OuterCfg cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "app_name": "myapp",
        "version": 2,
        "inner": {
            "host": "10.0.0.1",
            "port": 9999
        }
    })");
    assert(r.ok());
    assert(cfg.app_name == "myapp");
    assert(cfg.version == 2);
    assert(cfg.inner.host == "10.0.0.1");
    assert(cfg.inner.port.has_value() && cfg.inner.port.value() == 9999);
    // Check dot-separated field paths for nested fields
    assert(r.present_fields.size() == 5);  // app_name, version, inner, inner.host, inner.port
    assert(r.absent_optionals.empty());
    std::cout << "[PASS] JSON nested struct all present.\n";
}

void test_json_nested_some_absent() {
    OuterCfg cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "app_name": "myapp",
        "inner": {
            "host": "10.0.0.1"
        }
    })");
    assert(r.ok());
    assert(cfg.app_name == "myapp");
    assert(cfg.inner.host == "10.0.0.1");
    assert(!cfg.inner.port.has_value());
    // inner.port is absent from JSON
    auto has_port_absent = false;
    for (auto& name : r.absent_optionals) {
        if (name == "inner.port") has_port_absent = true;
    }
    assert(has_port_absent);
    std::cout << "[PASS] JSON nested struct: inner.port absent.\n";
}

// ---- YAML Tests ----

void test_yaml_basic() {
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
    assert(r.ok());
    assert(cfg.name == "yaml_test");
    assert(cfg.value == 100);
    assert(cfg.opt_str.has_value() && cfg.opt_str.value() == "present");
    assert(cfg.numbers.size() == 2);
    assert(r.present_fields.size() == 7);
    assert(r.absent_optionals.size() == 2);
    std::cout << "[PASS] YAML basic load.\n";
}

void test_yaml_empty() {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, "");
    assert(r.ok());
    assert(r.absent_optionals.size() == 2);
    std::cout << "[PASS] YAML empty document.\n";
}

// ---- Format Auto-Detection ----

void test_auto_detect_json() {
    const std::string path = "/tmp/light_config_test_auto.json";
    {
        std::ofstream f(path);
        f << R"({"name": "auto", "value": 1, "flag": false})";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "auto");
    std::cout << "[PASS] Auto-detect JSON (.json).\n";
}

void test_auto_detect_yaml() {
    const std::string path = "/tmp/light_config_test_auto.yaml";
    {
        std::ofstream f(path);
        f << "name: auto_yaml\nvalue: 2\nflag: true\n";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "auto_yaml");
    std::cout << "[PASS] Auto-detect YAML (.yaml).\n";
}

void test_auto_detect_yml() {
    const std::string path = "/tmp/light_config_test_auto.yml";
    {
        std::ofstream f(path);
        f << "name: auto_yml\nvalue: 3\nflag: false\n";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "auto_yml");
    std::cout << "[PASS] Auto-detect YAML (.yml).\n";
}

void test_auto_detect_no_extension() {
    const std::string path = "/tmp/light_config_test_auto_noext";
    {
        std::ofstream f(path);
        f << R"({"name": "noext", "value": 4, "flag": true})";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "noext");
    std::cout << "[PASS] Auto-detect no extension -> JSON.\n";
}

int main() {
    // JSON
    test_json_all_fields_present();
    test_json_some_optionals_absent();
    test_json_optional_explicit_null();
    test_json_all_optional();
    test_json_no_optionals();
    test_json_parse_error();
    test_json_missing_file();

    // Nested struct
    test_json_nested_all_present();
    test_json_nested_some_absent();

    // YAML
    test_yaml_basic();
    test_yaml_empty();

    // Auto-detect
    test_auto_detect_json();
    test_auto_detect_yaml();
    test_auto_detect_yml();
    test_auto_detect_no_extension();

    std::cout << "\nAll " << 15 << " tests passed.\n";
    return 0;
}
