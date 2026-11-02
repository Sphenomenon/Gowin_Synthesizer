#!/usr/bin/env python3
"""Build real runtime/PCM workload library for LCD cosim; smoke is model-only."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.prepare_ae350_sbc import prepare


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_library(output, run_smoke=True):
    """Build the C ABI and dependencies; return an absolute static-library Path.

    The caller must use an absent output directory. verification.json records
    all commands, source hashes and test scope next to the returned library.
    """
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    fw = ROOT / 'firmware/ae350'
    fixture = ROOT / 'sim/fixtures/task3_phone_firmware_workload.c'
    smoke = ROOT / 'sim/fixtures/task3_phone_firmware_smoke.c'
    header = ROOT / 'sim/fixtures/task3_phone_firmware_workload.h'
    firstparty_sources = [fixture, *[fw / name for name in (
        'hci_transport.c', 'classic_security.c', 'classic_service.c',
        'sbc_decoder_service.c', 'pcm_media.c', 'audio_clock_service.c')]]

    def source_inputs():
        # Bind the included private runtime, every actual first-party C/header,
        # adaptation implementation, arithmetic adapter, vendor manifest and
        # frozen upstream inventory before prepare or the compiler reads them.
        paths = [Path(__file__).resolve(), smoke, header, fw / 'classic_runtime.c',
                 *firstparty_sources, *sorted(fw.glob('*.h')),
                 ROOT / 'tools/prepare_ae350_sbc.py',
                 *sorted(p for p in (fw / 'third_party/sbc_oi').rglob('*') if p.is_file())]
        return {str(p.relative_to(ROOT)): sha(p) for p in paths}

    def adapted_inputs():
        return {str(p.relative_to(out / 'adapted')): sha(p)
                for p in sorted((out / 'adapted').rglob('*')) if p.is_file()}

    before = source_inputs()
    report = dict(schema='task3-phone-real-firmware-workload-v2', passed=False,
                  inputs=before, source_unchanged=False, adapted_unchanged=False,
                  scope='Unmodified real four-pass runtime and PCM media; injected established session/decoded PCM and local idle HCI; checked-model smoke only')
    adaptation = prepare(ROOT, out / 'adapted')
    # prepare checks the entire frozen upstream against its versioned manifest.
    # Also bind the exact separately adapted compilation tree, including the
    # adaptation receipt, before any native or sanitized compilation starts.
    adapted_before = adapted_inputs()
    if {k: v for k, v in adapted_before.items() if k != 'adaptation.json'} != adaptation['adapted_sha256']:
        raise ValueError('prepared SBC decoder differs from its adaptation identity')
    dec = out / 'adapted/decoder'
    sources = [*firstparty_sources, *sorted((dec / 'srce').glob('*.c'))]
    cc = Path(shutil.which('cc')).resolve()
    ar = Path(shutil.which('ar')).resolve()
    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
             '-DA138_WORKER_AUDIO_ONLY', '-DA138_SINGLE_BLE_RECORDING',
             '-I' + str(fw), '-I' + str(header.parent),
             '-I' + str(dec / 'include'), '-I' + str(dec / 'srce')]
    commands = []

    def run(argv, log):
        result = subprocess.run(list(map(str, argv)), text=True, capture_output=True, timeout=120)
        (out / (log + '.log')).write_text(result.stdout + result.stderr)
        commands.append(dict(argv=list(map(str, argv)), returncode=result.returncode))
        if result.returncode:
            raise RuntimeError((log, result.returncode, result.stdout, result.stderr))
        return result

    report.update(adaptation=adaptation, adapted_inputs=adapted_before, commands=commands,
                  compiler=dict(path=str(cc), sha256=sha(cc)),
                  archiver=dict(path=str(ar), sha256=sha(ar)),
                  callback_lanes=dict(PCM1=0, audio_clock=1),
                  production_capability_bit3=False, test_capability_read_injection=True,
                  maximum_new_decodes_per_pump=1, PCM_wait_timeout_ms=100,
                  maximum_private_pending_blocks=1, maximum_stereo_words_per_submit=16,
                  native_RTL_verified=False, CPU_cycles_measured=False,
                  HCI_SBC_RF_verified=False, hardware_tested=False)
    library = out / 'libtask3_phone_workload.a'
    try:
        objects = []
        for i, source in enumerate(sources):
            obj = out / (str(i) + '-' + source.stem + '.o')
            run([cc, *flags, '-c', source, '-o', obj], 'compile-' + str(i))
            objects.append(obj)
        run([ar, 'rcs', library, *objects], 'archive')
        summaries = {}
        variants = [('native', []), ('sanitized', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]
        for tag, extra in variants if run_smoke else []:
            exe = out / ('smoke-' + tag)
            # Instrument all actual sources in the sanitizer variant.
            link_inputs = [library] if tag == 'native' else sources
            run([cc, *flags, *extra, smoke, *link_inputs, '-o', exe], 'smoke-' + tag + '-compile')
            result = run([exe], 'smoke-' + tag)
            if 'Sanitizer' in result.stderr or 'runtime error:' in result.stderr:
                raise RuntimeError('sanitizer finding')
            summaries[tag] = result.stdout.strip()
        report.update(summaries=summaries, library=dict(path=str(library), sha256=sha(library)))
        after, adapted_after = source_inputs(), adapted_inputs()
        report['source_unchanged'] = before == after
        report['adapted_unchanged'] = adapted_before == adapted_after
        report['source_changes'] = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        report['adapted_changes'] = sorted(k for k in adapted_before.keys() | adapted_after.keys()
                                           if adapted_before.get(k) != adapted_after.get(k))
        if not report['source_unchanged'] or not report['adapted_unchanged']:
            raise ValueError('firmware workload inputs changed during build or smoke verification')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(library=report['library'], summaries=report['summaries'],
                          source_unchanged=report['source_unchanged'],
                          adapted_unchanged=report['adapted_unchanged'], scope=report['scope']), indent=2))
    return library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build_library(args.output)


if __name__ == '__main__':
    main()
