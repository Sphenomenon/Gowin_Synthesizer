#!/usr/bin/env python3
"""0x79: widen the CMD17 data-token wait to the SD spec's NAC scale so a slow
card is never abort-stormed by token-window retries mid-read."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full78_20261004_150443'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full79_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    shutil.copy2(ROOT / 'rtl/tf_audio/storage/tang_mp3/vendor/tf_spi_session.v',
                 stage / 'src/storage/tang_mp3/vendor/tf_spi_session.v')
    shutil.copy2(ROOT / 'rtl/tf_audio/storage/tang_mp3/vendor/tf_sd_spi_sector_reader.v',
                 stage / 'src/storage/tang_mp3/vendor/tf_sd_spi_sector_reader.v')

    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    assert old.count('set_option -user_code 00000078') == 1
    tcl.write_text(old.replace('set_option -user_code 00000078',
                               'set_option -user_code 00000079'))
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
