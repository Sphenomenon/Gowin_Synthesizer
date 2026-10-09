#!/usr/bin/env python3
"""Prove front-card priority and all independent payloads exactly equivalent."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from cnn_ddr_pipeline_patch import (DASHBOARD,predecode_dashboard,
    predecode_dashboard_text_coordinates,parallel_dashboard_cards,shallow_dashboard_card_select,predecode_dashboard_background,
    predecode_dashboard_wave_heights,predecode_dashboard_dynamic_ink)
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--build',type=Path);a=p.parse_args()
original=parallel_dashboard_cards(predecode_dashboard_text_coordinates(predecode_dashboard((BASE/DASHBOARD).read_text())))
patched=shallow_dashboard_card_select(original)
if a.build:
    build=a.build.resolve();metadata=json.loads((build/'build_metadata.json').read_text())
    assert metadata.get('shallow_card_select') and metadata.get('parallel_dashboard_cards')
    expected=original
    if metadata.get('predecoded_background_coordinates'):expected=predecode_dashboard_background(expected,metadata.get('complete_background_coordinates',False))
    if metadata.get('predecoded_wave_heights'):expected=predecode_dashboard_wave_heights(expected)
    if metadata.get('predecoded_dynamic_background_ink'):expected=predecode_dashboard_dynamic_ink(expected)
    patched=(build/'Prj1'/DASHBOARD).read_text()
    assert patched==shallow_dashboard_card_select(expected),'candidate dashboard drift'
def block(text):
    start=text.index('    wire card_front0=') if '    wire card_front0=' in text else text.index('    always @* begin\n        effect_hit_pre=hit0_pre')
    return text[start:text.index('    reg effect_hit;',start)]
body=''
ports='''input hit0_pre,hit1_pre,hit2_pre,input[1:0]front_effect,
input[10:0]effect_rel0_pre,effect_rel1_pre,effect_rel2_pre,
input[9:0]effect_text0_pre,effect_text1_pre,effect_text2_pre,
output reg effect_hit_pre,output reg[1:0]effect_id_pre,
output reg[10:0]effect_relative_pre,output reg[9:0]effect_text_pre'''
for name,text in [('old',original),('fresh',patched)]:
    body+=f'module {name}({ports});\n'+block(text)+'endmodule\n'
body+='''module miter(input[2:0]hit,input[1:0]front,input[32:0]rel,input[29:0]text,output equal);
wire[23:0]a,b;
old o(hit[0],hit[1],hit[2],front,rel[10:0],rel[21:11],rel[32:22],text[9:0],text[19:10],text[29:20],a[23],a[22:21],a[20:10],a[9:0]);
fresh f(hit[0],hit[1],hit[2],front,rel[10:0],rel[21:11],rel[32:22],text[9:0],text[19:10],text[29:20],b[23],b[22:21],b[20:10],b[9:0]);
assign equal=a==b;
endmodule
'''
with tempfile.TemporaryDirectory(prefix='cnn_card_select_sat_') as tmp:
    source=Path(tmp)/'miter.sv';source.write_text(body)
    command=f'read_verilog -sv {source}; hierarchy -top miter; proc; flatten; opt; check -assert; sat -verify -prove equal 1 -show-inputs'
    run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
    assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,hardware_tested=False,pcm_saved=False,
    added_cycles=0,proof='SAT all68inputbits,including all8overlaps/4frontIDs and independent11bitrelative/10bittextpayloads',
    miter_sha256=hashlib.sha256(body.encode()).hexdigest(),
    original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
