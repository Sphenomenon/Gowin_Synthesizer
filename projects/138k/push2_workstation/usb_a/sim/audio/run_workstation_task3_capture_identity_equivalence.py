#!/usr/bin/env python3
"""Compare the capture equality experiment with exact v21 and a real PCM owner."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_capture_compare as ordering
from tools import workstation_task3_capture_identity_experiment as identity

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    inputs=[Path(__file__),ROOT/identity.SOURCE,ROOT/identity.COMPARATOR,
            ROOT/'tools/workstation_task3_capture_identity_experiment.py',
            ROOT/'sim/audio/tb_workstation_task3_phone_batch_m.sv',
            ROOT/'sim/audio/run_workstation_task3_phone_batch_m.py']
    before={str(p):sha(p) for p in inputs}
    result=dict(schema=1,passed=False,input_sha256=before,hardware_tested=False,
        full_CDC_accepted=False,timing_closed=False,whole_batch_formal_proof=False)
    def run(name,command):
        r=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
        log=out/(name+'.log');log.write_text(r.stdout)
        result[name]=dict(command=command,exit_code=r.returncode,log_sha256=sha(log))
        if r.returncode:raise ValueError(name+' failed: '+r.stdout)
        return r.stdout
    try:
        run('default_fixture',[sys.executable,'-B',str(ROOT/'sim/audio/run_workstation_task3_phone_batch_m.py'),
            '--project',str(a.project.resolve()),'--output',str(out/'default')])
        snapshot=out/'default/inputs'
        native=(snapshot/identity.SOURCE).read_text()
        assert native.count(ordering.PARAMETER)==1
        parent=native.replace(ordering.PARAMETER,ordering.SELECTED,1)
        selected=out/'selected.sv';selected.write_text(identity.apply(parent))
        reference=out/'reference.sv'
        reference.write_text(parent.replace('module workstation_task3_phone_batch_m #(',
                                           'module capture_identity_reference #(',1))
        bench=(snapshot/'sim/audio/tb_workstation_task3_phone_batch_m.sv').read_text()
        instance=re.search(r'workstation_task3_phone_batch_m\s*#\(\.TIMEOUT_CYCLES\(2500\)\)\s*batch\((.*?)\);',bench,re.S)
        assert instance
        bindings=dict(re.findall(r'\.(\w+)\(([^()]*(?:\([^()]*\)[^()]*)*)\)',instance[1]))
        ports=[];direction=width=''
        for item in parent.split(')(\n',1)[1].split('\n);',1)[0].split(','):
            item=item.strip();m=re.fullmatch(r'(input|output)\s+(?:wire|reg)\s*(\[[^]]+\])?\s*(\w+)',item)
            if m:direction,width,name=m[1],m[2] or '',m[3]
            else:assert re.fullmatch(r'\w+',item);name=item
            ports.append((direction,width,name))
        declarations=[];connections=[];checks=[]
        for direction,width,name in ports:
            if direction=='input':connections.append('.'+name+'('+bindings[name]+')')
            else:
                declarations.append('wire '+width+' shadow_'+name+';')
                connections.append('.'+name+'(shadow_'+name+')')
                checks.append('if(batch.'+name+' !== shadow_'+name+')$fatal(1,"identity batch output difference: '+name+'");')
        extra='\n'.join(declarations)+'\ncapture_identity_reference #(.TIMEOUT_CYCLES(2500)) shadow(\n'+',\n'.join(connections)+''');
    integer identity_equivalence_cycles=0;
    always @(negedge clk)if(reset_n)begin
        identity_equivalence_cycles=identity_equivalence_cycles+1;
'''+ '\n'.join(checks)+'\nend\n'
        bench=bench[:instance.end()]+extra+bench[instance.end():]
        bench=bench.replace("force batch.next_sequence=32'hffffffff;",
            "force batch.next_sequence=32'hffffffff;force shadow.next_sequence=32'hffffffff;")
        bench=bench.replace('release batch.next_sequence;','release batch.next_sequence;release shadow.next_sequence;')
        marker='        $finish;';assert bench.count(marker)==1
        bench=bench.replace(marker,'        $display("PASS identity_equivalence cycles=%0d outputs='+str(len(checks))+'",identity_equivalence_cycles);\n'+marker)
        generated=out/'bench.sv';generated.write_text(bench)
        apbs=[p for p in (snapshot/'prepared').rglob('*') if p.is_file()];assert len(apbs)==1
        binary=out/'equivalence.vvp'
        run('compile',['iverilog','-g2012','-s','tb_workstation_task3_phone_batch_m','-o',str(binary),
            str(generated),str(snapshot/'rtl/audio/workstation_ae350_pcm_owner.sv'),str(selected),
            str(ROOT/identity.COMPARATOR),str(snapshot/'default_reference.sv'),str(reference),str(apbs[0])])
        log=run('simulation',['vvp',str(binary)])
        m=re.search(r'PASS identity_equivalence cycles=(\d+) outputs=(\d+)',log);assert m
        base=json.loads((out/'default/verification.json').read_text());assert base['passed']
        result.update(passed=True,cycles=int(m[1]),outputs=int(m[2]),
            actual_owner_checks=base['checks'],continuing_audio_ticks=base['continuing_audio_ticks'],
            actual_owner_reads=base['actual_owner_reads'],actual_owner_writes=base['actual_owner_writes'],
            parent_sha256=identity.digest(parent),selected_sha256=sha(selected),bench_sha256=sha(generated),
            reference_sha256=sha(reference),baseline_receipt_sha256=sha(out/'default/verification.json'),
            scope='Directed full batch outputs with exact v21 ordering parent,actual async APB and PCM owner,cancellation,link loss,timeout,backpressure,capture reuse and continuing audio ticks; local mapped all-state equality proof is separate.')
    except Exception as exc:result['error']=repr(exc);raise
    finally:
        result['inputs_unchanged']=before=={str(p):sha(p) for p in inputs}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['inputs_unchanged']
    print({k:result[k] for k in ('passed','cycles','outputs','actual_owner_checks','continuing_audio_ticks')})
if __name__=='__main__':main()
