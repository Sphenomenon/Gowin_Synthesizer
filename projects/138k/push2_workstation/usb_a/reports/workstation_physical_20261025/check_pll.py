"""Dated native physical verification; no programming or release promotion."""

from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
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
reference = root / 'vendor/ddr3_reference/ddr3_memory_interface.vo'
reference_view = physical / 'pll-audit-view/reference'
reference_view.mkdir(parents=True, exist_ok=True)
for suffix, source in [('vo', reference), ('v', stage / 'vendor/gowin_ddr3/ddr3_memory_interface.v')]:
    link = reference_view / ('ddr3_memory_interface.' + suffix)
    if not link.exists():
        link.symlink_to(source)
    assert link.resolve() == source.resolve()
os.environ['PRJ1_DDR_REFERENCE'] = str(reference_view / 'ddr3_memory_interface.vo')
sys.path.insert(0, str(stage / 'scripts'))
import check_build
if hashlib.sha256(reference.read_bytes()).hexdigest() != check_build.EXPECTED_NETLIST_SHA256:
    raise ValueError('DDR reference differs from the locked reset audit')
from check_video_pll_init import inspect_video_pll_init, RoutedDesign


def inspect_shared_clock_plls(sdf, netlist):
    routed = RoutedDesign(sdf, netlist)
    evidence, errors = {}, []
    try:
        for prefix in ('u_audio_clock/g_hardware.u_pll', 'u_usb_pll', 'u_cpu_pll', 'u_lcd/u_pll'):
            instance = prefix + '/PLL_inst'
            kind, ports = routed.cells[instance]
            assert kind == 'PLL', instance
            paths = []
            for bus, width, first_bit in (('ICPSEL', 6, 3), ('LPFRES', 3, 0), ('RESET', 1, 9)):
                bits = routed.bits(ports[bus])
                assert len(bits) == width, (instance, bus)
                for index, net in enumerate(reversed(bits)):
                    endpoint = instance + '/' + (bus if bus == 'RESET' else bus + '[' + str(index) + ']')
                    if net in routed.constants:
                        assert routed.constants[net] == 0, endpoint
                        paths.append(dict(endpoint=endpoint, constant=0, total_ns=0))
                        continue
                    driver, output_pin = routed.drivers[net]
                    expected = re.escape(prefix + '/pll_control_' + str(first_bit + index)) + r'_s\d+'
                    assert re.fullmatch(expected, driver), (endpoint, driver)
                    driver_kind, driver_ports = routed.cells[driver]
                    assert driver_kind.startswith('DFF') and output_pin == 'Q', driver
                    assert driver_ports['CLK'] == routed.clock_net, ('shared PLL control clock changed', driver)
                    flight = (routed.input_delay + routed.route('clk_50m_ibuf/O', driver + '/CLK') +
                              routed.arc(driver, 'CLK', 'Q') + routed.route(driver + '/Q', endpoint))
                    assert flight <= 10, (endpoint, flight, '10ns PLL control budget')
                    paths.append(dict(endpoint=endpoint, source=driver, total_ns=flight))
            evidence[prefix] = dict(paths=paths, maximum_propagation_ns=max(path['total_ns'] for path in paths),
                                    bound_ns=10, complete_tuple_directly_registered=True)
    except (AssertionError, KeyError, ValueError) as error:
        errors.append(str(error))
    return errors, evidence

source = stage / 'scripts/check_serializer_startup.py'
manifest = json.loads((candidate / 'integration_inputs.json').read_text())
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
assert source_hash == manifest['staged_input_sha256']['scripts/check_serializer_startup.py']
text = source.read_text()
adaptations = [
    ('u_video/u_dvi/clock_phy/tmds_serdes_inst0', 'u_video/u_dvi/clock_lane/serializer'),
    ('u_video/u_dvi/gen_enc[{i}].dvi_tx_tmds_phy_inst/tmds_serdes_inst0', 'u_video/u_dvi/data_lanes[{i}].serializer/serializer'),
    ('+ "/tmds_bufds_isnt0"', '+ "/differential"'),
    ('(ground if bit < 5 else power)', '(power if bit < 5 else ground)'),
    ("10'b1111100000 clock word", "10'b0000011111 clock word"),
    ('"word_d9_to_d0": "1111100000"', '"word_d9_to_d0": "0000011111"'),
]
for original, replacement in adaptations:
    assert text.count(original) == 1, original
    text = text.replace(original, replacement)
