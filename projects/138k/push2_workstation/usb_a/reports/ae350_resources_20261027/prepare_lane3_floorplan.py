"""Prepare a scoped SRAM diagnostic without changing the a26 business netlist."""

from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'out/workstation_resource_a26_20261027_c1_physical'
REFERENCE = ROOT / 'out/official_ddr_ab_20261026_01/c11026b3'
OUTPUT = ROOT / 'out/workstation_resource_a26_20261027_c6_floorplan'
PREFIX = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_init/'
LOCATIONS = {
    PREFIX + 'read_calibration_logic_gen[3].rburst_neg_s0': 'R87C174[0][A]',
    PREFIX + 'read_calibration_logic_gen[3].rburst_neg_r_s0': 'R87C174[2][A]',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(*, global_reference_clock=False):
    output = (ROOT / 'out/workstation_resource_a26_20261027_c7_refclock'
              if global_reference_clock else OUTPUT)
    user_code = 'C11027C7' if global_reference_clock else 'C11027C6'
    gao_id = '27C1' if global_reference_clock else '27C6'
    locations = {} if global_reference_clock else LOCATIONS
    manifest = json.loads((SOURCE / 'physical_inputs.json').read_text())
    for name, expected in manifest['input_sha256'].items():
        if digest(SOURCE / name) != expected:
            raise ValueError('C1 input changed: ' + name)
    if digest(REFERENCE / 'impl/pnr/ao_0.fs') != (
            'a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c'):
        raise ValueError('B3 reference changed')
    reference_timing = REFERENCE / 'impl/pnr/custom_138k_integration.tr'
    text = reference_timing.read_text()
    for instance, location in locations.items():
        if not re.search(re.escape(location) + r'\s+' + re.escape(instance) + r'/(?:Q|D)\s', text):
            raise ValueError('B3 placement not established: ' + instance)
    output.mkdir()
    for name in ('custom_138k_integration.vg', 'physical.cst', 'physical.sdc',
                 'parent_integration_inputs.json', 'parent_synthesis_audit.json'):
        shutil.copyfile(SOURCE / name, output / name)
    for suffix in ('p', 'pr'):
        shutil.copyfile(SOURCE / f'impl/pnr/custom_138k_integration.{suffix}',
                        output / f'reference.{suffix}')
    with (output / 'physical.cst').open('a') as stream:
        for instance, location in locations.items():
            stream.write(f'\nINS_LOC "{instance}" {location};\n')
        if global_reference_clock:
            stream.write('\nCLOCK_LOC "clk_50m_d" BUFG = CLK;\n')
    script = (SOURCE / 'run.tcl').read_text()
    if script.count('set_option -user_code C11027C1\n') != 1 or script.count('run pnr\n') != 1:
        raise ValueError('C1 Tcl anchors changed')
    script = script.replace('set_option -user_code C11027C1\n',
                            f'set_option -user_code {user_code}\n')
    script = script.replace('run pnr\n',
                            'set_option -inc_pnr [file join $root reference.p]\nrun pnr\n')
    (output / 'run.tcl').write_text(script)
    document = ET.parse(SOURCE / 'workstation.gao')
    document.find('./GAO_ID').text = gao_id
    document.write(output / 'workstation.gao', encoding='unicode')
    policy = ('exact C1 a26 business and SDC; explicit global 50 MHz reference '
              'clock route; no lane3 register locations; same-netlist C1 incremental '
              'P&R; unchanged C1 GAO identity and 16-bit observation'
              if global_reference_clock else
              'exact C1 a26 business and SDC; two lane3 falling-edge '
              'RBURST registers at measured B3 locations; same-netlist '
              'C1 incremental P&R; unchanged 16-bit GAO observation')
    manifest.update(
        identity='custom138k-native-physical-' + user_code,
        prepared_at=datetime.now().astimezone().isoformat(),
        source_policy=policy,
        user_code='0x' + user_code, gao_id=gao_id,
        locations=locations, global_reference_clock=global_reference_clock,
        synthesis_rerun=False, incremental_pnr=True,
        timing_driven=True, final_routed_sta_requested=True,
        preparer_sha256=digest(Path(__file__)),
        reference_timing_sha256=digest(reference_timing),
        reference_candidate=str(SOURCE),
        sram_programmed=False, flash_accessed=False,
        hardware_acceptance=False, release_ready=False,
        input_sha256={path.name: digest(path) for path in output.iterdir()})
    (output / 'physical_inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    core = document.find('./AoCore')
    observer = dict(schema=1, identity=manifest['identity'], user_code=manifest['user_code'],
                    source_identity=manifest['parent_identity'],
                    gao_configuration_id=gao_id, gao_file='workstation.gao',
                    source_policy=manifest['source_policy'],
                    sample_clock=core.get('sample_clock'),
                    storage_depth=int(core.get('storage_depth')),
                    signals=[signal.text for signal in core.findall('./SignalList/Signal')],
                    signal_schema='workstation-memory-video-16-v1', full_workstation=True,
                    input_sha256=manifest['input_sha256'], sram_programmed=False,
                    flash_accessed=False, hardware_acceptance=False)
    (output / 'inputs.json').write_text(json.dumps(observer, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--global-reference-clock', action='store_true')
    args = parser.parse_args()
    prepare(global_reference_clock=args.global_reference_clock)
