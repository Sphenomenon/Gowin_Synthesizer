#!/usr/bin/env python3
"""0x80: migrate the P10 delay line (delay_stage, 64 BSRAM blocks) to a DDR
ring behind a new arbiter owner 6.

- serial_delay_effect_ddr + delay_ddr_dma replace the BRAM delay storage;
  the 5-state FSM arithmetic is untouched (bit-exact equivalence TB:
  sim/audio/run_delay_ddr_equivalence.py).
- gw138k_ddr_arbiter gains owner 6 (below audio/music-turn, above CPU).
- The delay ring lives at PRJ1_DDR_BULK_POOL byte 0x3000_0000 (128 KiB).
- The frozen stereo_effects.sv is hash-asserted, then patched: module ports
  and the delay_stage instantiation (module swap + FIFO wiring).
"""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full79_20261004_204059'
FROZEN_SHA = '589cd255fb2643c7c7fc010246ecbb532176e4f9540735ed34ab6808fc325657'

# Pass-through port block for the .v/.sv wrappers (wire style).
WRAP_PORTS = """    // P10 delay DDR ring bridge (memory-domain side, see delay_ddr_dma)
    input wire delay_mem_clk_i, delay_mem_rst_ni,
    output wire delay_dwr_valid_o,
    output wire [64:0] delay_dwr_data_o,
    input wire delay_dwr_pop_i,
    input wire delay_drd_push_i,
    input wire [64:0] delay_drd_data_i,
    output wire delay_drd_ready_o"""
WRAP_CONN = ("""      .mem_clk_i(delay_mem_clk_i),.mem_rst_ni(delay_mem_rst_ni),
      .dwr_valid_o(delay_dwr_valid_o),.dwr_data_o(delay_dwr_data_o),.dwr_pop_i(delay_dwr_pop_i),
      .drd_push_i(delay_drd_push_i),.drd_data_i(delay_drd_data_i),.drd_ready_o(delay_drd_ready_o)""")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(data, old, new):
    assert data.count(old) == 1, 'expected exactly one occurrence: ' + old[:80]
    return data.replace(old, new)


