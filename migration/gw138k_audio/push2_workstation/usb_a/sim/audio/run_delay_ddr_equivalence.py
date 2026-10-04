#!/usr/bin/env python3
"""Run the delay-DDR bit-exact equivalence TB under iverilog.

The reference module comes from the frozen stereo_effects.sv (board lineage).
iverilog refuses its use-before-declaration of selected_id, so a patched
copy is generated into build/ with only that wire declaration moved above
its first use - no logic text is touched.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / 'results/song_guide_full79_20261004_204059/Prj1'
BUILD = Path(__file__).resolve().parent / 'delay_ddr_build'


def main():
    BUILD.mkdir(exist_ok=True)
    ref = BUILD / 'stereo_effects_ref.sv'
    text = (STAGE / 'legacy/rtl/audio/stereo_effects.sv').read_text()
    decl = "  wire [1:0] selected_id=slot_index==0?frame_order[1:0]:slot_index==1?frame_order[3:2]:frame_order[5:4];\n"
    assert text.count(decl) == 1
    text = text.replace(decl, '')
    anchor = "  logic [1:0] slot_index,maintenance_id,work_id;\n"
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + decl)
    ref.write_text(text)

    out = BUILD / 'tb_delay_ddr.vvp'
    cmd = [
        'iverilog', '-g2012', '-o', str(out),
        str(STAGE / 'legacy/rtl/audio/audio_math_pkg.sv'),
        str(Path(__file__).resolve().parent / 'tb_delay_ddr_equivalence.sv'),
        str(ROOT / 'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv'),
        str(ROOT / 'rtl/audio/delay_ddr/delay_ddr_dma.sv'),
        str(ROOT / 'rtl/music/music_async_fifo.sv'),
        str(ref),
    ]
    result = subprocess.run(cmd)
    if result.returncode:
        return result.returncode
    run = subprocess.run(['vvp', str(out)])
    return run.returncode


if __name__ == '__main__':
    sys.exit(main())
