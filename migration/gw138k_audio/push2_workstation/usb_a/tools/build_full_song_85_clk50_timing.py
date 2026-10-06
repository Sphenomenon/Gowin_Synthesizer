#!/usr/bin/env python3
"""Build a low-RAM clk50 timing candidate from the complete full84 staging tree.

Preserve the deployed scope/TF integration and all frozen DDR/display sources.
Only explicit overlays, the UserCode, and targeted CDC constraints/reports may differ.
No board I/O and no changes to LATEST_WORKSTATION.json.
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_full_song_83_bp_ddr_isolation import FROZEN
from workstation_memory import audit

BASE = ROOT / 'results/workstation_scope83_20261006_230626_011557'
OVERLAYS = ['rtl/music/basic_pitch_viterbi.sv', 'rtl/music/basic_pitch_cqt_engine.sv',
            'rtl/music/basic_pitch_cqt_frontend.sv', 'rtl/music/basic_pitch_workstation_link.sv']
CDC_CONSTRAINTS = '''
# USB song selection: gw138k_stream_cdc WIDTH=4 held-word/toggle mailbox.
# Source holds payload until ACK; destination waits req_meta/req_sync/req_settled.
# Bound payload flight; only the first metastability sampling stage is async.
set_max_delay 20.000 -from [get_regs {u_song_command_cdc/held_data*}] -to [get_regs {u_song_command_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_song_command_cdc/held_data*}] -to [get_regs {u_song_command_cdc/destination_data*}]
set_false_path -to [get_pins {u_song_command_cdc/req_meta*/D u_song_command_cdc/ack_meta*/D}]
# Async reset enters three-bit local release chains. Keep release-Q -> business
# CLEAR recovery/removal and release-chain D paths under ordinary local STA.
set_false_path -to [get_pins {u_song_command_cdc/source_release*/CLEAR u_song_command_cdc/destination_release*/CLEAR}]
'''
# Registered Gray pointers may change on every source edge, so constrain bus
# flight below both source/destination periods. The final Gray bit aliases the
# registered binary MSB after optimization; select that bit only, never all binary bits.
for _instance, _read, _write, _meta_read, _meta_write, _msb, _bound in [
    ('u_tf_audio/u_pcm_cdc', 'rd_gray', 'wr_gray', 'rd_gray_w1', 'wr_gray_r1', 4, 10),
    ('u_score_push_cdc', 'read_gray', 'write_gray', 'read_gray_meta', 'write_gray_meta', 2, 10),
    ('u_playlist_bridge/fifo', 'read_gray', 'write_gray', 'read_gray_meta', 'write_gray_meta', 2, 10),
]:
    for _gray, _meta, _binary in [(_read, _meta_read, 'rd_bin' if _read == 'rd_gray' else 'read_binary'),
                                (_write, _meta_write, 'wr_bin' if _write == 'wr_gray' else 'write_binary')]:
        _source = f'{_instance}/{_gray}* {_instance}/{_binary}_{_msb}*'
        _target = f'{_instance}/{_meta}*'
        CDC_CONSTRAINTS += (f'\nset_max_delay {_bound}.000 -from [get_regs {{{_source}}}] -to [get_regs {{{_target}}}]\n'
                            f'set_false_path -hold -from [get_regs {{{_source}}}] -to [get_regs {{{_target}}}]\n')
CDC_CONSTRAINTS += '''
# Audio diagnostic levels now enter two explicit clk50 stages. Keep meta->sync
# and all downstream CE/UART consumers under normal 20ns setup/hold checking.
set_false_path -to [get_pins {u_music/format_meta*/D u_music/source_meta*/D}]
'''
REPORTS = '''
# Diagnose clk50 without changing its 20ns constraint or any timing exceptions.
report_timing -setup -from_clock [get_clocks {clk_50m}] -to_clock [get_clocks {clk_50m}] -max_paths 100
report_timing -hold -from_clock [get_clocks {clk_50m}] -to_clock [get_clocks {clk_50m}] -max_paths 25
report_timing -setup -to_clock [get_clocks {clk_50m}] -max_paths 100
report_timing -recovery -to_clock [get_clocks {clk_50m}] -max_paths 25
report_timing -removal -to_clock [get_clocks {clk_50m}] -max_paths 25
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
    reuse = parser.add_mutually_exclusive_group()
    reuse.add_argument('--reroute-from', type=Path,
                       help='reuse completed full85 synthesis and P&R when only constraints differ')
    reuse.add_argument('--incremental-from', type=Path,
                       help='fresh synthesis with a completed full84/85 placement+route reference')
    args = parser.parse_args()
    reuse_from = args.reroute_from or args.incremental_from
    if args.incremental_from is not None and args.flow not in ('all', 'prepare', 'syn'):
        parser.error('--incremental-from requires a new all/prepare/syn candidate')
    if args.reroute_from is not None and args.flow not in ('all', 'prepare'):
        parser.error('--reroute-from requires a new all/prepare candidate')
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
        sdc.write_text(sdc.read_text() + CDC_CONSTRAINTS + REPORTS)
        if reuse_from is not None:
            previous_pnr = reuse_from.resolve() / 'Prj1/impl/pnr'
            reused_point = previous_pnr / ('Prj1.pr' if (previous_pnr / 'Prj1.pr').exists() else 'Prj1.p')
            reuse_name = 'reused' + reused_point.suffix
            tcl.write_text(tcl.read_text().replace(
                'set flow all', f'set_option -inc_pnr [file join $root build {reuse_name}]\nset flow all'))
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
    if reuse_from is not None:
        previous = reuse_from.resolve()
        old_record = json.loads((previous / 'tool_result.json').read_text())
        old_metadata = json.loads((previous / 'build_metadata.json').read_text())
        assert old_record['exit_code'] == 0 and old_record['inputs_unchanged'], 'old build incomplete'
        old_header = (previous / 'Prj1/impl/pnr/Prj1.fs').read_text()[:1000]
        old_code = re.search(r'//UserCode: (0x[0-9A-Fa-f]{8})', old_header)[1].lower()
        assert old_code in ('0x00000084', '0x00000085'), 'unexpected incremental reference identity'
        if args.reroute_from is not None:
            assert old_code == '0x00000085', 'reuse synthesis only for the same full85 identity'
        old_inputs = json.loads((previous / 'workstation_inputs.json').read_text())
        assert all(sha(previous / 'Prj1' / name) == digest for name, digest in old_inputs.items()), 'old input drift'
        exceptions = {'scripts/build.tcl', 'constraints/tang_mega_138k.sdc'}
        if args.incremental_from is not None:
            exceptions.update(OVERLAYS)
        old_logic = {name: digest for name, digest in old_inputs.items() if name not in exceptions}
        new_logic = {name: digest for name, digest in inputs.items() if name not in exceptions}
        assert old_logic == new_logic, 'RTL/IP/memory changed: fresh synthesis required'
        def without_incremental(text):
            return '\n'.join(line for line in text.splitlines() if not line.startswith(('set_option -inc_pnr', 'set_option -user_code')))
        assert without_incremental((previous / 'Prj1/scripts/build.tcl').read_text()) == \
               without_incremental((stage / 'scripts/build.tcl').read_text()), 'tool options changed'
        old_pnr = previous / 'Prj1/impl/pnr'
        assert all((old_pnr / name).is_file() for name in ['Prj1.p', 'Prj1.fs', 'Prj1.sdf']), 'old P&R incomplete'
        frozen(previous / 'Prj1')
        old_syn = previous / 'Prj1/impl/gwsynthesis'
        reused = {}
        if args.reroute_from is not None:
            assert (old_syn / 'Prj1.vg').is_file(), 'old netlist missing'
            shutil.copytree(old_syn, stage / 'impl/gwsynthesis')
            reused = {str(p.relative_to(old_syn)): sha(p) for p in old_syn.rglob('*') if p.is_file()}
            assert all(sha(stage / 'impl/gwsynthesis' / name) == digest for name, digest in reused.items()), 'copy drift'
        (stage / 'build').mkdir(exist_ok=True)
        shutil.copy2(reused_point, stage / 'build' / reuse_name)
        assert sha(stage / 'build' / reuse_name) == sha(reused_point), 'placement/route copy drift'
        metadata_path = output / 'build_metadata.json'
        metadata = json.loads(metadata_path.read_text())
        metadata['reuse_from'] = str(previous.relative_to(ROOT))
        metadata['reuse_source_code'] = old_code
        metadata['reuse_mode'] = 'constraints-only' if args.reroute_from is not None else 'fresh synthesis; incremental P&R'
        metadata['reused_synthesis_sha256'] = reused
        metadata['reused_point_file'] = 'build/' + reuse_name
        metadata['reused_point_sha256'] = sha(stage / 'build' / reuse_name)
        metadata['reuse_point_kind'] = 'placement+routing' if reused_point.suffix == '.pr' else 'placement'
        metadata['reuse_basis'] = ('all RTL/IP/memory inputs identical; only SDC/report commands differ'
                                   if args.reroute_from is not None else
                                   'all non-overlay RTL/IP/memory inputs and tool options identical; fresh synthesis for explicit overlays')
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
    frozen(stage)
    print(output, flush=True)
    if args.flow == 'prepare':
        return
    actual_flow = 'pnr' if args.reroute_from is not None else args.flow
    with (output / ('gowin_' + actual_flow + '.log')).open('w') as log:
        result = subprocess.run([str(Path.home() / '.local/bin/gw_sh'), 'scripts/build.tcl'],
                                cwd=stage, env=dict(os.environ, PRJ1_FLOW=actual_flow),
                                stdout=log, stderr=subprocess.STDOUT)
    changes = [name for name, digest in inputs.items() if sha(stage / name) != digest]
    metadata = json.loads((output / 'build_metadata.json').read_text())
    for name, digest in metadata.get('reused_synthesis_sha256', {}).items():
        if sha(stage / 'impl/gwsynthesis' / name) != digest:
            changes.append('reused synthesis:' + name)
    if 'reused_point_file' in metadata and sha(stage / metadata['reused_point_file']) != metadata['reused_point_sha256']:
        changes.append('reused placement/route')
    frozen(stage)
    record = {
        'exit_code': result.returncode, 'inputs_unchanged': not changes,
        'changed': changes, 'flow': actual_flow, 'requested_flow': args.flow, 'hardware_tested': False,
    }
    for name in ['tool_result.json', 'tool_result_' + actual_flow + '.json']:
        (output / name).write_text(json.dumps(record, indent=2) + '\n')
    if result.returncode or changes:
        raise SystemExit('Gowin/input check failed: ' + str(output))
    report = audit(output, 'full' if args.flow in ('all', 'pnr') else 'synthesis_only')
    print('BSRAM SYN', report['bsram'], 'PNR', report.get('pnr_bsram'), flush=True)
    if args.flow in ('all', 'pnr'):
        assert report['pnr_available'] and report['pnr_bsram'] <= 260, 'BSRAM budget exceeded'


if __name__ == '__main__':
    main()
