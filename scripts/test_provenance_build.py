#!/usr/bin/env python3
"""Self-test for _build_provenance (MD5, timestamp, version override)."""
import sys
import tempfile
import os
import hashlib
import re
from pathlib import Path
sys.path.insert(0, "scripts")
from gen_config import GeneratorConfig, SchemaModel, _build_provenance, generate  # noqa: E402


def _write(name: str, text: str) -> str:
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


CSV = (
    "__metadata__,schema_version=1.3.0,generator=light_config\n"
    "field_name,group,type,default,min,max,description,hpp_file\n"
    "debug,AppConfig,bool,false,,,enable debug,app_config.hpp\n"
)

p = _write("sample_config.csv", CSV)
raw = Path(p).read_bytes()
exp_md5 = hashlib.md5(raw).hexdigest()

model = SchemaModel.from_csv(p)

# 1. no override -> CSV version
cfg = GeneratorConfig(input_csv=p, output_dir=tempfile.mkdtemp())
prov = _build_provenance(cfg, model, p)
assert prov.schema_version == "1.3.0", prov.schema_version
assert prov.source_csv == "sample_config.csv", prov.source_csv
assert prov.csv_md5 == exp_md5, (prov.csv_md5, exp_md5)
assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+00:00", prov.generated_at), prov.generated_at
assert prov.generator == "light_config", prov.generator

# 2. CLI override wins
cfg = GeneratorConfig(input_csv=p, output_dir=tempfile.mkdtemp(), schema_version_override="9.9.9")
prov = _build_provenance(cfg, model, p)
assert prov.schema_version == "9.9.9", prov.schema_version

# 3. no metadata + no override -> unknown
p2 = _write("bare.csv", "field_name,group,type\nx,Foo,int\n")
model2 = SchemaModel.from_csv(p2)
cfg2 = GeneratorConfig(input_csv=p2, output_dir=tempfile.mkdtemp())
prov2 = _build_provenance(cfg2, model2, p2)
assert prov2.schema_version == "unknown", prov2.schema_version
assert prov2.generator == "light_config / scripts/gen_config.py", prov2.generator
print("OK _build_provenance")
