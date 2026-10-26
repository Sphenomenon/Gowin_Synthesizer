"""Dated native physical verification; no programming or release promotion."""

from pathlib import Path
import hashlib
import json
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
physical = Path(sys.argv[1]).resolve()
physical_inputs = json.loads((physical / 'physical_inputs.json').read_text())
for name, expected in physical_inputs['input_sha256'].items():
    if hashlib.sha256((physical / name).read_bytes()).hexdigest() != expected:
        raise ValueError('physical input drifted: ' + name)
candidate = Path(physical_inputs['parent_candidate'])
stage = candidate / 'workstation/Prj1'
parent = json.loads((physical / 'parent_integration_inputs.json').read_text())
for name in ('scripts/check_video_pll_init.py', 'scripts/check_serializer_startup.py', 'scripts/check_build.py'):
    if hashlib.sha256((stage / name).read_bytes()).hexdigest() != parent['staged_input_sha256'][name]:
        raise ValueError('physical verification dependency drifted: ' + name)
sys.path.insert(0, str(root / 'tools'))
sys.path.insert(0, str(stage / 'scripts'))
from workstation_timing_constraints import constraints

expected = {name: parent['source_snapshot_sha256'][name] for name in (
    'tools/audit_workstation_cdc.py', 'tools/workstation_timing_constraints.py',
    'tools/audit_clk50_cdc_routes.py')}
for name, digest in expected.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
source = root / 'tools/audit_workstation_cdc.py'
original = source.read_text()
assert original.count('u_push/') == 3
adapted = original.replace('u_push/', 'u_native_usb/input_owner/')
namespace = dict(__file__=str(source), __name__='native_common_cdc_audit')
exec(compile(adapted, str(source) + ':native-input-owner', 'exec'), namespace)
namespace['constraints'] = lambda: constraints().replace('u_push/', 'u_native_usb/input_owner/')
view = physical / 'cdc-audit-view'
target = view / 'Prj1'
target.mkdir(parents=True, exist_ok=True)
for name in ('src', 'rtl', 'scripts'):
    link = target / name
    if not link.exists():
        link.symlink_to(stage / name, target_is_directory=True)
(target / 'constraints').mkdir(exist_ok=True)
link = target / 'constraints/tang_mega_138k.sdc'
if not link.exists():
    link.symlink_to(physical / 'physical.sdc')
(target / 'impl/pnr').mkdir(parents=True, exist_ok=True)
for suffix in ('vo', 'sdf'):
    link = target / ('impl/pnr/Prj1.' + suffix)
    if not link.exists():
        link.symlink_to(physical / ('impl/pnr/custom_138k_integration.' + suffix))
result = namespace['audit'](view)
result.update(scope='existing nine FIFO pairs, song mailbox and level receivers after input-owner hierarchy adaptation; native USB/FPC/BLE paths are separate',
              source_checker_sha256=expected, hierarchy_replacement_count=3,
              adapted_checker_sha256=hashlib.sha256(adapted.encode()).hexdigest(),
              adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              hardware_tested=False, deployment_allowed=False)
(physical / 'common-cdc-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(passed=result['passed'], errors=result['errors'], gray_buses=len(result['gray']),
                     levels=len(result['levels'])), indent=2))
raise SystemExit(0 if result['passed'] else 1)
