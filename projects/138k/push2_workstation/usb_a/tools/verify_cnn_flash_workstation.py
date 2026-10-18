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
import hashlib
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
        if meta.get('ddr_initial_aux_settle_ms'):
            assert meta.get('startup_panic_aligns_delay_history'),'deferred DDR candidate lacks cold P10 history alignment; not eligible for release'
        status=json.loads((build/'tool_result.json').read_text())
        assert meta['full_workstation'] and status['exit_code']==0 and status['inputs_unchanged'],'incomplete build or source drift'
        memory=json.loads((build/'workstation_memory.json').read_text())
        assert not meta.get('synchronous_delay_read_fifo') or meta.get('synchronous_delay_write_fifo'),'read FIFO budget requires matching write FIFO'
        limit=268 if meta.get('synchronous_delay_read_fifo') else (264 if meta.get('synchronous_delay_write_fifo') else 260)
        assert meta.get('physical_bsram_limit',260)==limit and 0<memory['pnr_bsram']<=limit,'physical BSRAM exceeded explicit candidate budget'
        if meta.get('transport','direct')=='serial':
            assert json.loads((build/'serial_compatibility_source_audit.json').read_text())['passed'],'original parser/native DDR compatibility failed'
        checks=[
            ('clk50',[sys.executable,str(ROOT/'tools/audit_clk50_timing.py'),str(build),'--require-closed']),
            ('ddr_ui',[sys.executable,str(ROOT/'tools/audit_ddr_ui_timing.py'),str(build),'--output',str(output/'ddr_ui_timing.json'),'--require-closed']),
            ('scope_cdc',[sys.executable,str(ROOT/'tools/audit_scope_routes.py'),str(build),'--output',str(output/'scope_cdc.json')]),
            ('clk50_cdc',[sys.executable,str(ROOT/'tools/audit_clk50_cdc_routes.py'),str(build),'--output',str(output/'clk50_cdc.json')]),
            ('video_pll',[sys.executable,str(build/'Prj1/scripts/check_video_pll_init.py'),'--root',str(build/'Prj1'),'--output',str(output/'video_pll.json')])]
        with ThreadPoolExecutor(max_workers=5) as pool:
            result['checks']=dict(pool.map(lambda check:run(*check),checks))
        if meta.get('narrowed_feature_read_slot'):
            label,code=run('feature_read_equivalence',[sys.executable,
                str(ROOT/'tools/test_cnn_feature_read_address.py'),'--build',str(build),
                '--output',str(output/'feature_read_equivalence.json')])
            result['checks'][label]=code
        if meta.get('registered_pixel_ready'):
            label,code=run('pixel_skid_protocol',[sys.executable,
                str(ROOT/'tools/test_cnn_pixel_skid.py'),'--source',str(build/'Prj1/src/video/feedback_pixel_skid.v'),
                '--output',str(output/'pixel_skid_protocol.json')])
            result['checks'][label]=code
            command=[sys.executable,str(ROOT/'tools/test_cnn_renderer_predecode.py'),
                '--pixel-skid','--analysis-page','--build',str(build),'--output',str(output/'pixel_skid_full_renderer.json')]
            for key,flag in [('predecoded_text_coordinates','--text-coordinates'),
                    ('parallel_dashboard_cards','--parallel-cards'),('predecoded_background_coordinates','--background-coordinates'),
                    ('predecoded_wave_heights','--wave-heights'),('complete_background_coordinates','--complete-background-coordinates'),('predecoded_dynamic_background_ink','--dynamic-background-ink'),('parallel_renderer_spectrum_address','--parallel-spectrum-address'),('shallow_card_select','--shallow-card-select'),('quiet_shared_analysis_column','--quiet-shared-analysis'),('registered_renderer_first_issue','--first-issue-token')]:
                if meta.get(key):command.append(flag)
            label,code=run('pixel_skid_full_renderer',command)
            result['checks'][label]=code
        if meta.get('registered_renderer_first_issue'):
            label,code=run('renderer_dimension_guard',[sys.executable,
                str(ROOT/'tools/test_cnn_renderer_dimensions.py'),'--build',str(build),
                '--output',str(output/'renderer_dimension_guard.json')])
            result['checks'][label]=code
        if meta.get('predecoded_dashboard'):
            label,code=run('shared_display_integration',[sys.executable,
                str(ROOT/'tools/test_cnn_shared_display.py'),'--build',str(build),
                '--output',str(output/'shared_display_integration.json')])
            result['checks'][label]=code
        if meta.get('buffered_ddr_clients'):
            command=[sys.executable,str(ROOT/'tools/test_cnn_ddr_arbiter_pipeline.py'),
                '--build',str(build),'--buffered-clients','--output',str(output/'ddr_native_scoreboard.json')]
            if meta.get('registered_arbiter_tag_flags'):command.append('--registered-tag-flags')
            if meta.get('idle_client_payload_sampling'):command.append('--sample-idle-client-payload')
            label,code=run('ddr_native_scoreboard',command)
            result['checks'][label]=code
        if meta.get('idle_client_payload_sampling'):
            # This changes a model-side client queue. Require a newly executed
            # full-content pipeline test, not an unchanged-source composition.
            proof=json.loads((build/'frozen_full_model_pipeline.json').read_text())
            assert proof['passed'] and not proof['small_model_only'] and Path(proof['frozen_build']).resolve()==build,'missing executed full-model evidence'
            assert any(case['words']==52239 and case['payload_crc32']=='AF01A61B' and case['passed'] for case in proof['cases']),'full model word count/CRC not proved'
            assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest for path,digest in proof['source_sha256'].items()),'executed model source drift'
            result['executed_full_model_proof']=str(build/'frozen_full_model_pipeline.json')
            label,code=run('idle_client_payload_induction',[sys.executable,
                str(ROOT/'tools/test_cnn_idle_client_payload.py'),'--build',str(build),
                '--output',str(output/'idle_client_payload_induction.json')])
            result['checks'][label]=code
        if meta.get('parallel_tf_byte_counters'):
            protocol_flags=['--parallel-byte-counters']
            if meta.get('buffered_ddr_clients') and meta.get('retimed_tf_buffer_enable'):protocol_flags.append('--full-buffered-topology')
            if meta.get('retimed_tf_read_total'):protocol_flags.append('--retime-read-total')
            if meta.get('fast_tf_read_availability'):protocol_flags.append('--fast-read-availability')
            if meta.get('masked_tf_write_epoch'):protocol_flags.append('--mask-write-epoch')
            if meta.get('registered_tf_response'):protocol_flags.append('--registered-response')
            if meta.get('pipelined_tf_read_return'):protocol_flags.append('--pipeline-read-return')
            if meta.get('nibble_tf_byte_counters'):protocol_flags.append('--nibble-counters')
            for label,tool,flags in [('tf_byte_count_proof','test_cnn_tf_byte_count.py',[]),
                    ('tf_byte_count_protocol','test_cnn_tf_write_buffer_retime.py',protocol_flags)]:
                label,code=run(label,[sys.executable,str(ROOT/'tools'/tool),'--build',str(build),
                    '--output',str(output/(label+'.json'))]+flags)
                result['checks'][label]=code
        for key,label,tool in [('retimed_tf_read_total','tf_read_total_proof','test_cnn_tf_read_total.py'),
                ('parallel_renderer_spectrum_address','spectrum_address_proof','test_cnn_renderer_spectrum_address.py'),
                ('shallow_card_select','card_select_proof','test_cnn_card_select.py'),
                ('fast_tf_read_availability','tf_availability_proof','test_cnn_tf_read_availability.py'),
                ('masked_tf_write_epoch','tf_write_mask_equivalence','test_cnn_tf_write_mask.py')]:
            if meta.get(key):
                label,code=run(label,[sys.executable,str(ROOT/'tools'/tool),'--build',str(build),
                    '--output',str(output/(label+'.json'))])
                result['checks'][label]=code
        if meta.get('retimed_bist_expected_pattern'):
            label='bist_pipeline_protocol' if meta.get('pipelined_bist_compare') else 'bist_pattern_cycle_equivalence'
            tool='test_cnn_bist_pipeline.py' if meta.get('pipelined_bist_compare') else 'test_cnn_bist_expected_pattern.py'
            label,code=run(label,[sys.executable,str(ROOT/'tools'/tool),'--build',str(build),
                '--output',str(output/(label+'.json'))])
            result['checks'][label]=code
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
