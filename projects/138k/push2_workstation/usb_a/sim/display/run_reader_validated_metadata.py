#!/usr/bin/env python3
"""Compare both real reader/cache regressions, including same-edge outputs."""
from pathlib import Path
import argparse,json,hashlib,re,subprocess,sys
u=Path(__file__).resolve().parents[2];sys.path.insert(0,str(u))
from tools import workstation_reader_response_reuse as reuse
from tools import workstation_reader_validated_metadata as compact
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
# The layout package retains its production include spelling. Supply that
# exact authority in the test directory; do not depend on a private stage.
memory_include=out/'src/memory/ddr_address_map.vh'
memory_include.parent.mkdir(parents=True)
memory_include.write_bytes((u/'rtl/ddr_address_map.vh').read_bytes())
source=u/reuse.SOURCE
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();s=source.read_text();s=reuse.adapt(s);candidate=compact.adapt(s)
assert compact.restore(candidate)==s
assert not reuse.configured({})
for bad in [dict(display_reader_storage_policy=reuse.POLICY,demo_role='W',display_metadata_minor=1),
            dict(display_reader_storage_policy='unsupported')]:
    try:reuse.configured(bad)
    except ValueError:pass
    else:raise AssertionError('invalid selection accepted')
for operation,text in [(compact.adapt,s+'\n')]:
    try:operation(text)
    except ValueError:pass
    else:raise AssertionError('source drift accepted')
assert compact.restore(candidate+'\n')==candidate+'\n'
assert not compact.configured({})
for bad in [dict(display_reader_validated_policy=compact.POLICY,demo_role='W'),
            dict(display_reader_validated_policy='unsupported')]:
    try:compact.configured(bad)
    except ValueError:pass
    else:raise AssertionError('invalid compact selection accepted')
header=s[s.index('module display_data_reader'):s.index('    import display_data_layout_pkg::*;')]
ports=[];outputs=[]
for match in re.finditer(r'\b(input|output)\s+(wire|reg)\s*(\[[^\]]+\])?\s*([\w,]+)\s*[,\n]',header):
 direction,kind,width,names=match.groups()
 for name in names.strip(',').split(','):
  ports.append(name)
  if direction=='output':outputs.append((name,width or ''))
assert len(ports)==34 and len(outputs)==23,(len(ports),len(outputs))
wrapper=header+'    wire [4:0] state=candidate.state;\n    localparam [4:0] STORE_PAYLOAD=16;\n    wire [1:0] payload_kind=candidate.payload_kind;\n'
for name,width in outputs:wrapper+=f'    wire {width} reference_{name};\n'
params='#(.METADATA_MINOR(METADATA_MINOR))'
wrapper+='    candidate_display_data_reader '+params+' candidate('+','.join('.'+x+'('+x+')'for x in ports)+');\n'
wrapper+='    reference_display_data_reader '+params+' reference('+','.join('.'+x+'('+('reference_'+x if any(x==y for y,_ in outputs)else x)+')'for x in ports)+');\n'
wrapper+='    integer compared_edges=0;\n    always @(negedge clk)if(rst_n)begin\n'
for name,width in outputs:wrapper+=f'        if({name} !== reference_{name})$fatal(1,"reader public output {name} changed");\n'
wrapper+='''        if(reference.state>=reference.REQ_PAYLOAD && reference.state<=reference.PUBLISH && reference.header_q !== reference.global_q)
            $fatal(1,"accepted header/global equality lost");
        compared_edges=compared_edges+1;
    end
    final $display("PASS reader validated metadata: all23 outputs equal at %0d edges",compared_edges);
endmodule
'''
files={'reference.v':re.sub(r'\bdisplay_data_reader\b','reference_display_data_reader',s),'candidate.v':re.sub(r'\bdisplay_data_reader\b','candidate_display_data_reader',candidate),'twins.sv':wrapper}
for name,text in files.items():(out/name).write_text(text)
inputs=[source,u/'rtl/display_data_layout_pkg.svh',u/'rtl/display_data/display_data_writer.v',u/'sim/p11/tb_display_data_reader.sv',u/'sim/display/tb_display_metadata_v11.sv',Path(__file__),u/compact.TOOL,u/reuse.TOOL,u/reuse.MANIFEST,u/'rtl/ddr_address_map.vh']
hashes={str(p):sha(p)for p in inputs};cases=[]
for top,tb in [('tb_display_data_reader',inputs[3]),('tb_display_metadata_v11',inputs[4])]:
 binary=out/(top+'.vvp');sources=[inputs[1],inputs[2],*(out/name for name in files),tb]
 with (out/(top+'-compile.log')).open('w')as log:subprocess.run(['iverilog','-g2012','-I'+str(out),'-I'+str(u),'-s',top,'-o',str(binary),*map(str,sources)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
 with (out/(top+'-run.log')).open('w')as log:subprocess.run(['vvp',str(binary)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
 log=(out/(top+'-run.log')).read_text();assert 'PASS reader validated metadata: all23 outputs equal at 'in log;cases.append(dict(top=top,log_sha256=sha(out/(top+'-run.log')),output=log))
negative_controls=[]
for name,anchor in [('low','meta_low_ok_q<=rsp_q[255:224]=='),
                    ('high','meta_high_ok_q<=meta_low_ok_q &&')]:
    require_anchor=candidate.count(anchor)==1
    assert require_anchor,'metadata validation mutation anchor changed'
    mutated=candidate.replace(anchor,anchor.split('<=')[0]+"<=1'b1 || "+anchor.split('<=')[1],1)
    path=out/('mutant-'+name+'.v')
    path.write_text(re.sub(r'\bdisplay_data_reader\b','candidate_display_data_reader',mutated))
    top='tb_display_metadata_v11';binary=out/('mutant-'+name+'.vvp')
    sources=[inputs[1],inputs[2],out/'reference.v',path,out/'twins.sv',inputs[4]]
    with (out/('mutant-'+name+'-compile.log')).open('w')as log:
        subprocess.run(['iverilog','-g2012','-I'+str(out),'-I'+str(u),'-s',top,
                        '-o',str(binary),*map(str,sources)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
    with (out/('mutant-'+name+'-run.log')).open('w')as log:
        result=subprocess.run(['vvp',str(binary)],stdout=log,stderr=subprocess.STDOUT,timeout=180)
    text=(out/('mutant-'+name+'-run.log')).read_text()
    assert result.returncode!=0 and 'reader public output' in text,(name,text)
    negative_controls.append(dict(name=name,rejected=True,
        run_log_sha256=sha(out/('mutant-'+name+'-run.log'))))
assert all(sha(p)==h for p,h in hashes.items())
r=dict(passed=True,production_changed=False,profile_selected='explicit_M_preboard_only',synthesis=False,board_accessed=False,source_sha256=hashes,cases=cases,adaptation_manifest_sha256=sha(u/reuse.MANIFEST),scope='Actual legacy/minor1 reader twins: all23 public outputs at identical edges, accepted header equality, corrupt/overwritten metadata, retry and last-good cache. No routed benefit is inferred.')
r['negative_controls']=negative_controls
(out/'verification.json').write_text(json.dumps(r,indent=2)+'\n');print('PASS reader validated metadata',[(v['top'],v['output'].splitlines()[-1])for v in cases],negative_controls)
