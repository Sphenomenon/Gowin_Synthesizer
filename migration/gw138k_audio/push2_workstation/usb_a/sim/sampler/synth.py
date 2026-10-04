#!/usr/bin/env python3
"""Isolated GW5AST synthesis only. Does not modify main project or program hardware."""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,re,subprocess,xml.etree.ElementTree as ET
ap=argparse.ArgumentParser();ap.add_argument("--top",default="sampler_mode_d");args=ap.parse_args()
ROOT=Path(__file__).resolve().parents[2];rtl=ROOT/'rtl/sampler'
out=ROOT/'out'/datetime.now().strftime('sampler_synthesis_%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
print(out,flush=True)
project=ET.Element('Project');ET.SubElement(project,'Template').text='FPGA';ET.SubElement(project,'Version').text='5'
ET.SubElement(project,'Device',name='GW5AST-138C',pn='GW5AST-LV138PG484AC2/I1').text='gw5ast138c-006'
files=ET.SubElement(project,'FileList')
sources=[rtl/'sampler_pkg.sv']+sorted(f for f in rtl.glob('*.sv') if f.name!='sampler_pkg.sv')
sources += [ROOT/'rtl/tf_audio/storage'/n for n in ('tf_wav_pcm_decoder.v','tf_wav_chunk_parser.v','third_party_sd_spi_file_reader.v','third_party_sd_spi_sector_reader.v','third_party_spi_session.v')]
for f in sources:ET.SubElement(files,'File',path=str(f),type='file.verilog',enable='1')
ET.ElementTree(project).write(out/'sampler.gprj',encoding='utf-8',xml_declaration=True)
(out/'build.tcl').write_text(f'''open_project {{{out/'sampler.gprj'}}}
set_option -top_module {args.top}
set_option -output_base_name sampler
set_option -verilog_std sysv2017
set_option -include_path {{{ROOT/'rtl'}}}
run syn
''')
(out/'inputs_sha256.json').write_text(json.dumps({str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources+[ROOT/'rtl/ddr_address_map.vh']},indent=2)+'\n')
with (out/'synthesis.log').open('w') as log:
    result=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'build.tcl'],cwd=out,stdout=log,stderr=subprocess.STDOUT)
text=(out/'synthesis.log').read_text();print(text[-6000:])
passed=result.returncode==0 and not any(line.startswith('ERROR') for line in text.splitlines())
report=out/'impl/gwsynthesis/sampler_syn.rpt.html'
resources={};fmax=None
if report.exists():
    html=re.sub(r'<[^>]+>',' ',report.read_text());plain=re.sub(r'\s+',' ',html)
    for name,pattern in {'logic':r'Logic (\d+)\(', 'registers':r'Register (\d+) /', 'bsram':r'BSRAM (\d+) /'}.items():
        match=re.search(pattern,plain)
        if match:resources[name]=int(match[1])
    match=re.search(r'Actual Fmax.*?clk [0-9.]+\(MHz\) ([0-9.]+)\(MHz\)',plain)
    if match:fmax=float(match[1])
    (out/'report.txt').write_text(plain+'\n')
print('SYNTH_METRICS '+json.dumps(dict(top=args.top,resources=resources,fmax_mhz=fmax)),flush=True)
(out/'verification.json').write_text(json.dumps(dict(passed=passed,returncode=result.returncode,hardware_tested=False,place_route=False,top=args.top,
    resources=resources,synthesis_fmax_mhz=fmax,target_mhz=76.8,timing_met=fmax is not None and fmax>=76.8),indent=2)+'\n')
if not passed:raise SystemExit(1)
