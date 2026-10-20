#!/usr/bin/env python3
"""Verify imported source/evidence bytes without original absolute paths."""
import hashlib
import json
from pathlib import Path

project = Path(__file__).resolve().parents[1]
repository = project.parents[3]
manifest = json.loads((project / "SOURCE_IMPORT.json").read_text())
errors = []
for name, item in manifest["files"].items():
    path = repository / name
    expected = item.get("repository_sha256", item["sha256"])
    if not path.is_file():
        errors.append(f"missing: {name}")
    elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        errors.append(f"changed: {name}")
app = project / "clients/android"
if not app.is_symlink() or app.resolve() != repository / "clients/android":
    errors.append("standalone Android link must resolve to the shared client")
vendor = project / "vendor/rtl8723ds_ble"
for name, item in json.loads((vendor / "MANIFEST.json").read_text())["files"].items():
    path = vendor / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        errors.append(f"vendor input mismatch: {name}")
result = {"passed": not errors, "files": len(manifest["files"]),
          "shared_android": str(app.resolve()), "errors": errors}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
