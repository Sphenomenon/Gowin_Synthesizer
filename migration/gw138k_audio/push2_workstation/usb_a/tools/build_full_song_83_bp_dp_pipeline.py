#!/usr/bin/env python3
"""0x83: preserve staged CNN throughput; pipeline the failing Viterbi path.

Copy the complete full82 staging tree, assert accepted and frozen hashes, then
replace only Viterbi and UserCode. See CNN_CORRECTNESS_SPEED_20261006.md.
"""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full82_20261005_144933'
BASELINE_SHA = {
    'rtl/music/basic_pitch_viterbi.sv':
        '852d579b2a6e908b3e301b3dc6d38c4eb7b0ae39b4df7707d131bfc9fa173bcd',
    'rtl/music/basic_pitch_pcm_pipeline.sv':
        'd1d67f4a07ce7ec3a35c0f24adc794a5a2164b662451f32e701511d228038122',
    'rtl/music/basic_pitch_workstation_link.sv':
        '8e9e4938f9418b140150c03684de91298de4eb0f39ee263be7cc82a7ee74454e',
}
# live path -> (staged path, accepted SHA256)
FROZEN = {
    'rtl/display_data/gw138k_ddr_arbiter.sv': (
        'src/ae350/gw138k_ddr_arbiter.sv',
        '61b0353f72419f0a719f693e121b1aa9ff8b07ed0dbfbdd33ec39f72172ef178'),
    'rtl/display_data/hdmi_display.v': (
        'src/video/hdmi_display.v',
        '7421e472c9289b1cca0eefe1c428bc03d7f6ea1081e7f8f86a785d6d7ac42dcc'),
    'rtl/ddr_address_map.vh': (
        'src/memory/ddr_address_map.vh',
        '0ec949e54acecac04b71fceca2cf725d56d2691c850fbd83951fdc6441fc8ddb'),
    'rtl/audio/delay_ddr/delay_ddr_dma.sv': (
        'rtl/audio/delay_ddr/delay_ddr_dma.sv',
        'e39fc2672874fad520f1dfab8d945e23600499e7147f9057ed52fdd2561b7301'),
    'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv': (
        'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv',
        'e5764ef18a0c8a1918369121b1b27124eb9e5c0b6cfe4922a65cfd14d2d6eff6'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full83_%Y%m%d_%H%M%S_%f')
    stage = output / 'Prj1'
    for live, (staged, digest) in FROZEN.items():
        assert sha(ROOT / live) == digest, f'frozen live source drifted: {live}'
        assert sha(BASE / 'Prj1' / staged) == digest, f'frozen baseline drifted: {staged}'
    for name, digest in BASELINE_SHA.items():
        assert sha(BASE / 'Prj1' / name) == digest, f'baseline drifted: {name}'
        if name != 'rtl/music/basic_pitch_viterbi.sv':
            assert sha(ROOT / name) == digest, f'CNN configuration drifted: {name}'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    shutil.copy2(ROOT / 'rtl/music/basic_pitch_viterbi.sv',
                 stage / 'rtl/music/basic_pitch_viterbi.sv')
    tcl = stage / 'scripts/build.tcl'
    text = tcl.read_text()
    assert text.count('set_option -user_code 00000082') == 1
    tcl.write_text(text.replace('set_option -user_code 00000082',
                               'set_option -user_code 00000083'))
    inputs = {str(p.relative_to(stage)): sha(p)
              for p in stage.rglob('*') if p.is_file()}
    (output / 'workstation_inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    (output / 'build_metadata.json').write_text(json.dumps({
        'baseline': str(BASE), 'user_code': '0x00000083',
        'patches': ['rtl/music/basic_pitch_viterbi.sv', 'scripts/build.tcl'],
        'frozen_sha256': {live: digest for live, (_, digest) in FROZEN.items()},
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'hardware_tested': False}, indent=2) + '\n')
    print(output, flush=True)
    if '--dry-run' in sys.argv:
        print('dry run: patches applied and frozen hashes verified', flush=True)
        return
    with (output / 'gowin.log').open('w') as log:
        result = subprocess.run([str(Path.home() / '.local/bin/gw_sh'), 'scripts/build.tcl'],
                                cwd=stage, env=dict(os.environ, PRJ1_FLOW='all'),
                                stdout=log, stderr=subprocess.STDOUT)
    changed = [name for name, digest in inputs.items() if sha(stage / name) != digest]
    for live, (staged, digest) in FROZEN.items():
        assert sha(ROOT / live) == sha(stage / staged) == digest, f'frozen input drifted: {live}'
    (output / 'tool_result.json').write_text(json.dumps({
        'exit_code': result.returncode, 'inputs_unchanged': not changed,
        'changed': changed, 'baseline': str(BASE), 'hardware_tested': False}, indent=2) + '\n')
    print('Gowin exit', result.returncode, 'changed inputs', changed, flush=True)
    if result.returncode or changed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
