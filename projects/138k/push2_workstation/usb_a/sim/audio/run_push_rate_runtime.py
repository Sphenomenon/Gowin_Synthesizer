#!/usr/bin/env python3
"""Actual Push MMIO/CDC/sole clock service and dual-crystal DSP/I2S regression.

Every compile consumes an immutable byte snapshot of the selected sources,
ROM data and included files. The prepared project supplies locked support;
modified workstation owners come from their maintained source paths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from run_runtime_controlled import ROOT, runtime_sources


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--negative', choices=('wrong_target', 'wrong_period'))
    args = ap.parse_args()
    project, out = args.project.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tb = Path(__file__).with_name('tb_workstation_push_rate_runtime.sv')
    sources = runtime_sources(project, tb)
    sources += [ROOT/name for name in (
        'rtl/workstation/workstation_fifo_write_reset.sv', 'rtl/push2_usb_a_control.sv', 'rtl/services/workstation_audio_clock_service.sv',
        'rtl/workstation/workstation_usb2_input.sv', 'rtl/audio/push2_controls.sv',
        'rtl/display_data/push2_surface_pixels.sv', 'rtl/push2/push2_playlist_hold.sv',
        'rtl/push2/push2_song_menu.sv', 'rtl/push2/push2_score_guide.sv',
        'rtl/push2/push2_lights.sv', 'rtl/push2/push2_led_tx.sv', 'rtl/push2/push2_song_screen.sv')]
    sources += [project/name for name in ('src/usb_host/gw138k_usb_event_fifo.v',
        'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v')]
    sources = list(dict.fromkeys(sources))
    inputs = list(dict.fromkeys(sources + [Path(__file__).resolve(),
        Path(__file__).with_name('run_runtime_controlled.py'), ROOT/'tools/workstation_runtime_counter.py',
        ROOT/'rtl/services/workstation_controlled_services.provenance.json']))
    for folder in ('sim/data', 'sim/matlab/output', 'rtl/audio/scope_vec/data'):
        inputs += sorted((project/folder).rglob('*.mem'))
    inputs += [project/'Prj1.gprj', ROOT/'rtl/audio/runtime_spatial_room_preset.svh', project/'rtl/audio/spatial_room_preset.svh',
               project.parents[1]/'workstation_profile.json', project.parents[1]/'integration_inputs.json']
    # Resolve textual includes without substituting production owners.
    for source in inputs:
        if source.suffix not in ('.sv', '.v', '.svh', '.vh'):
            continue
        for name in re.findall(r'`include\s+"([^"]+)"', source.read_text()):
            found = next((p for p in (source.parent/name, ROOT/name, project/name) if p.is_file()), None)
            if found is None:
                raise ValueError('unresolved include '+name+' in '+str(source))
            if found not in inputs:
                inputs.append(found)
    inputs = list(dict.fromkeys(inputs))
    hashes = {str(p): sha(p) for p in inputs}
    snapshot = out/'source-snapshot'
    def frozen(path):
        return snapshot/str(path.resolve()).lstrip('/')
    for path in inputs:
        dest = frozen(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        if sha(dest) != hashes[str(path)]:
            raise ValueError('snapshot drift '+str(path))
    mutation = None
    if args.negative:
        if args.negative == 'wrong_target':
            source_owner = ROOT/'rtl/services/workstation_audio_clock_service.sv'
            before = "push_operation={1'b0,!core_active_44k1_i}"
            after = "push_operation={1'b0,core_active_44k1_i}"
        else:
            source_owner = tb
            before = '22675.73696 : 20833.333248'
            after = '20833.333248 : 22675.73696'
        owner = frozen(source_owner)
        original = owner.read_text()
        if original.count(before) != 1:
            raise ValueError('negative-control anchor drift')
        owner.write_text(original.replace(before, after))
        mutation = dict(name=args.negative, source=str(owner), before_sha256=hashes[str(source_owner)],
                        after_sha256=sha(owner), before=before, after=after)
    snapshot_hashes = {str(frozen(p)):sha(frozen(p)) for p in inputs}
    identity = hashlib.sha256(json.dumps(dict(inputs=hashes,mutation=mutation), sort_keys=True).encode()).hexdigest()
    report = dict(schema=1, passed=False, source_set_sha256=identity, input_sha256=hashes,
        snapshot_sha256=snapshot_hashes, negative_control=mutation,
        prepared_reference_candidate=json.loads((project.parents[1]/'workstation_profile.json').read_text())['candidate_identity'],
        hardware_tested=False, routed_CDC_tested=False,
        configuration=dict(compute_hz=76800000,control_hz=50000000,usb_hz=48000000,memory_hz=100000000,
            qualification_window_cycles=500,stable_windows=3,loss_timeout_cycles=25,stop_low_cycles=8,
            test_startup_mute_frames=512,production_startup_mute_frames=1028,rate_release_quiet_cycles=240000,
            physical_frame_period_tolerance_ns=1),
        scope='Real Push USB MMIO mapper/generated FIFO -> asynchronous production generation bridge -> sole clock service/media policy -> runtime native DSP/DDR model/official DCS/physical I2S decode and final PCM/display context',
        limits='Ideal RTL clocks with shortened qualification/startup. Functional ordered DDR model; USB packets start at the real owner MMIO boundary, not ULPI enumeration. No analog jitter/metastability, routed CDC, HDMI scanout, P&R or hardware acceptance.')
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', 'tb_workstation_push_rate_runtime', '--Mdir', str(out/'obj'),
            '-I'+str(frozen(ROOT)), '-I'+str(frozen(project)), *map(lambda p: str(frozen(p)), sources)]
        report['compile_argv'] = command
        with (out/'compile.log').open('w') as stream:
            subprocess.run(command,cwd=frozen(project),stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=300)
        with (out/'run.log').open('w') as stream:
            process = subprocess.run([str(out/'obj/Vtb_workstation_push_rate_runtime')],cwd=frozen(project),
                stdout=stream,stderr=subprocess.STDOUT,timeout=240)
        log = (out/'run.log').read_text()
        if args.negative:
            marker = 'Push request did not toggle actual committed rate' if args.negative == 'wrong_target' else 'independent physical frame period disagrees with rate'
            report['negative_control_rejected'] = process.returncode != 0 and marker in log
            if not report['negative_control_rejected']:
                raise ValueError('negative control escaped its intended hardware-request assertion')
        elif process.returncode or 'PASS push_rate_runtime ' not in log:
            raise ValueError('missing real runtime coverage marker: '+log[-2000:])
        warnings = (out/'compile.log').read_text().splitlines()
        report['fixture_warnings'] = [line for line in warnings if line.startswith('%Warning-') and 'tb_workstation_push_rate_runtime.sv:' in line]
        report['combinational_loop_warnings'] = [line for line in warnings if line.startswith('%Warning-UNOPTFLAT')]
        if report['fixture_warnings'] or report['combinational_loop_warnings']:
            raise ValueError('new fixture warning/combinational loop')
        report['metrics'] = {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)}
        report['snapshot_unchanged_during_run'] = all(sha(Path(path)) == expected for path,expected in snapshot_hashes.items())
        if not report['snapshot_unchanged_during_run']:
            raise ValueError('frozen compile inputs changed')
        report['live_inputs_unchanged_during_run'] = all(sha(p) == hashes[str(p)] for p in inputs)
        report['passed'] = True
        print(log,end='')
    finally:
        report['logs'] = {p.name:sha(p) for p in (out/'compile.log',out/'run.log') if p.exists()}
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
