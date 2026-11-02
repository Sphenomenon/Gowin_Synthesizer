#!/usr/bin/env python3
"""Compare one real CQT engine across DDR and local signal/coeff storage."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
TB = Path(__file__).with_name('tb_cqt_storage_equivalence.sv')
SOURCES = [ROOT / 'rtl/music/basic_pitch_cqt_engine.sv',
           ROOT / 'rtl/music/basic_pitch_ddr_coeff_pair.sv']
WEIGHTS = ['cnn_ddr_blob.mem', 'cqt_real.mem', 'cqt_imag.mem',
           'cqt_lowpass.mem', 'cqt_norm_log.mem', 'log2_lut.mem']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def words(path):
    return [int(word, 16) for word in Path(path).read_text().split()]


def fields(line):
    return {key: int(value) if value.isdecimal() else value
            for key, value in (item.split('=', 1) for item in line.split()[1:])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = (args.output or ROOT / 'out' /
           datetime.now().strftime('cqt_storage_%Y%m%d_%H%M%S')).resolve()
    out.mkdir(parents=True, exist_ok=False)
    weight_paths = [ROOT / 'rtl/music/weights' / name for name in WEIGHTS]
    tracked = [*SOURCES, TB, Path(__file__),
               ROOT / 'rtl/music/basic_pitch_ddr_map.svh',
               ROOT / 'rtl/music/basic_pitch_fixed_pkg.svh', *weight_paths]
    before = {str(path.relative_to(ROOT)): sha(path) for path in tracked}
    blob = words(weight_paths[0])
    real = words(weight_paths[1])
    imag = words(weight_paths[2])
    assert len(blob) == 52239 and len(real) == len(imag) == 9216
    assert blob[33807:43023] == real, 'real CQT ROM differs from actual model blob'
    assert blob[43023:52239] == imag, 'imaginary CQT ROM differs from actual model blob'
    assert [len(words(path)) for path in weight_paths[3:]] == [256, 309, 256]
    inputs = dict(input_sha256=before, cqt_real_model_word_offset=33807,
                  cqt_imag_model_word_offset=43023, full_model_words=len(blob),
                  complete_CQT_ROM_words_compared=2 * 9216,
                  actual_model_and_ROM_coefficient_words_identical=True,
                  fixture=dict(WIN_LEN=512, OCTAVES=2, FRAMES=2, PER_OCT=36,
                               KTAPS=256, HOP_NUMERATOR=513, HOP_DENOMINATOR=2),
                  modes=[dict(id=0, signal='DDR', CQT_coefficients='DDR'),
                         dict(id=1, signal='local', CQT_coefficients='DDR'),
                         dict(id=2, signal='local', CQT_coefficients='local')],
                  frontend_instantiated=False, production_sources_modified=False)
    (out / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')

    def run(config):
        negative, name = config
        target = out / name
        target.mkdir()
        binary = target / 'simulation.vvp'
        command = ['iverilog', '-g2012', '-I', str(ROOT / 'rtl/music'),
                   '-s', 'tb_cqt_storage_equivalence',
                   '-Ptb_cqt_storage_equivalence.NEGATIVE=' + str(negative),
                   '-o', str(binary), *(str(path) for path in SOURCES), str(TB)]
        start = time.monotonic()
        compiled = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        (target / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        invocation = dict(compile_argv=command, compile_exit_code=compiled.returncode)
        if compiled.returncode:
            return dict(name=name, negative=negative, passed=False, **invocation)
        sim_command = ['vvp', str(binary), '+TRACE_DIR=' + str(target)]
        simulated = subprocess.run(sim_command, cwd=ROOT, capture_output=True, text=True, timeout=300)
        text = simulated.stdout + simulated.stderr
        log = target / 'simulation.log'
        log.write_text(text)
        mismatch = re.search(r'MISMATCH (magnitude|ordered signal write|internal decimation)', text)
        passed = ((simulated.returncode == 0 and 'PASS CQT cross-storage exact:' in text)
                  if negative == 0 else simulated.returncode != 0 and mismatch is not None)
        result = dict(name=name, negative=negative, passed=passed,
                      expected_destructive_rejection=negative != 0,
                      actual_sequence_mismatch_detected=mismatch is not None,
                      mismatch_message=next((line for line in text.splitlines()
                                             if 'MISMATCH ' in line), None),
                      simulation_argv=sim_command, simulation_exit_code=simulated.returncode,
                      wall_seconds=time.monotonic() - start, log=str(log), log_sha256=sha(log),
                      windows=[fields(line) for line in text.splitlines() if line.startswith('WINDOW ')],
                      engine_run_reset_cancellations=[fields(line) for line in text.splitlines()
                                                       if line.startswith('ENGINE_CANCEL ')],
                      input_sensitivity=[fields(line) for line in text.splitlines()
                                         if line.startswith('INPUT_SENSITIVITY ')],
                      ordered_trace_sha256={str(path.relative_to(out)): sha(path)
                                            for path in sorted(target.glob('*.csv'))}, **invocation)
        print(json.dumps({key: result[key] for key in
                          ('name', 'passed', 'simulation_exit_code', 'wall_seconds', 'mismatch_message')}), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, [(0, 'positive'), (1, 'zero_local_coefficients'),
                                     (2, 'corrupt_DDR_signal_return')]))
    unchanged = before == {name: sha(ROOT / name) for name in before}
    positive = results[0]
    windows = positive.get('windows', [])
    positive_coverage = (len(windows) == 12 and
                         len(positive.get('engine_run_reset_cancellations', [])) == 3 and
                         len(positive.get('input_sensitivity', [])) == 1 and
                         positive['input_sensitivity'][0]['changed_magnitudes'] > 0)
    for label in ('extremes', 'random', 'restart_reads', 'restart_decimation'):
        traces = [out / 'positive' / f'{label}_cfg{mode}.csv' for mode in range(3)]
        positive_coverage &= all(path.is_file() for path in traces)
        if all(path.is_file() for path in traces):
            positive_coverage &= len({path.read_bytes() for path in traces}) == 1
    passed = all(result['passed'] for result in results) and unchanged and positive_coverage
    report = dict(schema=1, passed=passed,
                  scope='same maintained CQT engine across three actual storage configurations',
                  inputs=inputs, inputs_unchanged=unchanged, positive_coverage_complete=positive_coverage,
                  complete_windows=4, engine_configurations=3,
                  magnitudes_compared_per_configuration_per_window=144,
                  ordered_signal_writes_compared_per_configuration_per_window=768,
                  internal_decimation_results_compared_per_configuration_per_window=256,
                  deferred_head_boundary_indices_covered=[127, 128],
                  destructive_sequence_mismatches_required=2,
                  engine_reset_cancel_scope='engine and mock memory queues reset together, followed by full window reload; no task-owner or real-DDR-drain proof',
                  exact_normalized_features_or_CNN_proven=False,
                  full_production_dimension_proven=False, frontend_configuration_proven=False,
                  real_DDR_or_CDC_proven=False, physical_resources_verified=False,
                  hardware_tested=False, deployment_allowed=False, results=results)
    report_path = out / 'verification.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(report=str(report_path), sha256=sha(report_path), passed=passed,
                          inputs_unchanged=unchanged, positive_coverage_complete=positive_coverage)), flush=True)
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
