#!/usr/bin/env python3
"""Audit a complete Flash boot candidate, optionally deploy and test live under rollback.

Never promotes LATEST_WORKSTATION. With no --program, performs only local
artifact/source/routed checks. Requires the frozen workstation, not an isolated
DDR probe. Wholeboard baseline STA and physical power-cycle acceptance remain
separate; a successful source/clock gate is not a claim of wholeboard closure.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('--program',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    build=args.build.resolve()
    output=(args.output or build/('workstation_acceptance_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    output.mkdir(parents=True,exist_ok=False)
    result=dict(passed=False,programming_started=False,hardware_tested=False,
        promoted=False,physical_power_cycle_tested=False,build=str(build),
        wholeboard_timing_closed=False,checks={},started_at=datetime.now().astimezone().isoformat())
    def save():
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    def run(label,command):
        process=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=600)
        (output/(label+'.log')).write_text(process.stdout+process.stderr)
        return label,process.returncode
    save()
    try:
        meta=json.loads((build/'build_metadata.json').read_text())
        status=json.loads((build/'tool_result.json').read_text())
        assert meta['full_workstation'] and status['exit_code']==0 and status['inputs_unchanged'],'incomplete build or source drift'
        memory=json.loads((build/'workstation_memory.json').read_text())
        assert 0<memory['pnr_bsram']<=260,'physical BSRAM exceeded frozen workstation budget'
        if meta.get('transport','direct')=='serial':
            assert json.loads((build/'serial_compatibility_source_audit.json').read_text())['passed'],'original parser/native DDR compatibility failed'
        checks=[
            ('clk50',[sys.executable,str(ROOT/'tools/audit_clk50_timing.py'),str(build),'--require-closed']),
            ('scope_cdc',[sys.executable,str(ROOT/'tools/audit_scope_routes.py'),str(build),'--output',str(output/'scope_cdc.json')]),
            ('clk50_cdc',[sys.executable,str(ROOT/'tools/audit_clk50_cdc_routes.py'),str(build),'--output',str(output/'clk50_cdc.json')]),
            ('video_pll',[sys.executable,str(build/'Prj1/scripts/check_video_pll_init.py'),'--root',str(build/'Prj1'),'--output',str(output/'video_pll.json')])]
        with ThreadPoolExecutor(max_workers=4) as pool:
            result['checks']=dict(pool.map(lambda check:run(*check),checks))
        # Keep all evidence even if one independent routed check fails.
        sys.path.insert(0,str(ROOT/'tools'))
        deploy=importlib.import_module('deploy_cnn_flash_boot')
        clock_gate=deploy.audit_previous_positive_clocks(build)
        result['previous_positive_clock_audit']=clock_gate
        save()
        assert all(value==0 for value in result['checks'].values()),'routed timing/CDC/PLL check failed'
        assert clock_gate['passed'],'previously positive clocks regressed: '+','.join(clock_gate['failed_clocks'])
        sys.path.insert(0,str(build/'Prj1/scripts'))
        os.environ['PRJ1_DDR_REFERENCE']=str(ROOT/'vendor/ddr3_reference/ddr3_memory_interface.vo')
        from check_build import inspect_ddr_audit,inspect_ddr_configuration_audit
        from check_serializer_startup import inspect_serializer_startup
        source_errors,source=inspect_ddr_audit()
        configuration_errors,configuration=inspect_ddr_configuration_audit()
        assert not source_errors and not configuration_errors,(source_errors,configuration_errors)
        errors,evidence=inspect_serializer_startup(
            (build/'Prj1/impl/pnr/Prj1.sdf').read_text(),(build/'Prj1/impl/pnr/Prj1.vo').read_text(),
            ddr_audit=source,sdc=(build/'Prj1/constraints/tang_mega_138k.sdc').read_text())
        (output/'ddr_tmds_startup.json').write_text(json.dumps(dict(errors=errors,evidence=evidence,configuration=configuration),indent=2)+'\n')
        assert not errors,errors
        result['ddr_tmds_startup_passed']=True
        label,code=run('deploy_preview',[sys.executable,str(ROOT/'tools/deploy_cnn_flash_boot.py'),str(build)])
        result['checks'][label]=code;save();assert code==0,'candidate artifact or deployment preview failed'
        result['eligible_for_hardware_verification']=True
        if args.program:
            result['programming_started']=True;save()
            deploy_output=output/'flash_deploy'
            process=subprocess.run([sys.executable,str(ROOT/'tools/deploy_cnn_flash_boot.py'),str(build),
                '--program','--exercise-live','--output',str(deploy_output)],cwd=ROOT,capture_output=True,text=True,timeout=2400)
            (output/'deploy.log').write_text(process.stdout+process.stderr)
            result['deploy_exit_code']=process.returncode
            if (deploy_output/'result.json').exists():result['deployment']=json.loads((deploy_output/'result.json').read_text())
            save()
            assert process.returncode==0,'Flash/model/live test failed; inspect deployment and rollback evidence'
            assert result['deployment']['passed'] and result['deployment']['live_smoke_passed']
            result['hardware_tested']=True
        result['passed']=True
        print('PASS '+('full workstation Flash/model/live checks' if args.program else 'local routed/artifact gate; hardware not tested')+'; '+str(output),flush=True)
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        result['finished_at']=datetime.now().astimezone().isoformat();save()

if __name__=='__main__':
    main()
