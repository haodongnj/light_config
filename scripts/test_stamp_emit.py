#!/usr/bin/env python3
"""End-to-end: generated files contain the provenance stamp."""
import sys
import tempfile
import os
import hashlib
import re
from pathlib import Path
sys.path.insert(0, "scripts")
from gen_config import GeneratorConfig, generate  # noqa: E402


CSV = (
    "__metadata__,schema_version=1.3.0,generator=light_config\n"
    "field_name,group,type,default,min,max,optional,description,hpp_file\n"
    "debug,AppConfig,bool,false,,,false,enable debug,app_config.hpp\n"
)

d = tempfile.mkdtemp()
csv_path = os.path.join(d, "sample_config.csv")
with open(csv_path, "w", encoding="utf-8") as f:
    f.write(CSV)
exp_md5 = hashlib.md5(Path(csv_path).read_bytes()).hexdigest()

out = tempfile.mkdtemp()
cfg = GeneratorConfig(input_csv=csv_path, output_dir=out)
generate(cfg)

hpp = (Path(out) / "app_config.hpp").read_text()
cpp = (Path(out) / "app_config.cpp").read_text()

# Stamp present in header
assert "Schema provenance" in hpp, hpp
assert "schema_version : 1.3.0" in hpp, hpp
assert f"csv_md5        : {exp_md5}" in hpp, hpp
assert "source_csv     : sample_config.csv" in hpp, hpp
assert re.search(r"generated_at   : \d{4}-\d{2}-\d{2}T.+00:00", hpp), hpp

# Stamp present in source and AFTER the DO NOT EDIT line
assert "Schema provenance" in cpp, cpp
assert "DO NOT EDIT BY HAND" in cpp
assert cpp.index("DO NOT EDIT BY HAND") < cpp.index("Schema provenance"), cpp

# Header: stamp is between DO NOT EDIT and the first #include
assert hpp.index("DO NOT EDIT BY HAND") < hpp.index("Schema provenance")
assert hpp.index("Schema provenance") < hpp.index("#include")

# Override
out2 = tempfile.mkdtemp()
cfg2 = GeneratorConfig(input_csv=csv_path, output_dir=out2, schema_version_override="7.7.7")
generate(cfg2)
hpp2 = (Path(out2) / "app_config.hpp").read_text()
assert "schema_version : 7.7.7" in hpp2, hpp2

# Backward-compatible: no metadata row
d2 = tempfile.mkdtemp()
csv2 = os.path.join(d2, "bare.csv")
with open(csv2, "w", encoding="utf-8") as f:
    f.write("field_name,group,type,default,min,max,optional,description\nx,Foo,int,42,,,false,Value\n")
out3 = tempfile.mkdtemp()
cfg3 = GeneratorConfig(input_csv=csv2, output_dir=out3)
generate(cfg3)
# per _struct_to_hpp_name, Foo -> foo.hpp
hpp3 = (Path(out3) / "foo.hpp").read_text()
assert "schema_version : unknown" in hpp3, hpp3

# Schema version constant emitted in header (with metadata version)
assert 'constexpr std::string_view kAppConfigSchemaVersion{"1.3.0"};' in hpp, hpp

# Schema version constant emitted in header (override version)
assert 'constexpr std::string_view kAppConfigSchemaVersion{"7.7.7"};' in hpp2, hpp2

# Schema version constant emitted in header (no metadata → empty string)
assert 'constexpr std::string_view kFooSchemaVersion{""};' in hpp3, hpp3
print("OK stamp emit end-to-end")
