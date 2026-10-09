#!/usr/bin/env python3
"""Host-only tests of acceptance readiness and serialized deployment selection."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    cases=[]
    with tempfile.TemporaryDirectory(prefix='cnn_flash_waiter_')as temp:
        root=Path(temp);tools=root/'tools';tools.mkdir()
        (tools/'wait_cnn_flash_acceptance.py').write_bytes((ROOT/'tools/wait_cnn_flash_acceptance.py').read_bytes())
        (tools/'verify_cnn_flash_workstation.py').write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[1],"called.json").write_text(json.dumps(sys.argv[2:]))\n')
        for label in ['terminal_artifacts_missing','partial_terminal_artifact','earlier_hardware_success','first_hardware_attempt','earlier_attempt_failed','build_failed','existing_output','unfinished_predecessor','partial_predecessor']:
            build=root/label;build.mkdir()
            status=dict(exit_code=1 if label=='build_failed' else 0,inputs_unchanged=True)
            (build/'tool_result.json').write_text(json.dumps(status))
            if label!='terminal_artifacts_missing':
                (build/'workstation_memory.json').write_text('{}')
                (build/'flash_bundle.json').write_text('{' if label=='partial_terminal_artifact' else '{}')
            command=[sys.executable,str(tools/'wait_cnn_flash_acceptance.py'),str(build),'--program','--timeout-minutes','0.001']
            if label in ['earlier_hardware_success','first_hardware_attempt','earlier_attempt_failed','unfinished_predecessor','partial_predecessor']:
                predecessor=build/'predecessor';report=predecessor/'automatic_acceptance';report.mkdir(parents=True)
                prior=dict(finished_at=None if label=='unfinished_predecessor' else 'test',hardware_tested=label=='earlier_hardware_success',programming_started=label in ['earlier_hardware_success','earlier_attempt_failed'])
                (report/'result.json').write_text('{' if label=='partial_predecessor' else json.dumps(prior))
                command += ['--predecessor',str(predecessor)]
            if label=='existing_output':(build/'automatic_acceptance').mkdir()
            result=subprocess.run(command,capture_output=True,text=True,timeout=5)
            called=build/'called.json';should_call=label in ['earlier_hardware_success','first_hardware_attempt']
            assert called.exists()==should_call,(label,result.stdout,result.stderr)
            assert (result.returncode==0)==should_call,(label,result.stdout,result.stderr)
            program_requested=False
            if called.exists():
                program_requested='--program' in json.loads(called.read_text())
                assert program_requested==(label=='first_hardware_attempt'),label
            cases.append(dict(case=label,passed=True,verifier_called=called.exists(),program_requested=program_requested))
    report=dict(passed=True,hardware_tested=False,hardware_io=False,pcm_saved=False,cases=cases)
    (ROOT/'reports/CNN_FLASH_BOOT_WAITER_TESTS.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
