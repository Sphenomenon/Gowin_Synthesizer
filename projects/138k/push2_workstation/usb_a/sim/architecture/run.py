#!/usr/bin/env python3
"""Source-bound architecture miters against the pre-refactor composition."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_composition import verify


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, reference, output = args.project.resolve(), args.reference.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence = json.loads((project.parent / 'workstation_composition.json').read_text())
    verify(project, evidence)
    top = reference / 'src/push2/gw138k_push_workstation_top.v'
    original = top.read_text()
    start = original.index('    reg music_model_ready_q;')
    end = original.index('    assign debug_uart_tx=', start)
    block = original[start:end].replace("22'd2_500_000", "22'd16").replace("29'd480_000_000", "29'd24")
    golden = output / 'workstation_playback_reference.sv'
    golden.write_text('''module workstation_playback_reference (
        input wire clk_50m, reset_n,
        input wire [3:0] music_model_status,
        input wire tf_mode_50, tf_scope_restart, tf_scope_cancel,
        input wire [3:0] tf_scope_track,
        input wire song_cmd_valid,
        input wire [3:0] song_cmd_index,
        input wire playlist_scan_done,
        input wire [3:0] tf_track_count,
        input wire tf_card_lost, music_analysis_done,
        output wire [8:0] observed_o
    );
    reg song_pending;
''' + block + '''
    assign observed_o = {music_analysis_enable, music_analysis_restart,
        !tf_mode_50 && music_model_ready_q && music_song_started && !music_analysis_done,
        tf_scope_restart || (!tf_mode_50 && (tf_restart || tf_song_restart)),
        tf_mode_50 ? tf_scope_track : tf_selected_track,
        !song_pending && !song_cmd_valid && !tf_card_lost};
endmodule
''')
    tests = {
        'workstation_playback': [project / 'rtl/services/workstation_playback_service.sv', golden],
        'workstation_output': [project / 'rtl/audio/workstation_output_router.sv',
            project / 'rtl/audio/scope_vec/scope_dac_select.sv',
            project / 'src/audio/pt8211_tx.v', project / 'src/audio/pt8211_observer.v'],
    }
    inputs = {top, Path(__file__).resolve(), project.parent / 'workstation_composition.json'}
    for name, sources in tests.items():
        sources.append(HERE / ('tb_' + name + '.sv'))
        inputs.update(sources)
    hashes = {str(path): digest(path) for path in sorted(inputs)}
    (output / 'inputs.json').write_text(json.dumps(hashes, indent=2) + '\n')
    result = {'passed': False, 'tests': {}, 'hardware_tested': False,
              'project': str(project), 'reference': str(reference),
              'scope': 'cycle-exact playback policy and serial output/tap extraction'}
    try:
        for name, sources in tests.items():
            binary = output / name
            commands = [
                ('compile', ['iverilog', '-g2012', '-s', 'tb_' + name, '-o', str(binary), *map(str, sources)]),
                ('run', ['vvp', str(binary)]),
            ]
            for step, command in commands:
                log = output / (name + '_' + step + '.log')
                with log.open('w') as stream:
                    subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                                   check=True, timeout=120)
            text = (output / (name + '_run.log')).read_text()
            if 'PASS ' + name not in text:
                raise ValueError('missing boundary verification: ' + name)
            result['tests'][name] = text.strip()
            print(text, end='', flush=True)
        if hashes != {str(path): digest(path) for path in sorted(inputs)}:
            raise ValueError('verification input drift')
        verify(project, evidence)
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
