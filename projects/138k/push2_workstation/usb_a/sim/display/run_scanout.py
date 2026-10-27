#!/usr/bin/env python3
"""Check real-width scanout pixels, stable frames and late-line recovery."""

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-queues', action='store_true')
    parser.add_argument('--frame-publication', action='store_true')
    parser.add_argument('--hdmi-mode', choices=('1080p60', '720p30', '720p60'), default='1080p60')
    parser.add_argument('--read-latency-cycles', type=int, default=64)
    arguments = parser.parse_args()
    if arguments.read_latency_cycles < 1:
        parser.error('--read-latency-cycles must be positive')
    project = arguments.project.resolve()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [project / 'rtl/memory/workstation_sdp.sv',
               project / 'src/video/video_ddr_scanout.v',
               Path(__file__).with_name('tb_video_scanout.sv')]
    top = 'tb_video_scanout'
    labels = ('stable_and_swapped_frames', 'late_line_recovery', 'late_epoch_recovery')
    if arguments.frame_publication:
        if arguments.native_queues:
            parser.error('--frame-publication is a separate writer/view boundary test')
        top = 'tb_video_frame_publication'
        labels = ('frame_publication',)
        sources = [project / 'src/memory/ddr_frame_writer.v',
                   project / 'src/ae350/gw138k_view_select.sv',
                   Path(__file__).with_name('tb_video_frame_publication.sv')]
    if arguments.native_queues:
        sources.extend([project / 'rtl/timing/basic_pitch_ddr_client_queues.sv',
                        project / 'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv'])
    inputs = sources + [project / 'src/memory/ddr_address_map.vh', Path(__file__).resolve()]
    evidence = dict(scope='staged_scanout_behavioral_not_physical_ddr_or_workstation_acceptance',
                    project=str(project), hardware_tested=False, board_accessed=False,
                    native_queues=arguments.native_queues,
                    frame_publication=arguments.frame_publication,
                    hdmi_mode=arguments.hdmi_mode,
                    read_latency_cycles=arguments.read_latency_cycles,
                    input_sha256={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
                    cases=[])
    for path in inputs:
        shutil.copy2(path, output / path.name)
    command = ['iverilog', '-g2012', '-s', top, '-I', str(project),
               '-o', str(output / 'scanout.vvp'), *map(str, sources)]
    if not arguments.frame_publication:
        command.insert(1, f'-Ptb_video_scanout.READ_LATENCY_CYCLES={arguments.read_latency_cycles}')
        command.insert(1, f'-Ptb_video_scanout.USE_QUEUES={int(arguments.native_queues)}')
        command.insert(1, f'-Ptb_video_scanout.VIDEO_720P30={int(arguments.hdmi_mode == "720p30")}')
        command.insert(1, f'-Ptb_video_scanout.VIDEO_720P60={int(arguments.hdmi_mode == "720p60")}')
    compiled = subprocess.run(command, cwd=project, capture_output=True, text=True)
    (output / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    evidence['compile_command'] = command
    evidence['compile_returncode'] = compiled.returncode
    if compiled.returncode == 0:
        for mode, label in enumerate(labels):
            command = ['vvp', str(output / 'scanout.vvp'), f'+MODE={mode}']
            result = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=120)
            log = output / f'{label}.log'
            log.write_text(result.stdout + result.stderr)
            passed = result.returncode == 0 and f'PASS mode={mode} ' in result.stdout
            evidence['cases'].append(dict(case=label, command=command, returncode=result.returncode,
                                          passed=passed, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
            print(label, result.stdout.strip(), flush=True)
    evidence['passed'] = compiled.returncode == 0 and len(evidence['cases']) == len(labels) and all(
        case['passed'] for case in evidence['cases'])
    (output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    if not evidence['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
