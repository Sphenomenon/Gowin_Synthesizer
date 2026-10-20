#!/usr/bin/env python3
"""Audit only the fixed p33 offline experiment; no hardware or source changes."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import time
import watch_resumed_candidates as audit_tools

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BUILD = ROOT / 'results/timing_p33_measured_paths_20261018_173136_739962'
audit_tools.PREPARE = ROOT / 'results/timing_p33_measured_paths_20261018_173136_545041'
launch = json.loads((OUT / 'p33_launch.json').read_text())
deadline = time.monotonic() + 3 * 3600
while audit_tools.alive(launch['pid']) and time.monotonic() < deadline:
    time.sleep(5)
if audit_tools.alive(launch['pid']):
    result = {'passed': False, 'status': 'watch timeout; no acceptance'}
elif not (BUILD / 'tool_result.json').exists():
    result = {'passed': False, 'status': 'process exited without complete result'}
else:
    try:
        result = audit_tools.audit('p33', BUILD)
    except Exception as exc:
        result = {'passed': False, 'status': 'audit error', 'error': repr(exc)}
result.update(checked=datetime.now().astimezone().isoformat(), hardware_tested=False,
              build=str(BUILD.relative_to(ROOT)),
              audit_helper_sha256=hashlib.sha256(Path(audit_tools.__file__).read_bytes()).hexdigest())
(OUT / 'p33_audits.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(result['status'], flush=True)
