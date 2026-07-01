#!/usr/bin/env python3
"""Self-test for __metadata__ row parsing in SchemaModel.from_csv."""
import sys
import tempfile
import os
sys.path.insert(0, "scripts")
from gen_config import SchemaModel  # noqa: E402


def _write(name: str, text: str) -> str:
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


# 1. metadata row parsed into model.metadata, stripped from data rows
p = _write("m.csv", (
    "__metadata__,schema_version=1.3.0,generator=light_config\n"
    "field_name,group,type,default,min,max,description,hpp_file\n"
    "debug,AppConfig,bool,false,,,Enable debug logging,app_config.hpp\n"
))
m = SchemaModel.from_csv(p)
assert m.metadata == {"schema_version": "1.3.0", "generator": "light_config"}, m.metadata
assert "AppConfig" in m.groups, m.groups
# the field row was still parsed as a field
assert "debug" in (m.groups["AppConfig"][0]["field_name"]), m.groups

# 2. multiple metadata rows merge, later wins
p = _write("m2.csv", (
    "__metadata__,schema_version=1.0.0\n"
    "__metadata__,schema_version=2.0.0,generator=light_config\n"
    "field_name,group,type\n"
    "x,Foo,int\n"
))
m = SchemaModel.from_csv(p)
assert m.metadata == {"schema_version": "2.0.0", "generator": "light_config"}, m.metadata

# 3. no metadata row -> empty dict, backward compatible
p = _write("nometadata.csv", (
    "field_name,group,type\n"
    "x,Foo,int\n"
))
m = SchemaModel.from_csv(p)
assert m.metadata == {}, m.metadata
assert "Foo" in m.groups

# 4. malformed metadata pair -> exit nonzero
p = _write("bad.csv", (
    "__metadata__,NOEQUALSHERE\n"
    "field_name,group,type\n"
    "x,Foo,int\n"
))
try:
    SchemaModel.from_csv(p)
    raise AssertionError("expected SystemExit")
except SystemExit:
    pass

# 5. __metadata__ after header is NOT consumed (stays a data row)
p = _write("late.csv", (
    "field_name,group,type\n"
    "__metadata__,Foo,string\n"
))
try:
    SchemaModel.from_csv(p)
except SystemExit:
    raise AssertionError("late metadata row should be treated as data, not error")
m = SchemaModel.from_csv(p)
# The row maps as: field_name=__metadata__, group=Foo, type=string
assert "Foo" in m.groups, m.groups
assert m.groups["Foo"][0]["field_name"] == "__metadata__", m.groups["Foo"][0]

# 6. File-line accuracy: _csv_line and _csv_raw remain correct after metadata rows
p = _write("linecheck.csv", (
    "__metadata__,schema_version=1.0.0\n"
    "field_name,group,type\n"
    "x,Foo,int\n"
))
m = SchemaModel.from_csv(p)
row = m.groups["Foo"][0]
assert row["_csv_line"] == 3, f"expected _csv_line=3, got {row['_csv_line']}"
raw_third_line = "__metadata__,schema_version=1.0.0\nfield_name,group,type\nx,Foo,int\n"
third_line = raw_third_line.splitlines()[2]  # 0-indexed -> line 3
assert row["_csv_raw"] == third_line, (
    f"expected _csv_raw={third_line!r}, got {row['_csv_raw']!r}"
)

print("OK metadata parsing")
