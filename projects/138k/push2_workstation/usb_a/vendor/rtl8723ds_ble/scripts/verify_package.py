"""Verify every exported source, ROM and reference asset against MANIFEST.json."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
for name, expected in manifest['files'].items():
    data = (root / name).read_bytes()
    if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise SystemExit(f'Exported file mismatch: {name}')
print(f"PORTABLE_BT_MANIFEST=PASS FILES={len(manifest['files'])}")
