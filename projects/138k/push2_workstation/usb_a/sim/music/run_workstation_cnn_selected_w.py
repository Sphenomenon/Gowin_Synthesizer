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
DIMENSIONS = dict(WIN_LEN=44100, FRAME_LIMIT=8, OCTAVE_LIMIT=9,
                  CQT_HOP_NUMERATOR=22050, CQT_HOP_DENOMINATOR=4,
                  FEATURE_TILE_COLS=16, COARSE_GUIDANCE=1)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_prepared(prepared):
    manifest = prepared / 'workstation_profile.json'
    receipt = json.loads(manifest.read_text())
    if receipt['profile'] != PROFILE or receipt['configuration']['demo_role'] != 'W':
        raise ValueError('only the explicit W media role is supported')
    stage = prepared / 'workstation/Prj1'
    for field in ('staged_input_sha256', 'enabled_inputs'):
        for name, entry in receipt[field].items():
            expected = entry if isinstance(entry, str) else entry['sha256']
            if sha(stage / name) != expected:
                raise ValueError(f'{field} input drift: {name}')
    return stage, receipt, manifest


def run(prepared, out):
    stage, receipt, manifest = verify_prepared(prepared)
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
    result = dict(schema=1, passed=False, stage='selected_W4Hz_actual_task_component',
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
                '-GREQUIRE_SELECTED_W=1', *map(str, sources)]
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
        task_metrics = [dict(re.findall(r'(\w+)=([0-9a-f]+)', line))
                        for line in lines if line.startswith('TASK_METRICS ')]
        result.update(run_exit=code, run_log_sha256=sha(out / 'run.log'),
                      task_metrics=task_metrics, log=log_text,
                      elapsed_seconds=round(time.monotonic() - begun, 3))
        if code or 'PASS actual_W_CNN_task' not in log_text or len(task_metrics) != 2:
            raise RuntimeError('selected W task verification failed: ' + str(out / 'run.log'))
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
    args = parser.parse_args()
    run(args.prepared.resolve(), args.output.resolve())
