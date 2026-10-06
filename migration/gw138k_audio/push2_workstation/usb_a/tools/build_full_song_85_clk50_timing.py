#!/usr/bin/env python3
"""Build a low-RAM clk50 timing candidate from the complete full84 staging tree.

Preserve the deployed scope/TF integration and all frozen DDR/display sources.
Only explicit overlays, the UserCode, and diagnostic report commands may differ.
No board I/O and no changes to LATEST_WORKSTATION.json.
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_full_song_83_bp_ddr_isolation import FROZEN
from workstation_memory import audit

BASE = ROOT / 'results/workstation_scope83_20261006_230626_011557'
OVERLAYS = ['rtl/music/basic_pitch_viterbi.sv', 'rtl/music/basic_pitch_cqt_engine.sv']
REPORTS = '''
# Diagnose clk50 without changing its 20ns constraint or any timing exceptions.
report_timing -setup -from_clock [get_clocks {clk_50m}] -to_clock [get_clocks {clk_50m}] -max_paths 100
report_timing -hold -from_clock [get_clocks {clk_50m}] -to_clock [get_clocks {clk_50m}] -max_paths 25
report_timing -setup -to_clock [get_clocks {clk_50m}] -max_paths 100
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen(stage):
    for live, (staged, digest) in FROZEN.items():
        assert sha(ROOT / live) == sha(stage / staged) == digest, live


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flow', choices=['prepare', 'syn', 'all', 'pnr'], default='all')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.flow == 'pnr' and args.output is None:
        parser.error('--flow pnr requires --output of a previously synthesized candidate')
    output = (args.output or ROOT / 'results' /
              datetime.now().strftime('song_guide_full85_clk50_%Y%m%d_%H%M%S_%f')).resolve()
    stage = output / 'Prj1'
    if args.flow != 'pnr':
        originals = json.loads((BASE / 'workstation_inputs.json').read_text())
        assert all(sha(BASE / 'Prj1' / name) == digest for name, digest in originals.items()), 'full84 input drift'
        frozen(BASE / 'Prj1')
        assert not output.exists(), 'do not overwrite an existing candidate'
        shutil.copytree(BASE / 'Prj1', stage,
                        ignore=shutil.ignore_patterns('impl', 'build', '*.user', '__pycache__'))
        for name in OVERLAYS:
            shutil.copy2(ROOT / name, stage / name)
        tcl = stage / 'scripts/build.tcl'
        text = tcl.read_text()
        assert text.count('set_option -user_code 00000084') == 1
        tcl.write_text(text.replace('set_option -user_code 00000084', 'set_option -user_code 00000085'))
        sdc = stage / 'constraints/tang_mega_138k.sdc'
        sdc.write_text(sdc.read_text() + REPORTS)
        inputs = {str(p.relative_to(stage)): sha(p) for p in stage.rglob('*') if p.is_file()}
        changed = sorted(name for name, digest in inputs.items() if originals.get(name) != digest)
        allowed = sorted(OVERLAYS + ['scripts/build.tcl', 'constraints/tang_mega_138k.sdc'])
        assert changed == allowed, (changed, allowed)
        (output / 'workstation_inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        (output / 'build_metadata.json').write_text(json.dumps({
            'baseline': str(BASE.relative_to(ROOT)), 'user_code': '0x00000085',
            'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'changed_from_base': changed, 'frozen_sha256': {k: v[1] for k, v in FROZEN.items()},
            'music_sha256': {str(p.relative_to(stage)): sha(p)
                             for p in (stage / 'rtl/music').rglob('*') if p.is_file()},
            'hardware_tested': False, 'goal': 'clk50 timing closure with BSRAM no greater than 260',
        }, indent=2) + '\n')
    else:
        inputs = json.loads((output / 'workstation_inputs.json').read_text())
        assert all(sha(stage / name) == digest for name, digest in inputs.items()), 'candidate input drift'
    frozen(stage)
    print(output, flush=True)
    if args.flow == 'prepare':
        return
    with (output / ('gowin_' + args.flow + '.log')).open('w') as log:
        result = subprocess.run([str(Path.home() / '.local/bin/gw_sh'), 'scripts/build.tcl'],
                                cwd=stage, env=dict(os.environ, PRJ1_FLOW=args.flow),
                                stdout=log, stderr=subprocess.STDOUT)
    changes = [name for name, digest in inputs.items() if sha(stage / name) != digest]
    frozen(stage)
    record = {
        'exit_code': result.returncode, 'inputs_unchanged': not changes,
        'changed': changes, 'flow': args.flow, 'hardware_tested': False,
    }
    for name in ['tool_result.json', 'tool_result_' + args.flow + '.json']:
        (output / name).write_text(json.dumps(record, indent=2) + '\n')
    if result.returncode or changes:
        raise SystemExit('Gowin/input check failed: ' + str(output))
    report = audit(output, 'full' if args.flow in ('all', 'pnr') else 'synthesis_only')
    print('BSRAM SYN', report['bsram'], 'PNR', report.get('pnr_bsram'), flush=True)
    if args.flow in ('all', 'pnr'):
        assert report['pnr_available'] and report['pnr_bsram'] <= 260, 'BSRAM budget exceeded'


if __name__ == '__main__':
    main()
