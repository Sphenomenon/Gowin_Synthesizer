#!/usr/bin/env python3
"""Compare all batch outputs to exact v20 under the real APB/PCM-owner fixture."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools import workstation_task3_capture_compare as capture

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tracked=[Path(__file__),ROOT/capture.SOURCE,ROOT/capture.TOOL,
             ROOT/'sim/audio/tb_workstation_task3_phone_batch_m.sv',ROOT/'sim/audio/run_workstation_task3_phone_batch_m.py']
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();before={str(p):sha(p) for p in tracked}
    result=dict(schema=1,passed=False,input_sha256=before,hardware_tested=False,physical_CDC_accepted=False,
                timing_closed=False,whole_batch_formal_proof=False)
    def run(name,cmd):
        r=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
        log=out/(name+'.log');log.write_text(r.stdout)
        result[name]=dict(command=cmd,exit_code=r.returncode,log_sha256=sha(log))
        if r.returncode:raise ValueError(name+' failed: '+r.stdout)
        return r.stdout
    try:
        run('default_fixture',['python3',str(ROOT/'sim/audio/run_workstation_task3_phone_batch_m.py'),
            '--project',str(a.project.resolve()),'--output',str(out/'default')])
        snapshot=out/'default/inputs';source=(snapshot/capture.SOURCE).read_text()
        old=capture.restore(source).replace('module workstation_task3_phone_batch_m #(',
                                           'module capture_reference #(',1)
        reference=out/'reference.sv';reference.write_text(old)
        bench=(snapshot/'sim/audio/tb_workstation_task3_phone_batch_m.sv').read_text()
        instance=re.search(r'workstation_task3_phone_batch_m\s*#\(\.TIMEOUT_CYCLES\(2500\)\)\s*batch\((.*?)\);',bench,re.S)
        assert instance
        bindings=dict(re.findall(r'\.(\w+)\(([^()]*(?:\([^()]*\)[^()]*)*)\)',instance[1]))
        ports=[];direction=width=''
        for item in source.split(')(\n',1)[1].split('\n);',1)[0].split(','):
            item=item.strip();match=re.fullmatch(r'(input|output)\s+(?:wire|reg)\s*(\[[^]]+\])?\s*(\w+)',item)
            if match:direction,width,name=match[1],match[2] or '',match[3]
            else:
                assert re.fullmatch(r'\w+',item),item
                name=item
            ports.append((direction,width,name))
        declarations=[];connections=[];checks=[]
        for direction,width,name in ports:
            if direction=='input':
                assert name in bindings,name
                connections.append('.'+name+'('+bindings[name]+')')
            else:
                declarations.append('wire '+width+' shadow_'+name+';')
                connections.append('.'+name+'(shadow_'+name+')')
                checks.append('if(batch.'+name+' !== shadow_'+name+')$fatal(1,"batch output difference: '+name+'");')
        extra='\n'.join(declarations)+'''
    defparam batch.CAPTURE_COMPARE_GROUP_BITS=8;
    capture_reference #(.TIMEOUT_CYCLES(2500)) shadow(
'''+',\n'.join(connections)+''');
    integer capture_equivalence_cycles=0;
    always @(negedge clk)if(reset_n)begin
        capture_equivalence_cycles=capture_equivalence_cycles+1;
'''+ '\n'.join(checks)+'''\nend
'''
        bench=bench[:instance.end()]+extra+bench[instance.end():]
        # The existing fixture forces a saturated transaction ID once. Apply
        # the same stimulus to both owners; it is not a design adaptation.
        bench=bench.replace("force batch.next_sequence=32'hffffffff;",
                            "force batch.next_sequence=32'hffffffff;force shadow.next_sequence=32'hffffffff;")
        bench=bench.replace('release batch.next_sequence;','release batch.next_sequence;release shadow.next_sequence;')
        marker='        $finish;';assert bench.count(marker)==1
        bench=bench.replace(marker,'        $display("PASS capture_equivalence cycles=%0d outputs='+str(len(checks))+'",capture_equivalence_cycles);\n'+marker)
        generated=out/'bench.sv';generated.write_text(bench)
        apbs=[p for p in (snapshot/'prepared').rglob('*') if p.is_file()];assert len(apbs)==1
        binary=out/'equivalence.vvp'
        run('compile',['iverilog','-g2012','-s','tb_workstation_task3_phone_batch_m','-o',str(binary),
            str(generated),str(snapshot/'rtl/audio/workstation_ae350_pcm_owner.sv'),str(snapshot/capture.SOURCE),
            str(snapshot/'default_reference.sv'),str(reference),str(apbs[0])])
        log=run('simulation',['vvp',str(binary)])
        match=re.search(r'PASS capture_equivalence cycles=(\d+) outputs=(\d+)',log);assert match
        base=json.loads((out/'default/verification.json').read_text());assert base['passed']
        result.update(passed=True,cycles=int(match[1]),outputs=int(match[2]),
            public_outputs=[name for d,w,name in ports if d=='output'],
            actual_owner_checks=base['checks'],actual_owner_reads=base['actual_owner_reads'],
            actual_owner_writes=base['actual_owner_writes'],continuing_audio_ticks=base['continuing_audio_ticks'],
            baseline_receipt_sha256=sha(out/'default/verification.json'),
            reference_sha256=sha(reference),bench_sha256=sha(generated),
            scope='Directed whole batch/real async APB/PCM owner cycle comparison,including cancellation,link loss,timeout,backpressure,reused capture,transaction exhaustion and sample progress. Full unsigned comparator all-state proof is separate.')
    except Exception as exc:result['error']=repr(exc);raise
    finally:
        result['inputs_unchanged']=before=={str(p):sha(p) for p in tracked}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['inputs_unchanged']
    print({k:result[k] for k in ('passed','cycles','outputs','actual_owner_checks','continuing_audio_ticks')})
if __name__=='__main__':main()
