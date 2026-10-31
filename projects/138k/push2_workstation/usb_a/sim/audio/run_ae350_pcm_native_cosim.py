#!/usr/bin/env python3
"""Real C PCM callbacks through native APB/CDC, DSP and decoded I2S pins.

The native capability is always 0x67. An explicit C read wrapper injects bit 3
only after checking that the actual default causes no writes. This exercises
future enabled behavior without changing firmware or asserting sustained proof.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from run_runtime_controlled import runtime_sources, ROOT

MUTANTS = {
    'capability-gate': (
        'if(!(caps&8u))return 1;', 'if(!(caps&4u))return 1;',
        'actual cap3 false fails closed'),
    'partial-accept': (
        'if(d->offset!=d->frames)return A138_CLASSIC_REJECTED;',
        'if(d->offset!=d->frames)return A138_CLASSIC_ACCEPTED;',
        'one full 128-frame block commits once'),
    'mono-channel': (
        'pcm[at*channels+(channels==2u)]', 'pcm[at*channels+1u]',
        'C complete block payload differs'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(project, output, negative_control=None):
    project, output = project.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fw = ROOT / 'firmware/ae350'
    here = Path(__file__).resolve().parent
    sources = runtime_sources(project, here / 'ae350_pcm_native_cosim.sv') + [
        ROOT / 'rtl/audio/workstation_ae350_pcm_owner.sv',
        ROOT / 'rtl/audio/workstation_ae350_pcm_session.sv']
    cpp = here / 'ae350_pcm_native_cosim.cpp'
    includes = [fw, fw / 'third_party/sbc_oi/upstream/decoder/include']
    inputs = list(dict.fromkeys(sources + [cpp, Path(__file__).resolve(),
        here / 'run_runtime_controlled.py', ROOT / 'tools/workstation_runtime_counter.py',
        fw / 'pcm_media.c', fw / 'audio_clock_service.c',
        ROOT / 'rtl/audio/runtime_spatial_room_preset.svh',
        project / 'rtl/audio/spatial_room_preset.svh',
        *sorted(fw.glob('*.h')), *sorted(includes[1].glob('*.h'))]))
    for folder in ['sim/data', 'sim/matlab/output', 'rtl/audio/scope_vec/data']:
        inputs += sorted((project / folder).rglob('*.mem'))
    hashes = {str(p): sha(p) for p in inputs}
    executables = {name: Path(shutil.which(name)).resolve()
                   for name in ['clang', 'c++', 'verilator', 'verilator_bin', 'make']}
    result = dict(schema='ae350-pcm-native-cosim-v1', passed=False,
        input_sha256=hashes, tool_sha256={str(p): sha(p) for p in executables.values()},
        actual_C_callbacks=True, actual_APB_CDC=True, native_effects=True,
        unique_final_volume=True, decoded_I2S_pins=True, native_capabilities=0x67,
        test_only_capability3_read_wrapper=True, sustained_verified=False,
        total_delay_verified=False, actual_firmware_enabled=False,
        durable_bond_backend=False, SBC_decoder_in_this_fixture=False,
        CPU_cycles_measured=False, physical_CDC_verified=False,
        physical_timing_verified=False, hardware_tested=False, phone_interoperability=False,
        negative_control=negative_control,
        limits='Ideal clocks, ordered owner-6 DDR model and bounded injected decoded PCM. '
               'Actual C adapter/APB/CDC/native DSP/I2S are exercised; full HCI/SBC runtime, '
               'physical resource/timing, sustained frequency drift and phone are separate.')
    commands = []
    try:
        c_source = fw / 'pcm_media.c'
        if negative_control:
            old, new, _ = MUTANTS[negative_control]
            text = c_source.read_text()
            if text.count(old) != 1:
                raise ValueError('mutant anchor drift: ' + negative_control)
            c_source = output / ('mutant_' + negative_control + '.c')
            c_source.write_text(text.replace(old, new))
            result['mutant_sha256'] = sha(c_source)
        flags = ['-I' + str(p) for p in includes]
        for name, source in [('pcm_media', c_source), ('audio_clock_service', fw / 'audio_clock_service.c')]:
            argv = [str(executables['clang']), '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-O2', *flags, '-c', str(source), '-o', str(output / (name + '.o'))]
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            (output / (name + '-compile.log')).write_text(completed.stdout + completed.stderr)
            commands.append(dict(argv=argv, returncode=completed.returncode))
            if completed.returncode:
                raise ValueError(name + ' C compile failed')
        argv = [str(executables['verilator']), '--cc', '--exe', '--build', '--timing',
            '-j', '4', '-Wno-fatal', '--top-module', 'ae350_pcm_cosim',
            '--Mdir', str(output / 'obj'), '-I' + str(ROOT), '-I' + str(project),
            '-CFLAGS', ' '.join(flags), '-LDFLAGS',
            str(output / 'pcm_media.o') + ' ' + str(output / 'audio_clock_service.o'),
            *map(str, sources), str(cpp)]
        with (output / 'compile.log').open('w') as log:
            compiled = subprocess.run(argv, cwd=project, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        commands.append(dict(argv=argv, returncode=compiled.returncode))
        if compiled.returncode:
            raise ValueError('native RTL/C++ compile failed')
        binary = output / 'obj/Vae350_pcm_cosim'
        with (output / 'run.log').open('w') as log:
            completed = subprocess.run([str(binary)], cwd=project, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        commands.append(dict(argv=[str(binary)], returncode=completed.returncode))
        log = (output / 'run.log').read_text()
        if negative_control:
            expected = MUTANTS[negative_control][2]
            if completed.returncode == 0 or expected not in log:
                raise ValueError('negative control survived or failed for wrong reason: ' + negative_control)
            result['negative_control_killed'] = True
            result['expected_failure'] = expected
        else:
            if completed.returncode or 'PASS actual C PCM callbacks/APB/CDC/native DSP/one-volume/I2S:' not in log:
                raise ValueError('native PCM C co-simulation failed')
            metrics = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', log)}
            if metrics.get('complete_words', 0) != metrics.get('complete_blocks', 0) * 128:
                raise ValueError('whole-block assertion coverage changed')
            result['metrics'] = metrics
        if any(sha(Path(p)) != h for p, h in hashes.items()):
            raise ValueError('source input drift during run')
        result['inputs_unchanged_during_run'] = True
        result['passed'] = True
        print(log, end='')
    finally:
        result['commands'] = commands
        result['output_sha256'] = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*'))
                                   if p.is_file() and p.name != 'verification.json'}
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative-control', choices=MUTANTS)
    args = parser.parse_args()
    run(args.project, args.output, args.negative_control)
