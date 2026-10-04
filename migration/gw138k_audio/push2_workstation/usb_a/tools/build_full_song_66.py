#!/usr/bin/env python3
"""Add registered TF DDR command boundary to the full-song 0x65 build."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full65_20261003_223352'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(data, old, new):
    if data.count(old) != 1:
        raise ValueError(f'expected one occurrence of {old!r}, got {data.count(old)}')
    return data.replace(old, new)


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full66_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    shutil.copy2(ROOT / 'rtl/display_data/tf_audio_ddr_command_buffer.sv',
                 stage / 'src/memory/tf_audio_ddr_command_buffer.sv')
    top = stage / 'src/push2/gw138k_push_workstation_top.v'
    data = top.read_text()
    data = replace_once(data,
                        '    wire audio_ddr_req,audio_ddr_write,audio_ddr_ready,audio_ddr_response;',
                        '    wire audio_ddr_req,audio_ddr_write,audio_ddr_ready,audio_ddr_response;\n'
                        '    wire audio_queued_req,audio_queued_write,audio_queued_ready;\n'
                        '    wire [28:0] audio_queued_address;\n'
                        '    wire [255:0] audio_queued_data;')
    data = replace_once(data,
                        '    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;',
                        '    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;\n'
                        '    tf_audio_ddr_command_buffer u_audio_command_buffer(\n'
                        '        .clk(memory_clk),.rst_n(memory_reset_n),\n'
                        '        .in_valid(audio_ddr_req),.in_write(audio_ddr_write),\n'
                        '        .in_address(audio_ddr_address),.in_data(audio_ddr_data),\n'
                        '        .in_ready(audio_ddr_ready),.out_valid(audio_queued_req),\n'
                        '        .out_write(audio_queued_write),.out_address(audio_queued_address),\n'
                        '        .out_data(audio_queued_data),.out_ready(audio_queued_ready));')
    data = replace_once(data,
                        '.audio_req(audio_ddr_req),.audio_write(audio_ddr_write),.audio_address(audio_ddr_address),\n'
                        '        .audio_data(audio_ddr_data),.audio_ready(audio_ddr_ready),.audio_response(audio_ddr_response),',
                        '.audio_req(audio_queued_req),.audio_write(audio_queued_write),.audio_address(audio_queued_address),\n'
                        '        .audio_data(audio_queued_data),.audio_ready(audio_queued_ready),.audio_response(audio_ddr_response),')
    top.write_text(data)
    project = stage / 'Prj1.gprj'
    tree = ET.parse(project)
    ET.SubElement(tree.find('FileList'), 'File',
                  path='src/memory/tf_audio_ddr_command_buffer.sv',
                  type='file.verilog', enable='1')
    tree.write(project, encoding='utf-8', xml_declaration=True)
    tcl = stage / 'scripts/build.tcl'
    tcl.write_text(replace_once(tcl.read_text(),
                                'set_option -user_code 00000065',
                                'set_option -user_code 00000066'))
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
    if result.returncode or changed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
