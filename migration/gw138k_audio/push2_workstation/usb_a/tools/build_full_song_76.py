#!/usr/bin/env python3
"""Register the CNN DDR request after its CDC FIFO."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full75_20261004_033023'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full76_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    shutil.copy2(ROOT / 'rtl/music/basic_pitch_workstation_link.sv',
                 stage / 'rtl/music/basic_pitch_workstation_link.sv')
    shutil.copy2(ROOT / 'rtl/music/basic_pitch_ddr_command_buffer.sv',
                 stage / 'rtl/music/basic_pitch_ddr_command_buffer.sv')
    project = stage / 'Prj1.gprj'
    project_text = project.read_text()
    insert = '        <File path="rtl/music/basic_pitch_ddr_command_buffer.sv" type="file.verilog" enable="1" />\n'
    assert insert not in project_text
    assert project_text.count('</FileList>') == 1
    project.write_text(project_text.replace('</FileList>', insert + '    </FileList>'))
    assert old.count('set_option -user_code 00000075') == 1
    tcl.write_text(old.replace('set_option -user_code 00000075',
                               'set_option -user_code 00000076'))
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
