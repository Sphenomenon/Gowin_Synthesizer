#!/usr/bin/env python3
"""Actual SPI real-model boot, bounded DDR task staging and real CNN cancellation."""
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
SRC = ROOT / 'rtl/music'
sys.path.insert(0, str(ROOT))
from tools.build_cnn_flash_image import build_image, load_words


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    header = out / 'include/src/memory/ddr_address_map.vh'
    header.parent.mkdir(parents=True)
    header.write_bytes((ROOT / 'rtl/ddr_address_map.vh').read_bytes())
    link = SRC / 'basic_pitch_workstation_link.sv'
    anchor = '.WIN_LEN(43844),.FRAME_LIMIT(172),.OCTAVE_LIMIT(9)'
    text = link.read_text()
    if text.count(anchor) != 1:
        raise ValueError('production link dimension anchor drift')
    copy = out / link.name
    copy.write_text(text.replace(anchor, '.WIN_LEN(2048),.FRAME_LIMIT(2),.OCTAVE_LIMIT(9)'))
    image, manifest = build_image(load_words(SRC / 'weights/cnn_ddr_blob.mem'))
    if manifest['payload_crc32'] != 'AF01A61B' or manifest['word_count'] != 52239:
        raise ValueError('actual model identity changed')
    image_path = out / 'real_model_spi.hex'
    image_path.write_text('\n'.join(f'{byte:02x}' for byte in image) + '\n')
    sources = [SRC / 'basic_pitch_nn_ddr.sv']
    sources += [SRC / name for name in MUSIC_SOURCES if name != 'basic_pitch_nn_ddr.sv']
    sources += [copy]
    sources += [SRC / name for name in ['basic_pitch_link_uart.sv', 'basic_pitch_ddr16_port.sv',
                'basic_pitch_ddr_command_buffer.sv', 'music_async_fifo.sv',
                'workstation_cnn_ddr_broker.sv', 'workstation_cnn_task_service.sv']]
    sources += [ROOT / 'rtl/memory' / name for name in ['workstation_sdp.sv', 'workstation_ddr_bist.v',
                'workstation_recording_ddr_client_queues.sv', 'workstation_recording_ddr_arbiter_pipeline.sv',
                'workstation_media_memory.sv']]
    sources += [SRC / 'basic_pitch_ddr_client_queues.sv', SRC / 'basic_pitch_ddr_arbiter_pipeline.sv',
                ROOT.parent / 'touchboard_test/rtl/uart_tx.v', ROOT / 'sim/music/tb_workstation_cnn_task.sv']
    inputs = [*sources, link, ROOT / 'rtl/ddr_address_map.vh', ROOT / 'rtl/ddr_address_map_guard.v',
              SRC / 'weights/cnn_ddr_blob.mem', Path(__file__).resolve()]
    hashes = {str(p): sha(p) for p in inputs}
    result = dict(schema=1, passed=False, stage='unselected_actual_w_cnn_task_component',
                  source_sha256=hashes, production_link_sha256=sha(link), simulation_link_sha256=sha(copy),
                  simulation_dimensions=dict(WIN_LEN=2048, FRAME_LIMIT=2, input_clip_frames=4096),
                  production_dimensions=dict(WIN_LEN=43844, FRAME_LIMIT=172, capacity_frames=96000),
                  simulation_overlay='one exact dimension anchor in a copy; model/loader unchanged',
                  model_loader='actual full real-model read-only SPI BPF1 payload CRC and actual DDR readback CRC; no model preload or forced loader DONE',
                  model_manifest=manifest, model_image_sha256=hashlib.sha256(image).hexdigest(),
                  native_memory='actual media BIST/owner5 broker/owner6/owner8 queues with independent native stalls and delayed reads; behavioral DDR',
                  production_profile_selected=False, bitstream_identity=None, hardware_tested=False,
                  sram_programmed=False, flash_written=False)
    begun = time.monotonic()
    try:
        argv = ['verilator', '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
                '--top-module', 'tb_workstation_cnn_task', '--Mdir', str(out / 'obj'),
                '-I' + str(out / 'include'), '-I' + str(ROOT), '-I' + str(SRC), *map(str, sources)]
        result['build_argv'] = argv
        with (out / 'build.log').open('w') as log:
            built = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        result['build_exit'] = built.returncode
        result['build_log_sha256'] = sha(out / 'build.log')
        if built.returncode:
            raise RuntimeError('build failed: ' + str(out / 'build.log'))
        print('built actual W CNN task + full real SPI loader + media memory', flush=True)
        run_argv = [str(out / 'obj/Vtb_workstation_cnn_task'), '+IMAGE=' + str(image_path)]
        result['run_argv'] = run_argv
        with (out / 'run.log').open('w') as log:
            with subprocess.Popen(run_argv, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
                lines = []
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    lines.append(line)
                    print(line, end='', flush=True)
                code = process.wait()
        log_text = ''.join(lines)
        result.update(run_exit=code, run_log_sha256=sha(out / 'run.log'), log=log_text,
                      metrics={k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', log_text)},
                      elapsed_seconds=round(time.monotonic() - begun, 3))
        if code or 'PASS actual_W_CNN_task' not in log_text:
            raise RuntimeError('actual task simulation failed: ' + str(out / 'run.log'))
        result['source_unchanged_during_run'] = hashes == {str(p): sha(p) for p in inputs}
        if not result['source_unchanged_during_run']:
            raise ValueError('source drift during task verification')
        result['passed'] = True
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