namespace = dict(__file__=str(source), __name__='native_serializer_audit')
exec(compile(text, str(source) + ':native-lanes-adaptation', 'exec'), namespace)
pnr = physical / 'impl/pnr/custom_138k_integration'
sdf = pnr.with_suffix('.sdf').read_text()
netlist = pnr.with_suffix('.vo').read_text()
view = physical / 'pll-audit-view'
view.mkdir(exist_ok=True)
for name in ('scripts', 'vendor'):
    link = view / name
    if not link.exists():
        link.symlink_to(stage / name, target_is_directory=True)
evidence_directory = view / 'docs/evidence'
evidence_directory.mkdir(parents=True, exist_ok=True)
for script, evidence_name in [('audit_ddr_reset_sequence.py', 'ddr_reset_sequence.json'),
                              ('audit_ddr_configuration_paths.py', 'ddr_configuration_paths.json')]:
    target = evidence_directory / evidence_name
    if not target.exists():
        subprocess.run([sys.executable, str(stage / 'scripts' / script), '--output', str(target)], check=True)
check_build.ROOT = view
ddr_errors, ddr = check_build.inspect_ddr_audit()
configuration_errors, configuration = check_build.inspect_ddr_configuration_audit()
startup_errors, startup = namespace['inspect_serializer_startup'](sdf, netlist, ddr,
                                                                  (physical / 'physical.sdc').read_text())
pll_errors, pll = inspect_video_pll_init(sdf, netlist, stage)
shared_errors, shared_plls = inspect_shared_clock_plls(sdf, netlist)
errors = ddr_errors + configuration_errors + startup_errors + pll_errors + shared_errors
negative_checks = {}
for kind, name, pin, reason in [('OSER10', 'u_video/u_dvi/clock_lane/serializer', 'D0', 'clock word'),
                                 ('ELVDS_OBUF', 'u_video/u_dvi/clock_lane/differential', 'I', 'directly drives')]:
    expression = r'^' + kind + r'\s+\\' + re.escape(name) + r'\s*\((.*?)^\);'
    match = re.search(expression, netlist, re.M | re.S)
    assert match is not None, name
    changed, count = re.subn(r'(\.' + pin + r'\()([^)]*)', r'\g<1>GND', match[0])
    assert count == 1 and changed != match[0], (name, pin)
    broken = netlist[:match.start()] + changed + netlist[match.end():]
    rejected, unused = namespace['inspect_serializer_startup'](sdf, broken, ddr, (physical / 'physical.sdc').read_text())
    assert any(reason in error for error in rejected), rejected
    negative_checks[name + '/' + pin] = rejected
result = dict(scope='native four-lane startup and existing DDR/video PLL routed audits; not board acceptance',
              passed=not errors, errors=errors, ddr_source=ddr, ddr_configuration=configuration,
              serializer_startup=startup, video_pll=pll, shared_clock_plls=shared_plls, hardware_tested=False,
              source_checker_sha256=source_hash, exact_adaptations=adaptations,
              adapted_checker_sha256=hashlib.sha256(text.encode()).hexdigest(),
              adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
result['negative_checks'] = negative_checks
result['adapter_exit_plan'] = 'Fold native lane paths and polarity into the existing versioned checker before selecting this physical profile.'
result['ddr_reference'] = dict(path=str(reference), sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
(physical / 'pll-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(passed=not errors, errors=errors), indent=2))
raise SystemExit(0 if not errors else 1)
