#!/usr/bin/env python3
"""Rebuild the board-proven 0x4D workstation with only score guidance added."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/build_20261001_222442_709782'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(data, old, new):
    assert data.count(old) == 1, (old, data.count(old))
    return data.replace(old, new)


def main():
    baseline = json.loads((BASE / 'workstation_inputs.json').read_text())
    assert all(sha(BASE / 'Prj1' / path) == digest for path, digest in baseline.items())
    output = ROOT / 'results' / datetime.now().strftime('score_guidance_4d_%Y%m%d_%H%M%S_%f')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))

    for name in ('basic_pitch_cnn_streaming.sv', 'basic_pitch_pcm_pipeline.sv',
                 'basic_pitch_viterbi.sv', 'basic_pitch_workstation_link.sv'):
        shutil.copy2(ROOT / 'rtl/music' / name, stage / 'rtl/music' / name)
    shutil.copy2(ROOT / 'rtl/push2/push2_lights.sv', stage / 'src/push2/push2_lights.sv')
    shutil.copy2(ROOT / 'rtl/push2_usb_a_control.sv', stage / 'src/usb_a/push2_usb_a_control.sv')
    shutil.copy2(ROOT / 'rtl/push2/push2_score_guide.sv', stage / 'src/usb_a/push2_score_guide.sv')

    controls = stage / 'src/push2/push2_controls.sv'
    data = controls.read_text()
    data = replace_once(data, '    input wire [9:0] actual_panic_epoch,',
                        '    input wire [9:0] actual_panic_epoch,\n'
                        '    input wire guide_enabled_i,\n    output reg guide_toggle_o,')
    data = replace_once(data, '            event_valid<=0;event_data<=0;held<=0;buttons<=0;',
                        '            event_valid<=0;event_data<=0;held<=0;buttons<=0;\n'
                        '            guide_toggle_o<=0;')
    data = replace_once(data, '        end else begin\n            was_connected<=connected;',
                        '        end else begin\n            guide_toggle_o<=0;\n'
                        '            was_connected<=connected;')
    data = replace_once(data,
                        '                            if(a>=102 && a<=104) begin event_valid<=1;event_data<={4\'d2,7\'d80,a-7\'d102};mapped<=mapped+1\'b1;end',
                        '                            if(a==85 && guide_enabled_i) begin guide_toggle_o<=1;mapped<=mapped+1\'b1;end\n'
                        '                            else if(a>=102 && a<=104) begin event_valid<=1;event_data<={4\'d2,7\'d80,a-7\'d102};mapped<=mapped+1\'b1;end')
    controls.write_text(data)

    top = stage / 'src/push2/gw138k_push_workstation_top.v'
    data = top.read_text()
    data = replace_once(data,
                        '    wire [33:0] service_state_usb;wire service_state_usb_valid;',
                        '''    wire [33:0] service_state_usb;wire service_state_usb_valid;
    wire music_score_valid,music_score_ready,score_usb_valid,score_usb_ready;
    wire [6:0] music_score_note,score_usb_note;
    music_async_fifo #(.WIDTH(7),.ADDRESS_BITS(2)) u_score_push_cdc(
        .write_clk_i(clk_50m),.write_rst_ni(reset_n),
        .write_valid_i(music_score_valid),.write_ready_o(music_score_ready),
        .write_data_i(music_score_note),
        .read_clk_i(usb_clk),.read_rst_ni(usb_reset_n),
        .read_valid_o(score_usb_valid),.read_ready_i(score_usb_ready),
        .read_data_o(score_usb_note));''')
    data = replace_once(data,
                        '        .service_state_data(service_state_usb),.service_state_valid(service_state_usb_valid),',
                        '        .service_state_data(service_state_usb),.service_state_valid(service_state_usb_valid),\n'
                        '        .score_valid(score_usb_valid),.score_ready(score_usb_ready),.score_note(score_usb_note),')
    data = replace_once(data,
                        '        .result_note(music_result_note),.result_frame(music_result_frame),',
                        '        .result_note(music_result_note),.result_frame(music_result_frame),\n'
                        '        .score_valid(music_score_valid),.score_ready(music_score_ready),.score_note(music_score_note),')
    top.write_text(data)

    project = stage / 'Prj1.gprj'
    tree = ET.parse(project)
    ET.SubElement(tree.find('FileList'), 'File', path='src/usb_a/push2_score_guide.sv',
                  type='file.verilog', enable='1')
    tree.write(project, encoding='utf-8', xml_declaration=True)
    tcl = stage / 'scripts/build.tcl'
    tcl.write_text(replace_once(tcl.read_text(),
                                'set_option -user_code 0000004D',
                                'set_option -user_code 00000052'))

    inputs = {str(path.relative_to(stage)): sha(path)
              for path in stage.rglob('*') if path.is_file()}
    (output / 'workstation_inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    print(output, flush=True)
    with (output / 'gowin.log').open('w') as log:
        result = subprocess.run([str(Path.home() / '.local/bin/gw_sh'), 'scripts/build.tcl'],
                                cwd=stage, env=dict(os.environ, PRJ1_FLOW='all'),
                                stdout=log, stderr=subprocess.STDOUT)
    changed = [path for path, digest in inputs.items() if sha(stage / path) != digest]
    (output / 'tool_result.json').write_text(json.dumps({
        'exit_code': result.returncode, 'inputs_unchanged': not changed,
        'changed': changed, 'baseline': str(BASE), 'hardware_tested': False}, indent=2) + '\n')
    print('Gowin exit', result.returncode, 'changed inputs', changed, flush=True)
    assert result.returncode == 0 and not changed


if __name__ == '__main__':
    main()
