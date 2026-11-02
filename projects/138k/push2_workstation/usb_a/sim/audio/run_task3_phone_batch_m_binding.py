#!/usr/bin/env python3
"""M batch board/parameter/APB reset seam, with explicit non-DSP cuts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CONTROLLED = 'rtl/workstation/workstation_runtime_controlled.sv'
AUDIO = 'rtl/workstation/workstation_runtime_audio.sv'
BOARD = 'rtl/workstation/workstation_task3_m_paired_board.svh'
BENCH = 'sim/audio/tb_task3_phone_batch_m_binding.sv'
SOURCES = (CONTROLLED, AUDIO, 'rtl/audio/workstation_ae350_pcm_owner.sv',
    'rtl/audio/workstation_ae350_pcm_session.sv',
    'rtl/workstation/workstation_task3_m_bus_endpoint.sv',
    'rtl/workstation/workstation_task3_phone_batch_m.sv',
    'rtl/workstation/workstation_task3_phone_window_rx.sv',
    'rtl/workstation/workstation_task3_phone_command_ingress.sv',
    'rtl/workstation/workstation_task3_phone_command_mux.sv',
    'rtl/workstation/workstation_task3_final_tap_export.sv',
    'rtl/workstation/workstation_task3_pcm_block_tx.sv',
    'rtl/music/workstation_task3_tf_analysis_source.sv',
    'rtl/music/workstation_task3_score_commit_m.sv', BENCH)
MUTANTS = (
    ('controlled_drops_snapshot', CONTROLLED, '.PCM_SNAPSHOT_ENABLE(PCM_SNAPSHOT_ENABLE)', '.PCM_SNAPSHOT_ENABLE(0)', True),
    ('audio_drops_snapshot', AUDIO, '.SNAPSHOT_ENABLE(PCM_SNAPSHOT_ENABLE)', '.SNAPSHOT_ENABLE(0)', True),
    ('batch_keeps_stale_COMPLETE', BOARD,
     '.reset_n(runtime_common_reset_n && (!TASK3_PHONE_BATCH || task3_m_phone_live))', '.reset_n(runtime_common_reset_n)', True),
    ('legacy_reset_policy_changes', BOARD,
     '.reset_n(runtime_common_reset_n && (!TASK3_PHONE_BATCH || task3_m_phone_live))', '.reset_n(runtime_common_reset_n && task3_m_phone_live)', False),
    ('endpoint_batch_disabled', BOARD, '.PHONE_BATCH(TASK3_PHONE_BATCH)', '.PHONE_BATCH(0)', True),
    ('owner_root_tracks_observer', AUDIO,
     '.reset_ni(compute_reset_n),.cpu_ready_i(pcm_cpu_ready_i)',
     '.reset_ni(compute_reset_n && pcm_cpu_ready_i),.cpu_ready_i(pcm_cpu_ready_i)', True))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='explicit prepared paired M Prj1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    if output.is_relative_to(ROOT.parents[3]) or output.is_relative_to(project):
        raise ValueError('evidence must remain outside the source and prepared candidate')
    output.mkdir(parents=True, exist_ok=False)
    stage = output/'inputs'
    report = dict(schema=1, passed=False, validation_stage='offline_M_board_command_seam',
        hardware_tested=False, physical_CDC_accepted=False, routed_timing_verified=False,
        real_controlled_audio_owner=True, real_board_include=True, real_APB_CDC=True,
        full_DSP_clock_display_closure=False, endpoint_protocol_exercised=False,
        fixture_cuts=['endpoint lease/command and HCI outputs overridden by deterministic fixture',
                      'physical context qualification, rate, epoch and sample_take are fixed owner input fixtures',
                      'iverilog -i leaves unrelated DSP, PLL, display and CPU-service children unelaborated'],
        invocations=[], mutations=[], source_negative_controls=[], default_off=[], error=None)
    tracked = {}
    try:
        sys.path.insert(0, str(ROOT))
        from tools import workstation_task3_m_paired_profile as policy
        pending = list(SOURCES)+[BOARD, policy.BATCH_PROVIDER, policy.PROVIDER,
            policy.PHONE_WINDOW_PROVIDER, policy.REFERENCE,
            'tools/workstation_task3_m_paired_profile.py',
            'rtl/workstation/TASK3_PHONE_BATCH_CONTRACT.md',
            str(Path(__file__).resolve().relative_to(ROOT))]
        # Snapshot literal include closure only, not a copy of the full project.
        # The selected top is the exact frozen prepared paired composition.
        top_relative = 'rtl/workstation/gw138k_push_workstation_top.v'
        pending.append(top_relative)
        while pending:
            relative = pending.pop()
            if relative in tracked:continue
            source = project/relative if relative==top_relative or not (ROOT/relative).is_file() else ROOT/relative
            data = source.read_bytes();target = stage/relative
            target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(data)
            tracked[relative] = dict(source=str(source), sha256=sha(source))
            if target.suffix in ('.sv', '.svh', '.v', '.vh'):
                pending.extend(re.findall(r'^\s*`include\s+"([^"]+)"', data.decode(), re.M))
        apb_policy = ROOT/'tools/workstation_ae350_pcm_cdc_policy.json'
        reviewed = json.loads(apb_policy.read_text())
        cdc_relative = reviewed['prepared_APB_source']
        if sha(project/cdc_relative)!=reviewed['prepared_APB_sha256']:
            raise ValueError('prepared APB differs from reviewed lock')
        prepared = []
        for relative in (cdc_relative, 'src/migration/gw138k_stream_cdc.sv'):
            dest = stage/relative;dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project/relative, dest);prepared.append(relative)
            tracked[relative] = dict(source=str(project/relative), sha256=sha(dest))
        tracked['reviewed_APB_policy'] = dict(source=str(apb_policy), sha256=sha(apb_policy))
        report['inputs'] = tracked

        def invoke(name, argv):
            result = subprocess.run(argv, cwd=stage, capture_output=True, text=True, timeout=60)
            log = output/(name+'.log');log.write_text(result.stdout+result.stderr)
            report['invocations'].append(dict(argv=argv, returncode=result.returncode, log=str(log), log_sha256=sha(log)))
            return result

        # Icarus rejects legal same-scope declarations used before their text.
        # Move only this exact declaration pair; all SV tokens remain identical.
        decl=('    wire observed_valid,observed_rate,observed_error,observed_change,observed_gap,observation_loss;\n'
              '    wire [31:0] observed_epoch,observed_sequence,observed_pcm,observation_source_drop;\n')
        text=(stage/CONTROLLED).read_text();anchor='    workstation_runtime_audio #(\n'
        if text.count(decl)!=1 or text.count(anchor)!=1:raise ValueError('Icarus declaration move anchor drift')
        adapted=text.replace(decl,'').replace(anchor,decl+anchor)
        if Counter(re.findall(r'\S+',text))!=Counter(re.findall(r'\S+',adapted)):
            raise ValueError('declaration adaptation changes tokens')
        original=(stage/CONTROLLED).read_bytes()
        (stage/CONTROLLED).write_text(adapted)
        report['Icarus_adaptation']=dict(source=CONTROLLED, before_sha256=hashlib.sha256(original).hexdigest(),
            after_sha256=sha(stage/CONTROLLED), only_same_scope_declaration_reorder=True)

        def exercise(label, batch, expected_pass):
            binary=output/(label+'.vvp')
            argv=['iverilog','-i','-g2012','-I.','-DWORKSTATION_TASK3_PHONE_WINDOW_BLOCK']
            if batch:argv.append('-DWORKSTATION_TASK3_PHONE_BATCH')
            result=invoke(label+'_compile', argv+['-s','tb_task3_phone_batch_m_binding','-o',str(binary),*SOURCES,*prepared])
            if result.returncode:raise ValueError('binding compilation failed: '+label)
            result=invoke(label+'_run',['vvp',str(binary)])
            match=re.search(r'PASS phone batch M binding batch=(\d+) checks=(\d+)',result.stdout)
            passed=result.returncode==0 and match is not None
            if passed!=expected_pass:raise ValueError('unexpected binding result: '+label)
            return int(match[2]) if passed else 0

        checks={label:exercise(label,batch,True) for label,batch in [('legacy_window',False),('new_batch',True)]}
        for name,relative,old,new,batch in MUTANTS:
            text=(stage/relative).read_text()
            if text.count(old)!=1:raise ValueError('mutation anchor drift: '+name)
            (stage/relative).write_text(text.replace(old,new))
            try:exercise(name,batch,False)
            finally:(stage/relative).write_text(text)
            report['mutations'].append(dict(name=name, rejected=True))
        (stage/CONTROLLED).write_bytes(original)
        config=dict(interboard_media_policy=policy.BATCH_MEDIA_POLICY,phone_batch_policy=policy.BATCH_POLICY)
        report['selected_batch_source_evidence']=policy.selected_batch_source_evidence(ROOT,stage,config,policy.BATCH_PROVIDER)
        if policy.selected_batch_source_evidence(ROOT,stage,{},policy.PROVIDER) is not None:
            raise ValueError('legacy provider implicitly selects batch')
        # Feed matching source/stage mutants to the source gate so failures
        # exercise its actual binding rules rather than only the hash compare.
        source_mutants=[(name,relative,old,new) for name,relative,old,new,_ in MUTANTS]
        source_mutants += [
            ('provider_macro_scope',policy.BATCH_PROVIDER,'`undef WORKSTATION_TASK3_PHONE_BATCH',''),
            ('missing_window_prerequisite',policy.PHONE_WINDOW_PROVIDER,'`define WORKSTATION_TASK3_PHONE_WINDOW_BLOCK',''),
            ('wrong_defparam_target',BOARD,'defparam u_managed.PCM_SNAPSHOT_ENABLE','defparam u_managed.ENABLE_AE350_PCM'),
            ('capture_ID_cleared_on_observer_reset','rtl/audio/workstation_ae350_pcm_owner.sv',
             'end else if(!cpu_ready_i)begin\n                valid<=0;',
             'end else if(!cpu_ready_i)begin\n                capture_id<=0;valid<=0;')]
        for name,relative,old,new in source_mutants:
            text=(stage/relative).read_text()
            if text.count(old)!=1:raise ValueError('source negative-control anchor drift: '+name)
            (stage/relative).write_text(text.replace(old,new))
            try:
                try:policy.selected_batch_source_evidence(stage,stage,config,policy.BATCH_PROVIDER)
                except ValueError as error:reason=str(error)
                else:raise ValueError('source gate accepted mutation: '+name)
            finally:(stage/relative).write_text(text)
            report['source_negative_controls'].append(dict(name=name,rejected=True,reason=reason))
        for name,configuration,provider in [
            ('batch_policy_without_provider',config,policy.PROVIDER),
            ('provider_without_policies',{},policy.BATCH_PROVIDER),
            ('wrong_media_policy',dict(config,interboard_media_policy='unreviewed'),policy.BATCH_PROVIDER),
            ('wrong_batch_policy',dict(config,phone_batch_policy='unreviewed'),policy.BATCH_PROVIDER)]:
            try:policy.selected_batch_source_evidence(ROOT,stage,configuration,provider)
            except ValueError as error:reason=str(error)
            else:raise ValueError('source gate accepted policy mismatch: '+name)
            report['source_negative_controls'].append(dict(name=name,rejected=True,reason=reason))
        for label,provider,batch in [('legacy',policy.PROVIDER,False),('window',policy.PHONE_WINDOW_PROVIDER,False),('batch',policy.BATCH_PROVIDER,True)]:
            probe=stage/(label+'_macro_scope.sv')
            probe.write_text('`include "'+provider+'"\n'+''.join(
                '`ifdef '+m+'\nTASK3_MACRO_LEAK\n`endif\n' for m in ('WORKSTATION_TASK3_PHONE_BATCH','WORKSTATION_TASK3_PHONE_WINDOW_BLOCK','WORKSTATION_TASK3_M_PAIRED')))
            result=invoke(label+'_preprocess',['iverilog','-g2012','-E','-I.','-o','-',str(probe)])
            if result.returncode or 'TASK3_MACRO_LEAK' in result.stdout:
                raise ValueError('provider preprocessing/macro scope failed: '+label)
            has_snapshot="defparamu_managed.PCM_SNAPSHOT_ENABLE=1'b1;" in ''.join(result.stdout.split())
            if has_snapshot!=batch:raise ValueError('default-off snapshot selection failed: '+label)
            report['default_off'].append(dict(provider=provider,batch_selected=batch,macro_leak=False))
        report['checks']=checks
        report['source_unchanged']=all(sha(Path(v['source']))==v['sha256'] for v in tracked.values())
        report['passed']=report['source_unchanged'] and checks['new_batch']>=40 and checks['legacy_window']>=30
        if not report['passed']:raise ValueError('binding coverage or input invariance shortfall')
    except Exception as error:
        report['error']=str(error)
    receipt=output/'verification.json';receipt.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],error=report['error'],verification=str(receipt))))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
