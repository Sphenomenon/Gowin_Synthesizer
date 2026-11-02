#!/usr/bin/env python3
"""Run real bounded CNN tasks with an immutable prepared W media configuration.

No dimension overlay or RTL copy is used. This is component verification of
selected inputs, not full-top simulation, routed timing or recognition quality.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from run_bp_config_ab import MUSIC_SOURCES

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.build_cnn_flash_image import build_image, load_words

PROFILE = 'custom138k-workstation-task3-w-media-v1'
STORAGE_PROFILES = {
    PROFILE: ('task3_w_ddr_cnn_memory_v1', 1, 1, 'rtl/workstation/workstation_profile_task3_w_media.sv'),
    'custom138k-workstation-task3-w-media-signal-bsram-v1':
        ('task3_w_signal_bsram_v1', 0, 1, 'rtl/workstation/workstation_profile_task3_w_media_signal_bsram.sv'),
    'custom138k-workstation-task3-w-media-cqt-bsram-v1':
        ('task3_w_signal_cqt_bsram_v1', 0, 0, 'rtl/workstation/workstation_profile_task3_w_media_cqt_bsram.sv'),
}
DIMENSIONS = dict(WIN_LEN=44100, FRAME_LIMIT=8, OCTAVE_LIMIT=9,
                  CQT_HOP_NUMERATOR=22050, CQT_HOP_DENOMINATOR=4,
                  FEATURE_TILE_COLS=16, COARSE_GUIDANCE=1)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_prepared(prepared):
    manifest = prepared / 'workstation_profile.json'
    receipt = json.loads(manifest.read_text())
    if receipt['profile'] not in STORAGE_PROFILES or receipt['configuration']['demo_role'] != 'W':
        raise ValueError('only the explicit W media role is supported')
    policy, signal, coeff, provider = STORAGE_PROFILES[receipt['profile']]
    actual_policy = receipt['configuration'].get('cnn_memory_policy', 'task3_w_ddr_cnn_memory_v1')
    if actual_policy != policy:
        raise ValueError('W CNN memory configuration differs from explicit profile')
    if receipt['profile'] != PROFILE:
        expected = dict(policy=policy, USE_DDR_SIGNAL=signal, USE_DDR_CQT_COEFF=coeff,
                        USE_DDR_FRONT_COEFF=1, USE_ALL_DDR=0, provider=provider)
        if receipt['classic_runtime']['worker_media_source'].get('selected_CNN_memory') != expected:
            raise ValueError('actual prepared W board storage binding changed')
        if provider not in receipt['enabled_inputs']:
            raise ValueError('expected W storage provider is not compiled')
    stage = prepared / 'workstation/Prj1'
    for field in ('staged_input_sha256', 'enabled_inputs'):
        for name, entry in receipt[field].items():
            expected = entry if isinstance(entry, str) else entry['sha256']
            if sha(stage / name) != expected:
                raise ValueError(f'{field} input drift: {name}')
    return stage, receipt, manifest


def parse_results(lines):
    def records(prefix):
        return [dict(re.findall(r'(\w+)=([0-9a-f]+)', line))
                for line in lines if line.startswith(prefix + ' ')]
    metrics, traffic, scores = records('TASK_METRICS'), records('TASK_TRAFFIC'), records('SCORE')
    if len(metrics) != 2 or [row['task'] for row in metrics] != ['5', '7']:
        raise ValueError('two complete fresh/post-cancel task metrics are required')
    if len(traffic) != 2 or [row['task'] for row in traffic] != ['5', '7']:
        raise ValueError('per-task accepted DDR traffic measurements are missing')
    for row in metrics:
        sequence = [s for s in scores if s['task'] == row['task']]
        if [int(s['index']) for s in sequence] != list(range(int(row['notes']))) or not sequence:
            raise ValueError('complete ordered score evidence is missing')
        row['ordered_notes'] = [int(s['note']) for s in sequence]
        counts = [int(row['writes' + str(i)]) for i in range(6)]
        if counts != [16896, 2112, 22528, 704, 22528, 704]:
            raise ValueError('actual selected eight-frame six-layer write count changed')
    if metrics[0]['ordered_notes'] != metrics[1]['ordered_notes']:
        raise ValueError('fresh/post-cancel complete score differs')
    return metrics, traffic


def validate_complete_results(result):
    if result.get('schema') != 2:
        raise ValueError('complete schema2 task evidence is required')
    metrics, traffic = result.get('task_metrics'), result.get('task_traffic')
    for rows in (metrics, traffic):
        if not isinstance(rows, list) or len(rows) != 2 or [row.get('task') for row in rows] != ['5', '7']:
            raise ValueError('complete ordered fresh/post-cancel evidence is required')
    numeric = ('clip_frames', 'launch_clock', 'first_score_clock', 'complete_clock', 'task_cycles', 'notes')
    traffic_fields = ('cnn_ddr16_reads', 'cnn_ddr16_writes', 'owner5_native_reads',
                      'owner5_native_writes', 'staging_native_reads', 'staging_native_writes')
    for row, counts in zip(metrics, traffic):
        for key in (*numeric, *('writes' + str(i) for i in range(6))):
            if not isinstance(row.get(key), str) or not row[key].isdigit():
                raise ValueError('incomplete numeric task metric: ' + key)
        for key in traffic_fields:
            if not isinstance(counts.get(key), str) or not counts[key].isdigit():
                raise ValueError('incomplete accepted traffic metric: ' + key)
        notes = row.get('ordered_notes')
        if (not isinstance(notes, list) or not notes or len(notes) != int(row['notes']) or
                any(type(note) is not int or not 0 <= note <= 127 for note in notes)):
            raise ValueError('complete ordered MIDI score is required')
        if not isinstance(row.get('hashes'), str) or not re.fullmatch('[0-9a-f]{48}', row['hashes']):
            raise ValueError('complete six-layer hash is required')
        if int(row['clip_frames']) != 96000 or [int(row['writes' + str(i)]) for i in range(6)] != [16896, 2112, 22528, 704, 22528, 704]:
            raise ValueError('selected clip or six-layer dimensions changed')
        launch, first, complete, cycles = (int(row[k]) for k in ('launch_clock', 'first_score_clock', 'complete_clock', 'task_cycles'))
        if not launch < first <= complete or complete - launch != cycles:
            raise ValueError('inconsistent task completion clocks')
        if (int(counts['staging_native_reads']) != 24000 or int(counts['staging_native_writes']) != 12000 or
                int(counts['owner5_native_reads']) != int(counts['cnn_ddr16_reads']) + int(counts['staging_native_reads']) or
                int(counts['owner5_native_writes']) != int(counts['cnn_ddr16_writes']) + int(counts['staging_native_writes'])):
            raise ValueError('source/native/staging acceptance accounting differs')
    parsed_metrics, parsed_traffic = parse_results(result['log'].splitlines())
    if metrics != parsed_metrics or traffic != parsed_traffic:
        raise ValueError('task evidence differs from its actual run log')
    if hashlib.sha256(result['log'].encode()).hexdigest() != result['run_log_sha256']:
        raise ValueError('actual task log hash differs')


def compare_reference(result, path):
    reference = json.loads(path.read_text())
    validate_complete_results(result)
    validate_complete_results(reference)
    if not reference.get('passed') or not reference.get('source_unchanged_during_run'):
        raise ValueError('reference has not passed unchanged-source validation')
    if sha(path.parent / 'run.log') != reference['run_log_sha256']:
        raise ValueError('reference run log bytes changed')
    if reference['selected_dimensions'] != DIMENSIONS or reference['model_image_sha256'] != result['model_image_sha256']:
        raise ValueError('reference changes model or inference dimensions')
    if reference['source_sha256'][str(ROOT / 'sim/music/tb_workstation_cnn_task.sv')] != result['source_sha256'][str(ROOT / 'sim/music/tb_workstation_cnn_task.sv')]:
        raise ValueError('cross-configuration reference must use identical instrumented task fixture')
    comparisons = []
    for actual, old, traffic, old_traffic in zip(result['task_metrics'], reference['task_metrics'],
                                               result['task_traffic'], reference['task_traffic']):
        equal_keys = ['task', 'clip_frames', 'hashes', 'notes', 'ordered_notes'] + ['writes' + str(i) for i in range(6)]
        if any(actual[k] != old[k] for k in equal_keys):
            raise ValueError('cross-configuration layer or complete score mismatch')
        if int(traffic['cnn_ddr16_reads']) >= int(old_traffic['cnn_ddr16_reads']):
            raise ValueError('selected local storage did not reduce accepted CNN DDR16 reads')
        comparisons.append(dict(task=actual['task'], full_six_layer_hashes_equal=True,
            full_ordered_notes_equal=True, all_six_layer_write_counts_equal=True,
            task_cycle_delta=int(actual['task_cycles']) - int(old['task_cycles']),
            accepted_DDR16_read_delta=int(traffic['cnn_ddr16_reads']) - int(old_traffic['cnn_ddr16_reads']),
            accepted_DDR16_write_delta=int(traffic['cnn_ddr16_writes']) - int(old_traffic['cnn_ddr16_writes'])))
    return dict(path=str(path), sha256=sha(path), candidate_identity=reference['candidate_identity'],
                comparisons=comparisons, passed=True)


def run(prepared, out, references=()):
    stage, receipt, manifest = verify_prepared(prepared)
    policy, signal, coeff, _provider = STORAGE_PROFILES[receipt['profile']]
    if receipt['profile'] != PROFILE and not references:
        raise ValueError('local-storage candidates require a complete task reference')
    out.mkdir(parents=True, exist_ok=False)
    src = stage / 'rtl/music'
    link = src / 'basic_pitch_workstation_link.sv'
    selected = '.WIN_LEN(44100),.FRAME_LIMIT(8),.OCTAVE_LIMIT(9),\n        .CQT_HOP_NUMERATOR(22050),.CQT_HOP_DENOMINATOR(4),\n        .FEATURE_TILE_COLS(16),.COARSE_GUIDANCE(1\'b1),'
    if link.read_text().count(selected) != 1:
        raise ValueError('selected W dimension identity drift')
    image, model = build_image(load_words(src / 'weights/cnn_ddr_blob.mem'))
    if model['payload_crc32'] != 'AF01A61B' or model['word_count'] != 52239:
        raise ValueError('real model identity changed')
    image_path = out / 'real_model_spi.hex'
    image_path.write_text('\n'.join(f'{byte:02x}' for byte in image) + '\n')
    sources = [src / 'basic_pitch_nn_ddr.sv']
    sources += [src / name for name in MUSIC_SOURCES if name != 'basic_pitch_nn_ddr.sv']
    sources += [link]
    sources += [src / name for name in (
        'basic_pitch_link_uart.sv', 'basic_pitch_ddr16_port.sv',
        'basic_pitch_ddr_command_buffer.sv', 'music_async_fifo.sv',
        'workstation_cnn_ddr_broker.sv', 'workstation_cnn_task_service.sv')]
    sources += [stage / 'rtl/memory' / name for name in (
        'workstation_sdp.sv', 'workstation_ddr_bist.v',
        'workstation_recording_ddr_client_queues.sv',
        'workstation_recording_ddr_arbiter_pipeline.sv', 'workstation_media_memory.sv')]
    sources += [src / 'basic_pitch_ddr_client_queues.sv',
                src / 'basic_pitch_ddr_arbiter_pipeline.sv', stage / 'src/control/uart_tx.v',
                stage / 'rtl/timing/gw138k_level_cdc.sv']
    tb = ROOT / 'sim/music/tb_workstation_cnn_task.sv'
    for path in sources:
        name = str(path.relative_to(stage))
        # Some support implementations are included by a selected parent, but
        # every byte must still belong to the prepared inventory.
        if name not in receipt['staged_input_sha256']:
            raise ValueError('simulation support input is not staged: ' + name)
    sources.append(tb)
    inputs = {str(p): sha(p) for p in [*sources, manifest, Path(__file__).resolve(),
                                      ROOT / 'tools/build_cnn_flash_image.py',
                                      ROOT / 'sim/music/run_bp_config_ab.py']}
    result = dict(schema=2, passed=False, stage='selected_W4Hz_actual_task_component',
                  profile=receipt['profile'], selected_memory_policy=policy,
                  selected_memory=dict(USE_DDR_SIGNAL=signal, USE_DDR_CQT_COEFF=coeff,
                                       USE_DDR_FRONT_COEFF=1, USE_ALL_DDR=0),
                  candidate_identity=receipt['candidate_identity'],
                  candidate_input_sha256=receipt['candidate_input_sha256'],
                  prepared_manifest=str(manifest), prepared_manifest_sha256=sha(manifest),
                  staged_input_count=len(receipt['staged_input_sha256']),
                  enabled_input_count=len(receipt['enabled_inputs']),
                  source_sha256=inputs, selected_dimensions=DIMENSIONS,
                  input_clip_frames=96000, input_format='48kHz stereo16 deterministic LFSR',
                  rtl_overlays=[], model_manifest=model,
                  model_image_sha256=hashlib.sha256(image).hexdigest(),
                  model_loader='full BPF1 SPI read, payload CRC and native DDR readback CRC; no preload or forced DONE',
                  native_memory='actual BIST/owner5 broker/owner6+8 competing write probes; behavioral DDR with independent command/write stalls and delayed reads',
                  scope='selected CNN task/media-memory inputs; full W top, CPU, real Delay/recording concurrency, physical link and accuracy are not covered',
                  production_profile_selected=True, bitstream_identity=None,
                  hardware_tested=False, sram_programmed=False, flash_written=False)
    begun = time.monotonic()
    try:
        argv = ['verilator', '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
                '--top-module', 'tb_workstation_cnn_task', '--Mdir', str(out / 'obj'),
                '-I' + str(stage), '-I' + str(src),
                '-GCLIP_FRAMES=96000', '-GMAX_CYCLES=1000000000',
                '-GIO_TIMEOUT_CYCLES=50000000', "-GTASK_TIMEOUT_CYCLES=32'd3600000000",
                '-GREQUIRE_SELECTED_W=1', '-GCNN_USE_DDR_SIGNAL=' + str(signal),
                '-GCNN_USE_DDR_CQT_COEFF=' + str(coeff)]
        if receipt['profile'] != PROFILE:
            argv += ['-DTB_CONFIGURABLE_CNN_STORAGE']
        argv += list(map(str, sources))
        result['build_argv'] = argv
        with (out / 'build.log').open('w') as log:
            built = subprocess.run(argv, cwd=stage, stdout=log, stderr=subprocess.STDOUT)
        result['build_exit'] = built.returncode
        result['build_log_sha256'] = sha(out / 'build.log')
        if built.returncode:
            raise RuntimeError('build failed: ' + str(out / 'build.log'))
        print('built unmodified selected W4Hz CNN task + 96000-frame PCM pool', flush=True)
        argv = [str(out / 'obj/Vtb_workstation_cnn_task'), '+IMAGE=' + str(image_path)]
        result['run_argv'] = argv
        lines = []
        with (out / 'run.log').open('w') as log:
            with subprocess.Popen(argv, cwd=stage, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT) as process:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    lines.append(line)
                    print(line, end='', flush=True)
                code = process.wait()
        log_text = ''.join(lines)
        result.update(run_exit=code, run_log_sha256=sha(out / 'run.log'),
                      log=log_text,
                      elapsed_seconds=round(time.monotonic() - begun, 3))
        if code or 'PASS actual_W_CNN_task' not in log_text:
            raise RuntimeError('selected W task verification failed: ' + str(out / 'run.log'))
        result['task_metrics'], result['task_traffic'] = parse_results(lines)
        validate_complete_results(result)
        result['cross_configuration_references'] = [compare_reference(result, p) for p in references]
        verify_prepared(prepared)
        result['source_unchanged_during_run'] = inputs == {p: sha(p) for p in inputs}
        if not result['source_unchanged_during_run']:
            raise ValueError('verification source drift during run')
        result['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path, action='append', default=[],
                        help='completed schema2 task evidence for exact cross-configuration comparison')
    args = parser.parse_args()
    run(args.prepared.resolve(), args.output.resolve(), [p.resolve() for p in args.reference])
