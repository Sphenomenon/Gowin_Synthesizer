"""Verify the temporary isolated DDR observer without operating a board."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import audit_workstation_timing
from tools.workstation_synthesis_netlist import SynthesisNetlist


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(output):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    if json.loads((output / 'build_result.json').read_text())['returncode'] != 0:
        raise ValueError('isolated DDR implementation did not finish')
    for relative, expected in manifest['input_sha256'].items():
        if digest(output / relative) != expected:
            raise ValueError('isolated DDR input changed: ' + relative)
    synthesis = json.loads((output / 'synthesis_inputs.json').read_text())
    if digest(Path(__file__).with_name('ddr_calibration_diagnostic.sv')) != synthesis['top_source_sha256']:
        raise ValueError('diagnostic wrapper changed after synthesis')
    parent = Path(synthesis['source_parent'])
    if digest(parent / 'integration_inputs.json') != synthesis['source_parent_manifest_sha256']:
        raise ValueError('workstation source identity changed')
    original_inputs = json.loads((parent / 'integration_inputs.json').read_text())
    stage = parent / 'workstation/Prj1'
    for relative in ('scripts/check_video_pll_init.py',):
        if digest(stage / relative) != original_inputs['staged_input_sha256'][relative]:
            raise ValueError('routed parser changed')
    sys.path.insert(0, str(stage / 'scripts'))
    from check_video_pll_init import RoutedDesign

    report = output / 'impl/pnr/diagnostic_tr_content.html'
    view = output / 'timing-audit-view'
    target = view / 'Prj1/impl/pnr/Prj1_tr_content.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.resolve() != report:
            raise ValueError('timing view points to another candidate')
    else:
        target.symlink_to(report)
    original_targets = audit_workstation_timing.TARGETS
    try:
        audit_workstation_timing.TARGETS = {
            'clk_50m': 50.0, 'ddr_mem400': 400.0, 'ddr_ui100': 100.0, 'tck_pad_i': 20.0}
        timing = audit_workstation_timing.audit(view)
    finally:
        audit_workstation_timing.TARGETS = original_targets
    with (output / 'timing-audit.json').open('x') as stream:
        stream.write(json.dumps(timing, indent=2) + '\n')
    netlist_path = output / 'impl/pnr/diagnostic.vo'
    routed_text = netlist_path.read_text()
    netlist = SynthesisNetlist(routed_text, 'ddr_calibration_diagnostic')
    design = RoutedDesign((output / 'impl/pnr/diagnostic.sdf').read_text(), routed_text)
    pll_path = 'u_memory/u_pll/u_pll_0/PLL_inst'
    divider_path = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv'
    parameters = netlist.cells[pll_path]['parameters']
    assert parameters['FCLKIN'] == '"50"' and parameters['CLKOUT2_EN'] == '"TRUE"'
    assert parameters['CLKFB_SEL'] == '"INTERNAL"'
    assert parameters['IDIV_SEL'] == '1' and parameters['FBDIV_SEL'] == '1'
    assert int(parameters['MDIV_SEL']) / int(parameters['ODIV2_SEL']) == 8
    assert netlist.cells[divider_path]['parameters']['DIV_MODE'] == '"4"'
    assert netlist.pin(divider_path, 'HCLKIN') == netlist.pin(pll_path, 'CLKOUT2')
    assert netlist.pin(pll_path, 'CLKIN') == 'clk_50m'
    cdc = {}
    for stem, origin_stem in (('ui_gray', 'ui_counter_gray'), ('status', None)):
        bits = []
        for bit in range(8):
            first, second = f'{stem}_meta_{bit}_s0', f'{stem}_sync_{bit}_s0'
            first_pins, second_pins = design.cells[first][1], design.cells[second][1]
            assert first_pins['Q'] == second_pins['D']
            assert first_pins['CLK'] == second_pins['CLK']
            flight = design.arc(first, 'CLK', 'Q') + design.route(first + '/Q', second + '/D')
            assert flight <= 2.0
            entry = dict(bit=bit, stage_flight_ns=flight)
            if origin_stem:
                source = f'{origin_stem}_{bit}_s0'
                source_pins = design.cells[source][1]
                assert source_pins['Q'] == first_pins['D']
                assert source_pins['CLK'] != first_pins['CLK']
                flight = design.arc(source, 'CLK', 'Q') + design.route(source + '/Q', first + '/D')
                assert flight <= 10.0
                entry['source_flight_ns'] = flight
            bits.append(entry)
        cdc[stem] = bits
    wrapper = output / 'impl/gao/gw_gao_top.v'
    wrapper_text = wrapper.read_text()
    match = re.search(r'\.data_i\s*\(\s*\{(.*?)\}\s*\)', wrapper_text, re.S)
    assert match
    assert [name.strip().lstrip('\\').strip() for name in match[1].split(',')] == manifest['signals']
    sample_clock = manifest['sample_clock']
    assert sample_clock in ('clk_50m_d', 'ui_clk')
    assert re.search(r'\.clk_i\s*\(\s*' + re.escape(sample_clock) + r'\s*\)', wrapper_text)
    bitstream = output / 'impl/pnr/ao_0.fs'
    with bitstream.open() as stream:
        header = ''.join(next(stream) for unused in range(25))
    match = re.search(r'//UserCode:\s*(0x[0-9a-f]+)', header, re.I)
    assert match and int(match[1], 16) == int(manifest['user_code'], 16)
    with (output / 'contract_regression.log').open('x') as stream:
        regression = subprocess.run([sys.executable, str(ROOT / 'sim/test_workstation_ddr_diagnostic.py')],
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=60)
    assert regression.returncode == 0
    result = dict(identity=manifest['identity'], input_manifest_sha256=digest(output / 'inputs.json'),
                  fs=str(bitstream), fs_sha256=digest(bitstream), timing_closed=timing['timing_closed'],
                  timing_global_worst_ns=timing['global_worst_ns'], pll_frequency_hz=400000000,
                  ui_divider=4, pll_source_and_divider_verified=True, diagnostic_cdc=cdc,
                  gao_wrapper_sha256=digest(wrapper), checker_sha256=digest(__file__),
                  contract_test_script_sha256=digest(ROOT / 'sim/test_workstation_ddr_diagnostic.py'),
                  contract_regression_returncode=regression.returncode,
                  scope='isolated STA, PLL/divider and diagnostic CDC, not full PHY or workstation signoff',
                  hardware_acceptance=False, release_ready=False, sram_programmed=False, flash_accessed=False)
    with (output / 'implementation_verification.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    result = verify(args.candidate)
    print(json.dumps({key: result[key] for key in ('identity', 'timing_closed',
                    'timing_global_worst_ns', 'fs_sha256')}, indent=2))
    raise SystemExit(0 if result['timing_closed'] else 1)
