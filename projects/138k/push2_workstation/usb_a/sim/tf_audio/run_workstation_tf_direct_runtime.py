#!/usr/bin/env python3
"""Real runtime/DSP/DMA plus native SPI/FAT/WAV to physical I2S and tail receipt.

Initial integration cases cover 48/44.1 kHz stereo16 only. FAST2 is explicit
digital protocol stimulus, not measured real-card throughput or IO validation.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / 'sim/tf_audio'
TB = SIM / 'tb_workstation_tf_direct_runtime.sv'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rate', type=int, action='append', choices=(48000, 44100))
    parser.add_argument('--pause', action='store_true', help='Also check real CC pause/resume and retained TF head')
    parser.add_argument('--local-compute-release',action='store_true',
                        help='Select the explicit preboard functional compute reset boundary')
    parser.add_argument('--local-native-head',action='store_true',
                        help='Select the bounded M preboard PCM head before the native RAM')
    parser.add_argument('--cold-start', action='store_true',
                        help='Use actual production reset_release, fixed external reset high and HOLD_CYCLES=1024')
    case_modes = dict(play=0, pause=1, cancel=2, stop=3, panic=4, invalid_track=5,
                      cancel_inflight=6, stop_inflight=7)
    parser.add_argument('--case', action='append', choices=tuple(case_modes),
                        help='Repeat for a selected boundary matrix; default: play')
    args = parser.parse_args()
    project = args.project.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT))
    controlled = module('controlled_sources', ROOT / 'sim/audio/run_runtime_controlled.py')
    native = module('native_wire_vectors', SIM / 'run_workstation_tf_direct_native_wire.py')
    sources = controlled.runtime_sources(project, TB)
    # The real direct-runtime integration needs the maintained transport
    # command edges and counter watermark port. Older prepare trees retain
    # their historical interfaces, so select these production owners here.
    replacements = {
        project / 'src/migration/gw138k_counter_cdc.sv':
            ROOT / 'rtl/migration/workstation_runtime_counter_cdc.sv',
        project / 'rtl/audio/scope_vec/scope_tf_transport.sv':
            ROOT / 'rtl/audio/scope_vec/scope_tf_transport.sv',
    }
    sources = [replacements.get(path, path) for path in sources]
    # The maintained runtime DMA/effect implementation replaces same-name
    # staged dependencies. Do not elaborate a duplicate owner from both trees.
    maintained_names = {path.name for path in sources if path.is_relative_to(ROOT)}
    sources = [path for path in sources if not (
        path.is_relative_to(project / 'rtl/audio/delay_ddr') and path.name in maintained_names)]
    sources += [project / 'src/platform/reset_release.v',
                ROOT / 'rtl/memory/workstation_runtime_memory_guard.sv',
                *native.SOURCES, ROOT / 'rtl/tf_audio/workstation_tf_frame_bridge_v2.sv',
                ROOT / 'rtl/tf_audio/workstation_tf_physical_tail_v1.sv',
                ROOT / 'rtl/tf_audio/workstation_tf_direct_runtime_service.sv',
                ROOT / 'rtl/services/workstation_playback_service.sv', native.CARD]
    sources = list(dict.fromkeys(sources))
    inputs = [*sources, Path(__file__).resolve(), ROOT / 'sim/audio/run_runtime_controlled.py',
              SIM / 'run_workstation_tf_direct_native_wire.py', SIM / 'run_workstation_tf_direct_ingress.py',
              ROOT / 'rtl/audio/runtime_spatial_room_preset.svh']
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    inputs += sorted((project / 'rtl/audio/scope_vec/data').glob('*.mem'))
    inputs += [project / 'rtl/audio/spatial_room_preset.svh']
    if args.cold_start:
        inputs += [ROOT / 'rtl/workstation/gw138k_push_workstation_top.v']
    for path in inputs:
        if not path.is_file():
            raise ValueError('required real runtime source/data absent: ' + str(path))
    hashes = {str(path): sha(path) for path in inputs}
    result = dict(schema=1, passed=False, input_sha256=hashes, cases={},
                  actual_runtime_controlled=True, actual_DSP=True, actual_SPI_FAT_WAV=True,
                  actual_router_PCM_bridge_I2S_observation=True, fake_renderer=False,
                  source_format_tested='stereo16 only', SPI_FAST_test_divider=2,
                  real_card_throughput_measured=False, whole_workstation_owner4_trace_verified=False,
                  separate_common_reset_startup_exercised=True,
                  actual_root_reset_release_fixed_ext_reset=args.cold_start,
                  actual_memory_guard_startup_grant=args.cold_start,
                  local_compute_functional_release_selected=args.local_compute_release,
                  local_native_PCM_head_selected=args.local_native_head,
                  reset_release_hold_cycles=1024 if args.cold_start else None,
                  actual_top_elaborated=False,
                  whole_runtime_clock_stop_verified=False, native_file_error_remount_verified=False,
                  in_flight_SD_sector_cancel_verified=False,
                  physical_CDC_verified=False, hardware_operated=False, deployment_allowed=False,
                  limits='Ordered owner6 DDR model, constructed external SD card, stereo16 only, shortened startup/qualification. Initial six cases use short fully prefetched files; explicit inflight cases use 4097-frame first files. No whole-runtime clock-stop, native file-error/remount, selected whole-board arbitration/P&R/hardware claim')
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '-GLOCAL_COMPUTE_RESET_ENABLE='+str(int(args.local_compute_release)),
                   '-GLOCAL_NATIVE_HEAD_ENABLE='+str(int(args.local_native_head)),
                   '--top-module', 'tb_workstation_tf_direct_runtime', '--Mdir', str(output / 'obj'),
                   '-I' + str(ROOT), '-I' + str(project), *map(str, sources)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        cases = args.case or ['play']
        if args.pause and 'pause' not in cases:
            cases += ['pause']
        for rate, case in [(rate, case) for rate in args.rate or (48000, 44100) for case in cases]:
            mode = case_modes[case]
            name = f'real_runtime_stereo16_{rate}' + ('_' + case if mode else '')
            if args.cold_start:
                name += '_cold_start'
            folder = output / name
            first_frames = 4097 if mode >= 6 else 97
            disk = native.disk(folder, 16, False, rate, first_frames, 97, 0)
            command = [str(output / 'obj/Vtb_workstation_tf_direct_runtime'),
                       '+IMAGE=' + str(folder / 'image.hex'), '+LBAS=' + str(folder / 'lbas.hex'),
                       '+ORACLE0=' + str(folder / 'oracle0.hex'), '+ORACLE1=' + str(folder / 'oracle1.hex'),
                       '+RATE=' + str(rate), '+FIRST_FRAMES=' + str(first_frames),
                       '+FRAMES=97', '+MODE=' + str(mode), '+COLD_START=' + str(int(args.cold_start))]
            with (folder / 'run.log').open('w') as stream:
                subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=240)
            log = (folder / 'run.log').read_text()
            if 'PASS tf_direct_runtime ' not in log:
                raise ValueError('missing real runtime validation: ' + name)
            result['cases'][name] = dict(passed=True, disk=disk,
                first_file_frames=first_frames, second_file_frames=97,
                in_flight_SD_sector_cancel_verified=(mode >= 6),
                metrics={key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)},
                run_argv=command, run_log_sha256=sha(folder / 'run.log'))
            print(log, end='')
        warnings = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            warnings[name] = warnings.get(name, 0) + 1
        result['warning_counts'] = warnings
        if 'UNOPTFLAT' in warnings:
            raise ValueError('combinational loop in real runtime closure')
        result['inputs_unchanged_during_run'] = hashes == {str(path): sha(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('runtime input drift during test')
        result['compile_log_sha256'] = sha(output / 'compile.log')
        result['in_flight_SD_sector_cancel_verified'] = any(
            item['in_flight_SD_sector_cancel_verified'] for item in result['cases'].values())
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
