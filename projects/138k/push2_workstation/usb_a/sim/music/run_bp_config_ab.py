#!/usr/bin/env python3
"""Dual-config A/B equivalence sim for the 0x82 staged-cache fix.

iverilog is single-pass and cannot bind the live pipeline's
declaration-after-use style, so this runner emits a sim-only copy of
basic_pitch_pcm_pipeline.sv with pure declaration statements hoisted above
their first use.  The real RTL is never modified.  Config A (USE_ALL_DDR,
the 0x80/0x81 baseline datapath) and config B (the 0x82 staged-cache datapath)
run the same PCM through one behavioural DDR preloaded with the model blob;
per-frame layer hashes and score notes must match bit-exactly.
"""
from pathlib import Path
import argparse
import hashlib
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]          # usb_a/
HERE = Path(__file__).resolve().parent
GEN = HERE / 'gen'
SRC = ROOT / 'rtl/music'

MUSIC_SOURCES = [
    'basic_pitch_pcm_pipeline.sv', 'basic_pitch_nn_ddr.sv',
    'basic_pitch_uart_model_loader.sv', 'basic_pitch_uart_rx.sv',
    'basic_pitch_model_loader.sv', 'basic_pitch_weight_cache.sv',
    'basic_pitch_boot_model_loader.sv', 'basic_pitch_flash_model_loader.sv',
    'basic_pitch_feature_ddr.sv', 'basic_pitch_plane_cache.sv',
    'basic_pitch_normlog_ddr.sv', 'basic_pitch_normlog.sv',
    'basic_pitch_ddr_coeff_pair.sv', 'basic_pitch_cqt_engine.sv',
    'basic_pitch_cqt_frontend.sv', 'basic_pitch_conv2d.sv',
    'basic_pitch_activation.sv', 'basic_pitch_requant.sv',
    'basic_pitch_row_buffer.sv', 'basic_pitch_cnn_streaming.sv',
    'basic_pitch_viterbi.sv', 'basic_pitch_shared_sigmoid.sv',
    'basic_pitch_44100_to_48000.sv',
]

# Pure declaration lines the single-pass compiler must see before use.
HOIST_ANCHORS = [
    '    logic model_done, model_mem_req, model_mem_write, model_mem_ready;',
    '    logic weight_cache_done, weight_cache_busy;',
    '    logic weight_mem_req, weight_mem_ready, weight_mem_rsp_valid;',
    '    logic [31:0] weight_mem_addr;',
    '    logic [15:0] weight_mem_wdata;',
    '    logic [14:0] weight_blob_base;',
    '    logic [13:0] weight_word_count;',
    '    logic [17:0] weight_cache_read_addr;',
    '    logic signed [15:0] weight_cache_read_data;',
    '    logic [5:0] nn_sample_req, nn_input_range, nn_bias_req;',
    '    logic nn_sample_valid, nn_bias_valid, nn_idle, nn_overflow;',
    '    logic signed [15:0] nn_sample_x, nn_sample_w;',
    '    logic signed [31:0] nn_bias;',
    '    logic [2:0] nn_layer, nn_write_layer;',
    '    logic [15:0] nn_plane_addr;',
    '    logic [23:0] nn_x_addr, nn_x_cell_addr;',
    '    logic [7:0] nn_x_channel;',
    '    logic [17:0] nn_weight_addr;',
    '    logic [8:0] nn_bias_addr, nn_write_row, nn_write_col, nn_write_channel;',
    '    logic nn_write_valid, nn_feed_valid;',
    '    logic [15:0] nn_write_data, nn_feed_note, nn_feed_onset;',
    '    logic nn_mem_req, nn_mem_write, nn_mem_ready, nn_mem_rsp_valid;',
    '    logic model_mem_rsp_valid;',
    '    logic read_outstanding;',
    '    logic [3:0] request_owner, response_owner;',
]

HOIST_BEFORE = '    wire run_rst_ni = rst_ni && !analysis_restart_i;'


def hoist_declarations(text, names):
    """Move the declarations of `names` above first use.  A declaration is
    matched as a whole statement (from a module-level logic/wire/reg keyword
    to its terminating semicolon, spanning newlines) and moved intact."""
    moved = []
    for name in names:
        stmt_re = re.compile(
            r'^[ \t]*(?:logic|wire|reg)\b[^;]*?\b' + re.escape(name) +
            r'\b[^;]*;', re.M)
        found = stmt_re.findall(text)
        if not found:
            continue
        stmt = found[0]
        if stmt in moved:
            continue
        assert text.count(stmt) == 1, f'ambiguous declaration: {stmt!r}'
        text = text.replace(stmt, '', 1)
        moved.append(stmt)
    if moved:
        assert text.count(HOIST_BEFORE) == 1
        text = text.replace(HOIST_BEFORE,
                            HOIST_BEFORE + '\n' + ''.join(moved) + '\n')
    return text, moved


