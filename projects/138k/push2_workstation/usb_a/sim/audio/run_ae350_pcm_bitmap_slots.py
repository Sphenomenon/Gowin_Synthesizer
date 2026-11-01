#!/usr/bin/env python3
"""Compare current per-slot bitmap permissions with the exact previous owner."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import ae350_pcm_bitmap_slot_sources as sources
import run_ae350_pcm_bitmap_context as previous


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.resolve()
    assert not output.is_relative_to(sources.ROOT)
    output.mkdir(parents=True,exist_ok=False)
    previous.OUT=output
    paths=list(dict.fromkeys(sources.inputs()+[
        Path(__file__).resolve(),Path(previous.__file__).resolve(),previous.WINDOW,
        previous.whole.REFERENCE,sources.ROOT/'sim/test_ae350_pcm_owner.py',
        Path(previous.sources.__file__).resolve()]))
    hashes={str(path):sha(path)for path in paths}
    candidate=sources.SOURCE.read_text()
    before=sources.restore_before_bitmap_slots(candidate)
    assert sources.apply_bitmap_slots(before)==candidate
    old_start=before.index(sources.OLD);new_start=candidate.index(sources.NEW)
    assert before[:old_start]==candidate[:new_start]
    assert before[old_start+len(sources.OLD):]==candidate[new_start+len(sources.NEW):]
    source=output/'candidate.sv';source.write_text(candidate)
    (output/'before.sv').write_text(before)
    (output/'reference.sv').write_text(before.replace('module workstation_ae350_pcm_owner',
        'module pcm_owner_window_reference',1))
    report=dict(schema=1,passed=False,stage='maintained_PCM_bitmap_per_slot_permissions',
        source_sha256=sha(sources.SOURCE),previous_sha256=sources.BASELINE_SHA256,
        input_sha256=hashes,strict_complete_source_inverse=True,
        all_bytes_outside_bitmap_sequence_unchanged=True,new_registers=False,
        sample_or_command_latency_changed=False,derived_predicates_forced=False,
        synthesis=False,pnr=False,hardware_tested=False,physical_gain_claimed=False,
        scope='Actual complete owners, public outputs, all prior sequential state, 512 RAM words and four bitmaps are compared. This is simulation plus a strict source inverse; no full sequential formal or physical timing claim.',
        cases={},negative_controls={})
    try:
        bench,count=previous.actual_bench(before)
        result=previous.simulate('actual-four-state',source,bench,True)
        assert 'checks='+str(count)in result['summary']
        report['cases']['actual_four_state']=dict(result,checks=count)
        print(result['summary'],flush=True)
        report['cases']['whole_owner']=previous.simulate('whole-owner',source,previous.full_owner_bench(),True)
        assert 'PASS PCM window gate whole-owner cycle reference:'in report['cases']['whole_owner']['summary']
        print(report['cases']['whole_owner']['summary'],flush=True)
        mutants={
            'missing_clear':candidate.replace('else if(bitmap_clear_by_slot[bitmap_slot])written[bitmap_slot]<=0;',
                "else if(1'b0)written[bitmap_slot]<=0;",1),
            'wrong_bit':candidate.replace('written[bitmap_slot][write_index]<=1;',
                "written[bitmap_slot][write_index^7'd1]<=1;",1),
            'unknown_uses_known_context':candidate.replace('                if(accepted_start)bitmap_clear_by_slot=4\'hf;',
                '                if(bitmap_start_without_context)bitmap_clear_by_slot=4\'hf;',1).replace(
                '                if(accepted_commit)bitmap_clear_by_slot[tail_slot]=1;',
                '                if(bitmap_commit_without_context)bitmap_clear_by_slot[tail_slot]=1;',1),
        }
        for name,text in mutants.items():
            assert text!=candidate
            path=output/(name+'.sv');path.write_text(text)
            result=previous.simulate('mutant-'+name,path,bench,False)
            assert 'PCM CONTEXT REAL FOUR STATE'in result['summary']
            report['negative_controls'][name]=dict(result,rejected=True)
        lint=subprocess.run(['verilator','--lint-only','--top-module','workstation_ae350_pcm_owner',str(sources.SOURCE)],capture_output=True,text=True,timeout=60)
        (output/'lint.log').write_text(lint.stdout+lint.stderr)
        assert lint.returncode==0,lint.stdout+lint.stderr
        report['strict_lint_passed']=True
        assert hashes=={str(path):sha(path)for path in paths},'source changed during verification'
        report['input_seal_before_after']=True;report['passed']=True
    finally:
        report['output_sha256']={path.relative_to(output).as_posix():sha(path)for path in sorted(output.rglob('*'))if path.is_file()}
        (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=count,negative_controls=len(mutants),verification_sha256=sha(output/'verification.json'))),flush=True)


if __name__=='__main__':main()