def main():
    if '--skip-sim' not in sys.argv:
        print('running equivalence TB gate...', flush=True)
        gate = subprocess.run([sys.executable,
                               str(ROOT / 'sim/audio/run_delay_ddr_equivalence.py')])
        assert gate.returncode == 0, 'equivalence TB gate failed'

    output = ROOT / 'results' / datetime.now().strftime('song_guide_full80_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))

    # Live files that are identical in lineage (verified) or new.
    for live, staged in [
        ('rtl/display_data/gw138k_ddr_arbiter.sv', 'src/ae350/gw138k_ddr_arbiter.sv'),
        ('rtl/display_data/hdmi_display.v', 'src/video/hdmi_display.v'),
        ('rtl/ddr_address_map.vh', 'src/memory/ddr_address_map.vh'),
        ('rtl/audio/delay_ddr/serial_delay_effect_ddr.sv',
         'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv'),
        ('rtl/audio/delay_ddr/delay_ddr_dma.sv',
         'rtl/audio/delay_ddr/delay_ddr_dma.sv'),
    ]:
        dest = stage / staged
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / live, dest)

    # --- frozen stereo_effects.sv: hash, then patch ---
    frozen = stage / 'legacy/rtl/audio/stereo_effects.sv'
    assert sha(frozen) == FROZEN_SHA, 'frozen stereo_effects.sv drifted'
    data = frozen.read_text()
    data = replace_once(data,
        """    output logic ready_o,valid_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o
);
  import audio_math_pkg::*;
  localparam [3:0] IDLE=0,SCALE=1,DRY=2,SELECT=3,SEND=4,WAIT=5,FINISH=6;""",
        """    output logic ready_o,valid_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o,
    // P10 delay DDR ring bridge (memory-domain side, see delay_ddr_dma)
    input logic mem_clk_i,mem_rst_ni,
    output logic dwr_valid_o,
    output logic [64:0] dwr_data_o,
    input logic dwr_pop_i,
    input logic drd_push_i,
    input logic [64:0] drd_data_i,
    output logic drd_ready_o
);
  import audio_math_pkg::*;
  localparam [3:0] IDLE=0,SCALE=1,DRY=2,SELECT=3,SEND=4,WAIT=5,FINISH=6;""")
    data = replace_once(data,
        """  serial_delay_effect #(.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) delay_stage(
      .clk_i,.rst_ni,.clear_i,.valid_i(state==SEND&&work_id==0),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(delay_ready),.valid_o(delay_valid),.active_o(delay_active),.left_o(delay_l),.right_o(delay_r),.clip_o(delay_clip));""",
        """  serial_delay_effect_ddr #(.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) delay_stage(
      .clk_i,.rst_ni,.clear_i,.valid_i(state==SEND&&work_id==0),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(delay_ready),.valid_o(delay_valid),.active_o(delay_active),.left_o(delay_l),.right_o(delay_r),.clip_o(delay_clip),
      .mem_clk_i,.mem_rst_ni,
      .dwr_valid_o,.dwr_data_o,.dwr_pop_i,
      .drd_push_i,.drd_data_i,.drd_ready_o,
      .debug_status_o());""")
    frozen.write_text(data)

    # --- event_workstation: ports + instance wiring ---
    ws = stage / 'src/ae350/gw138k_event_workstation.sv'
    data = ws.read_text()
    data = replace_once(data,
        "    output logic [6:0] panel_command_o\n);",
        "    output logic [6:0] panel_command_o,\n" +
        WRAP_PORTS.replace('input wire', 'input logic').replace(
            'output wire', 'output logic') + ");")
    data = replace_once(data,
        "      .ready_o(fx_ready),.valid_o(sample_valid_o),.left_o(effect_left),.right_o(effect_right),.clip_o(fx_clip));",
        "      .ready_o(fx_ready),.valid_o(sample_valid_o),.left_o(effect_left),.right_o(effect_right),.clip_o(fx_clip),\n"
        + WRAP_CONN + ');')
    ws.write_text(data)

    # --- controlled_adapter: ports + pass-through ---
    ad = stage / 'src/ae350/gw138k_controlled_adapter.sv'
    data = ad.read_text()
    data = replace_once(data,
        """    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o
);""",
        """    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o,
""" + WRAP_PORTS + ");")
    data = replace_once(data,
        "        .clip_o(clip),.synth_gain_o(synth_gain),.pcm_gain_o(pcm_gain),.effect_mask_o(effect_mask),.effect_order_o(effect_order));",
        "        .clip_o(clip),.synth_gain_o(synth_gain),.pcm_gain_o(pcm_gain),.effect_mask_o(effect_mask),.effect_order_o(effect_order),\n"
        "        .delay_mem_clk_i(delay_mem_clk_i),.delay_mem_rst_ni(delay_mem_rst_ni),\n"
        "        .delay_dwr_valid_o(delay_dwr_valid_o),.delay_dwr_data_o(delay_dwr_data_o),.delay_dwr_pop_i(delay_dwr_pop_i),\n"
        "        .delay_drd_push_i(delay_drd_push_i),.delay_drd_data_i(delay_drd_data_i),.delay_drd_ready_o(delay_drd_ready_o));")
    ad.write_text(data)

    # --- usb_controlled_audio: ports + pass-through ---
    ua = stage / 'src/usb_host/gw138k_usb_controlled_audio.sv'
    data = ua.read_text()
    data = replace_once(data,
        """    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o
);""",
        """    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o,
""" + WRAP_PORTS + ");")
    data = replace_once(data,
        "        .display_voices_o(display_voices_o),.display_status_o(display_status_o),.effect_mask_o(effect_mask_audio),.effect_order_o(effect_order_audio));",
        "        .display_voices_o(display_voices_o),.display_status_o(display_status_o),.effect_mask_o(effect_mask_audio),.effect_order_o(effect_order_audio),\n"
        "        .delay_mem_clk_i(delay_mem_clk_i),.delay_mem_rst_ni(delay_mem_rst_ni),\n"
        "        .delay_dwr_valid_o(delay_dwr_valid_o),.delay_dwr_data_o(delay_dwr_data_o),.delay_dwr_pop_i(delay_dwr_pop_i),\n"
        "        .delay_drd_push_i(delay_drd_push_i),.delay_drd_data_i(delay_drd_data_i),.delay_drd_ready_o(delay_drd_ready_o));")
    ua.write_text(data)

    # --- push top: wires + DMA instance + u_managed/u_video wiring ---
    top = stage / 'src/push2/gw138k_push_workstation_top.v'
    data = top.read_text()
    data = replace_once(data,
        "    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;",
        """    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;
    wire delay_ddr_req,delay_ddr_write,delay_ddr_ready,delay_ddr_response;
    wire [28:0] delay_ddr_address;
    wire [255:0] delay_ddr_data;
    wire delay_dwr_valid,delay_dwr_pop,delay_drd_push,delay_drd_ready;
    wire [64:0] delay_dwr_data,delay_drd_data;
    wire [7:0] delay_ddr_debug;
    // P10 delay ring DMA: arbiter owner 6, BULK_POOL first granule (128 KiB).
    delay_ddr_dma #(.DELAY_BITS(14),.ECHO_SAMPLES(9600)) u_delay_ddr_dma(
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .dwr_valid_i(delay_dwr_valid),.dwr_data_i(delay_dwr_data),.dwr_pop_o(delay_dwr_pop),
        .drd_push_o(delay_drd_push),.drd_data_o(delay_drd_data),.drd_ready_i(delay_drd_ready),
        .ddr_req_o(delay_ddr_req),.ddr_write_o(delay_ddr_write),.ddr_address_o(delay_ddr_address),
        .ddr_data_o(delay_ddr_data),.ddr_mask_o(),
        .ddr_ready_i(delay_ddr_ready),.ddr_response_i(delay_ddr_response),.ddr_read_data_i(app_rdata),
        .debug_status_o(delay_ddr_debug));""")
    data = replace_once(data,
        "        .display_voices_o(active_voices),.display_status_o(display_status),.effect_mask_o(effect_mask),.effect_order_o(effect_order));",
        """        .display_voices_o(active_voices),.display_status_o(display_status),.effect_mask_o(effect_mask),.effect_order_o(effect_order),
        .delay_mem_clk_i(memory_clk),.delay_mem_rst_ni(memory_reset_n),
        .delay_dwr_valid_o(delay_dwr_valid),.delay_dwr_data_o(delay_dwr_data),.delay_dwr_pop_i(delay_dwr_pop),
        .delay_drd_push_i(delay_drd_push),.delay_drd_data_i(delay_drd_data),.delay_drd_ready_o(delay_drd_ready));""")
    data = replace_once(data,
        "        .music_ready(music_ddr_ready),.music_response(music_ddr_response),",
        """        .music_ready(music_ddr_ready),.music_response(music_ddr_response),
        .delay_req(delay_ddr_req),.delay_write(delay_ddr_write),.delay_address(delay_ddr_address),
        .delay_data(delay_ddr_data),
        .delay_ready(delay_ddr_ready),.delay_response(delay_ddr_response),""")
    top.write_text(data)

    # --- project file list: after music_async_fifo so the package (legacy
    # audio) and the async FIFO precede the new modules ---
    gprj = stage / 'Prj1.gprj'
    data = gprj.read_text()
    data = replace_once(data,
        '        <File path="rtl/music/music_async_fifo.sv" type="file.verilog" enable="1" />',
        '        <File path="rtl/music/music_async_fifo.sv" type="file.verilog" enable="1" />\n'
        '        <File path="rtl/audio/delay_ddr/serial_delay_effect_ddr.sv" type="file.verilog" enable="1" />\n'
        '        <File path="rtl/audio/delay_ddr/delay_ddr_dma.sv" type="file.verilog" enable="1" />')
    gprj.write_text(data)

    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    assert old.count('set_option -user_code 00000079') == 1
    tcl.write_text(old.replace('set_option -user_code 00000079',
                               'set_option -user_code 00000080'))

    inputs = {str(path.relative_to(stage)): sha(path)
              for path in stage.rglob('*') if path.is_file()}
    (output / 'workstation_inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    print(output, flush=True)
    if '--dry-run' in sys.argv:
        print('dry run: patches applied, synthesis skipped', flush=True)
        return
    with (output / 'gowin.log').open('w') as log:
        result = subprocess.run([str(Path.home() / '.local/bin/gw_sh'), 'scripts/build.tcl'],
                                cwd=stage, env=dict(os.environ, PRJ1_FLOW='all'),
                                stdout=log, stderr=subprocess.STDOUT)
    changed = [path for path, digest in inputs.items() if sha(stage / path) != digest]
    (output / 'tool_result.json').write_text(json.dumps({
        'exit_code': result.returncode, 'inputs_unchanged': not changed,
        'changed': changed, 'baseline': str(BASE), 'hardware_tested': False}, indent=2) + '\n')
    print('Gowin exit', result.returncode, 'changed inputs', changed, flush=True)
    if result.returncode or changed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
