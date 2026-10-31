#!/usr/bin/env python3
"""Read-only complete-workstation FIFO reset/CEA/LSB-adder regression."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_demo_audit import verify_prepared
from tools.workstation_runtime_pcm_cdc import PcmNetlist
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_usb_fifo_reset import audit_synthesis


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('full workstation FIFO regression: '+message)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--process-exit-code',type=int,required=True)
    p.add_argument('--expect-legacy-alias-failure',action='store_true')
    a=p.parse_args();candidate=a.candidate.resolve();out=a.output.resolve()
    require(a.process_exit_code==0 and not out.exists() and candidate not in out.parents,'completed synthesis/new independent output required')
    out.mkdir(parents=True)
    manifest=candidate/'integration_inputs.json';metadata=json.loads(manifest.read_text())
    role,profile,stage=verify_prepared(candidate,metadata)
    vg=stage/'impl/gwsynthesis/custom_138k_integration.vg';log=candidate/'synthesis.log'
    text=log.read_text();require(text.count('GowinSynthesis finish')==1 and not re.search(r'^ERROR\b',text,re.M),'actual compiler completion missing')
    inputs=[manifest,vg,log,ROOT/'tools/workstation_usb_fifo_reset.py',ROOT/'tools/workstation_demo_audit.py',
        ROOT/'tools/workstation_runtime_pcm_cdc.py',ROOT/'tools/workstation_synthesis_netlist.py',Path(__file__).resolve()]
    hashes={str(path):sha(path) for path in inputs}
    n=PcmNetlist(vg.read_text(),'workstation_custom_138k_top');gate=audit_synthesis(n)
    result=dict(schema=1,passed=False,candidate_identity=profile['candidate_identity'],role=role,
        process_exit_code=0,input_sha256=hashes,lexical_connection_audit=n.lexical_connection_audit,
        actual_gate=gate,negative_controls={},candidate_inputs_modified=False,source_RTL_modified=False,
        full_workstation_synthesis_gate_accepted=False,PNR=False,hardware_tested=False)
    try:
        try:audit_synthesis(SynthesisNetlist(vg.read_text(),'workstation_custom_138k_top'))
        except ValueError as error:
            require('actual packet memory cannot write before local release' in str(error),'wrong alias negative oracle')
            result['negative_controls']['escaped_formal_alias_omitted']=dict(rejected=True,error=str(error))
        else:
            require(not a.expect_legacy_alias_failure,
                'complete-workstation alias negative did not reproduce independent-cut defect')
            result['legacy_parser_comparison']=dict(gate_passed=True,
                alias_defect_triggered_by_this_mapping=False,strict_lexer_still_required=True)
        producer=next(iter(gate['write_groups']['produce_w_bin'].values()))
        release=gate['release_registers'][0]
        memory=gate['actual_memory_write_pin'].rsplit('/',1)[0]
        mutations=[('producer_reset_bypass',producer,'ports','CLEAR',"1'b0"),
            ('producer_wrong_clock',producer,'ports','CLK',"1'b0"),
            ('release_wrong_clock',release,'ports','CLK',"1'b0"),
            ('memory_admission_bypass',memory,'ports','CEA',"1'b1")]
        grant=n.pin(memory,'CEA')
        grant_drivers=[path for path,c in n.cells.items()
            if re.fullmatch('LUT[1-6]',c['kind']) and n.pin(path,'F')==grant]
        require(len(grant_drivers)==1,'actual packet CEA must have one reviewed LUT driver')
        grant_driver=grant_drivers[0];width=int(n.cells[grant_driver]['kind'][3:])
        # Keep every real input connected, including final release. Only the
        # real LUT truth table bypasses release, so the Boolean/cofactor proof
        # itself must reject this mutation rather than a missing-frontier test.
        mutations.append(('admission_lut_truth_table_bypass',grant_driver,'parameters','INIT',
            str(1<<width)+"'h"+format((1<<(1<<width))-1,'x')))
        increment=gate['pointer_increment_function']
        if increment.get('kind')=='ALU':
            adder=increment['primitive']
            mutations += [('adder_mode',adder,'parameters','ALU_MODE','1'),
                ('adder_carry',adder,'ports','CIN',"1'b1"),
                ('adder_operand',adder,'ports','I1',"1'b0")]
            result['pointer_increment_mapping']='exact_real_ALU_MODE0'
        else:
            pointer=next(path for bit,path in gate['write_groups']['produce_w_bin'].items() if int(bit)==0)
            data=n.pin(pointer,'D')
            drivers=[path for path,c in n.cells.items()
                if re.fullmatch('LUT[1-6]',c['kind']) and n.pin(path,'F')==data]
            require(len(drivers)==1,'non-ALU producer Q0 must have one reviewed LUT driver')
            driver=drivers[0];width=int(n.cells[driver]['kind'][3:])
            mutations += [('pointer_data_bypass',pointer,'ports','D',"1'b0"),
                ('pointer_enable_bypass',pointer,'ports','CE',"1'b0"),
                ('pointer_lut_truth_table_bypass',driver,'parameters','INIT',
                    str(1<<width)+"'h"+format((1<<(1<<width))-1,'x'))]
            result['pointer_increment_mapping']='effective_next_Q_actual_LUT'
        for name,path,field,key,value in mutations:
            original=n.cells[path][field][key];n.cells[path][field][key]=value
            try:
                try:audit_synthesis(n)
                except ValueError as error:result['negative_controls'][name]=dict(rejected=True,error=str(error))
                else:raise ValueError('actual full-netlist negative escaped: '+name)
            finally:n.cells[path][field][key]=original
        require(audit_synthesis(n)==gate,'mutant restoration changed actual parsed netlist')
        require(verify_prepared(candidate,metadata)[1]==profile,'immutable closure changed during audit')
        require({str(path):sha(path) for path in inputs}==hashes,'candidate/auditor inputs changed during audit')
        result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=True,actual_registers=13,negative_controls=len(result['negative_controls']))))


if __name__=='__main__':main()
