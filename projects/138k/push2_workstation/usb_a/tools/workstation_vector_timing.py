"""Exact per-voice envelope transform for the measured vector setup path.

No added cycles, voices, state, ROM data or event rules. The reference source
must match the p27 snapshot; this helper cannot absorb unrelated edits.
"""
from pathlib import Path
import hashlib

VECTOR = 'rtl/audio/scope_vec/scope_vec_engine.sv'
REFERENCE = 'results/timing_p27_uart_cdc_route1_20261018_142516_456857'
BASE_SHA256 = 'c0e7208d907da85ec12172f1eb2babf6b2b69879bb9bd08f68bc26334f7b49c1'


def transform(text):
    if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256:
        raise ValueError('per-voice envelope reference drift')
    start = text.index('                        env_sum={')
    end = text.index('                        state<=2;', start)
    original = text[start:end]
    first = "                        env_sum={1'b0,envelope[voice_index]}+{1'b0,attack[voice_index]};\n"
    if original.count(first) != 1:
        raise ValueError('unexpected shared envelope arithmetic')
    local = original.replace(first, '').replace('[voice_index]', '[j]').replace('env_sum', 'voice_attack_sum[j]')
    local = ('                        // Keep each voice arithmetic local; decode only its write enable.\n'
             '                        for(j=0;j<VOICES;j=j+1) if(voice_index==j) begin\n'
             + ''.join('    ' + line + '\n' for line in local.splitlines())
             + '                        end\n')
    text = text[:start] + local + text[end:]
    anchor = '    reg [24:0] env_sum;\n'
    if text.count(anchor) != 1:
        raise ValueError('unexpected shared envelope temporary')
    return text.replace(anchor, """    wire [24:0] voice_attack_sum[0:VOICES-1];
    for(genvar e=0;e<VOICES;e=e+1) begin: g_local_envelope
        assign voice_attack_sum[e]={1'b0,envelope[e]}+{1'b0,attack[e]};
    end
""")