def compile_tb(sim_copy, sources, exe):
    return subprocess.run(
        ['iverilog', '-g2012', '-s', 'tb_bp_config_ab', '-o', str(exe),
         '-I', str(SRC)] + sources, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', choices=('auto', 'iverilog', 'verilator'), default='auto')
    parser.add_argument('--frames', type=int, default=3)
    parser.add_argument('--win-len', type=int, default=2048)
    parser.add_argument('--ddr-latency', type=int, default=1)
    parser.add_argument('--max-cycles', type=int, default=400000000)
    args = parser.parse_args()
    simulator = args.simulator
    if simulator == 'auto':
        simulator = 'verilator' if shutil.which('verilator') else 'iverilog'
    assert args.frames > 1 and args.win_len > 0 and args.ddr_latency > 0
    GEN.mkdir(exist_ok=True)
    params = {'FRAMES': args.frames, 'WIN_LEN': args.win_len,
              'DDR_READ_CYCLES': args.ddr_latency, 'MAX_CYCLES': args.max_cycles}
    print(f'backend={simulator} parameters={params}', flush=True)
    text = (SRC / 'basic_pitch_pcm_pipeline.sv').read_text()
    sources = None
    for round_no in range(8):
        sim_copy = GEN / 'basic_pitch_pcm_pipeline.sv'
        sim_copy.write_text(text)
        others = [str(SRC / s) for s in MUSIC_SOURCES
                  if s not in ('basic_pitch_pcm_pipeline.sv',
                               'basic_pitch_nn_ddr.sv')]
        # nn_ddr first: its include defines the BP_DDR_* macros the pipeline
        # copy references (single compilation unit, Gowin order preserved).
        sources = [str(SRC / 'basic_pitch_nn_ddr.sv'), str(sim_copy)] + others
        sources.append(str(ROOT / 'rtl/memory/workstation_sdp.sv'))
        sources.append(str(HERE / 'tb_bp_config_ab.sv'))
        result = compile_tb(sim_copy, sources, GEN / 'tb_bp_config_ab.vvp')
        if result.returncode == 0:
            break
        names = re.findall(r"Unable to bind wire/reg/memory `(\w+)'",
                           result.stdout + result.stderr)
        names = [n for n in dict.fromkeys(names)]
        if not names:
            print(result.stdout)
            print(result.stderr)
            raise SystemExit('iverilog elaboration failed (non-bind errors)')
        text, moved = hoist_declarations(text, names)
        if not moved:
            print(result.stdout)
            print(result.stderr)
            raise SystemExit(f'cannot hoist declarations for: {names}')
    else:
        raise SystemExit('declaration hoisting did not converge')
    if simulator == 'verilator':
        build_log = GEN / 'verilator_build.log'
        cmd = ['verilator', '--binary', '--timing', '--build-jobs', '4',
               '-Wno-fatal', '--top-module', 'tb_bp_config_ab',
               '--Mdir', str(GEN / 'obj_dir'), '-I' + str(SRC)]
        cmd += [f'-G{name}={value}' for name, value in params.items()]
        cmd += sources
        with build_log.open('w') as log:
            result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            print(build_log.read_text()[-12000:])
            raise SystemExit('Verilator build failed')
        run_cmd = [str(GEN / 'obj_dir' / 'Vtb_bp_config_ab')]
    else:
        exe = GEN / 'tb_bp_config_ab.vvp'
        cmd = ['iverilog', '-g2012', '-s', 'tb_bp_config_ab', '-o', str(exe),
               '-I', str(SRC)]
        cmd += [f'-Ptb_bp_config_ab.{name}={value}' for name, value in params.items()]
        result = subprocess.run(cmd + sources, capture_output=True, text=True)
        (GEN / 'iverilog_build.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            print(result.stdout + result.stderr)
            raise SystemExit('iverilog elaboration failed')
        run_cmd = ['vvp', str(exe)]
    metadata = {
        'backend': simulator, 'parameters': params,
        'sources': {str(Path(path).relative_to(ROOT)):
                    hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in sources},
        'model_sha256': hashlib.sha256((SRC / 'weights/cnn_ddr_blob.mem').read_bytes()).hexdigest(),
    }
    import json
    (GEN / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    # Stream and persist stdout so heartbeats survive a host timeout.
    passed = False
    with (GEN / 'run.log').open('w') as log:
        with subprocess.Popen(run_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, cwd=ROOT) as run:
            for line in run.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
                passed |= 'PASS dual-config equivalence' in line
            result_code = run.wait()
    if result_code or not passed:
        raise SystemExit(f'equivalence failed (exit={result_code}); see {GEN / "run.log"}')


if __name__ == '__main__':
    main()
