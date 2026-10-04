#!/usr/bin/env python3
"""MIT upstream song adapter: omit per-note DC placement before stereo mixing.

The upstream video draws each voice separately. Its per-note offsets add up
for chords in the exported stereo mix, driving tanh into a large DC bias.
A physical two-axis display has one summed trace. Keep all notes/envelopes/
ratios/timing/drums, but center each voice before the original common mix.
Run only with PYTHONPATH pointing at the pinned external upstream checkout.
"""
import sys
from pathlib import Path
from oscilloscope_music import song,cli

original_add = song._addv


def centered_add(L,R,voice,x,y,start_s,dur_s,amp=1.0,dx=0.0,dy=0.0):
    return original_add(L,R,voice,x,y,start_s,dur_s,amp,dx=0.0,dy=0.0)


if __name__ == '__main__':
    song._addv = centered_add
    left,right,duration = song.build_song()
    path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True)
    cli.write_wav(left,right,duration,path)
    print('Centered stereo sum, unchanged arrangement: '+str(duration)+'s')
