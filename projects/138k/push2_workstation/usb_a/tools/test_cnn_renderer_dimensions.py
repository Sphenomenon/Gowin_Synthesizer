#!/usr/bin/env python3
"""Compile actual first-issue dimension guard; unsupported dimensions fail explicitly."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from cnn_ddr_pipeline_patch import RENDERER,align_renderer_predecode,register_renderer_first_issue
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
if a.build:
    meta=json.loads((a.build/'build_metadata.json').read_text());assert meta.get('registered_renderer_first_issue')
    text=(a.build/'Prj1'/RENDERER).read_text()
else:
    base=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'/RENDERER
    text=register_renderer_first_issue(align_renderer_predecode(base.read_text()))
guard=re.search(r'    generate if\(WIDTH<2.*?    end endgenerate',text,re.S)[0]
body='module dimensions #(parameter WIDTH=1920,HEIGHT=1080)();\n'+guard+'\nendmodule\n'
cases=[]
with tempfile.TemporaryDirectory(prefix='cnn_renderer_dimensions_')as temp:
    src=Path(temp)/'guard.sv';src.write_text(body)
    for width,height in [(2,1),(64,1),(1920,1080),(2048,2048),(0,1),(1,1),(3,1),(2050,1080),(1920,0),(1920,2049),(-2,1080)]:
        supported=2<=width<=2048 and width%2==0 and 1<=height<=2048
        cmd=['iverilog','-g2012','-s','dimensions',f'-Pdimensions.WIDTH={width}',f'-Pdimensions.HEIGHT={height}','-o',str(Path(temp)/'guard'),str(src)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
        assert (result.returncode==0)==supported,(width,height,result.stderr)
        if not supported:assert 'cnn_renderer_first_issue_invalid_dimensions' in result.stderr,result.stderr
        cases.append(dict(width=width,height=height,supported=supported,explicit_compile_rejection=not supported,passed=True))
report=dict(passed=True,source_bound=bool(a.build),build=str(a.build)if a.build else None,hardware_tested=False,pcm_saved=False,guard_sha256=hashlib.sha256(guard.encode()).hexdigest(),cases=cases)
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
