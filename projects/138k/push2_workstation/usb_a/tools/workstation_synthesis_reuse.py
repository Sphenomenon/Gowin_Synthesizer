"""Reuse exact paired-preboard synthesis only when every compiler input matches.

Audit/report changes can create a new sealed prepare without changing hardware.
The prior VG is never edited. A reuse receipt binds both immutable prepares,
all enabled files, the project and script, and every copied synthesis artifact.
"""
from pathlib import Path
import argparse,hashlib,json,shutil
from datetime import datetime,timezone


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def reuse(source,destination,*,audit_tool_only=False):
    from tools.workstation_task3_paired_audit import verify_prepared
    source,destination=Path(source).resolve(),Path(destination).resolve()
    sm=json.loads((source/'integration_inputs.json').read_text());dm=json.loads((destination/'integration_inputs.json').read_text())
    sr,sp,ss,_=verify_prepared(source,sm);dr,dp,ds,_=verify_prepared(destination,dm)
    if sr!=dr or any(p['profile']!='custom138k-workstation-task3-'+sr.lower()+'-preboard-v1'for p in [sp,dp]):
        raise ValueError('exact same explicit paired preboard role required')
    if (destination/'synthesis.log').exists()or(ds/'impl/gwsynthesis').exists():
        raise ValueError('destination already has synthesis evidence')
    # File order and complete enabled payload are compiler inputs, including
    # recursively consumed includes, firmware, memories and encrypted IP.
    if sm['enabled_inputs']!=dm['enabled_inputs']:
        raise ValueError('enabled compiler file inventory or order differs')
    names=set(sm['staged_input_sha256'])|set(dm['staged_input_sha256'])
    if set(sm['staged_input_sha256'])!=set(dm['staged_input_sha256']):
        raise ValueError('staged compiler closure inventory differs')
    different=[p for p in sorted(names)if sm['staged_input_sha256'][p]!=dm['staged_input_sha256'][p]]
    noncompiler={}
    if different:
        # These proof tools are staged for source review, not loaded by
        # Gowin. Keep default reuse strict; explicitly bind their old/new hashes
        # only after every project, script, HDL/include, memory and IP matches.
        reviewed={'tools/workstation_w_context_compare.py',
                  'tools/workstation_task3_receipt_audit.py',
                  # Reviewed mapped/startup proof updates after v35. These
                  # Python files are staged review inputs; the checks below
                  # still reject any compiler listing or source reference.
                  'tools/workstation_task3_native_held.py',
                  'tools/workstation_tf_compute_local_release.py',
                  'tools/workstation_tf_status_compare.py'}
        if not audit_tool_only or not set(different)<=reviewed:
            raise ValueError('staged compiler input bytes differ: '+repr(different))
        import xml.etree.ElementTree as ET
        listed={r.get('path')for r in ET.parse(ss/'Prj1.gprj').find('FileList')}
        for relative in different:
            if relative in listed or relative in sm['enabled_inputs']:
                raise ValueError('reviewed audit tool is a compiler input')
            for candidate,stage,meta in [(source,ss,sm),(destination,ds,dm)]:
                for name in meta['staged_input_sha256']:
                    if name.endswith(('.v','.sv','.vh','.svh','.tcl','.gprj')) and Path(relative).name.encode() in (stage/name).read_bytes():
                        raise ValueError('compiler source references audit tool: '+name)
            noncompiler[relative]=dict(source_sha256=sm['staged_input_sha256'][relative],
                destination_sha256=dm['staged_input_sha256'][relative],not_listed_or_referenced_by_compiler=True)
    if not (source/'synthesis.log').read_text().count('GowinSynthesis finish')==1:
        raise ValueError('source synthesis incomplete')
    old=ss/'impl/gwsynthesis';new=ds/'impl/gwsynthesis'
    files={str(p.relative_to(old)):sha(p)for p in old.rglob('*')if p.is_file()}
    if not files or not {'custom_138k_integration.vg','custom_138k_integration_syn_rsc.xml'}<=set(files):
        raise ValueError('source synthesis artifacts incomplete')
    receipt=dict(policy='exact_all_staged_compiler_bytes_reuse_v1'if not noncompiler else 'exact_compiler_bytes_explicit_noncompiler_proof_update_v1',
        reviewed_noncompiler_tool_changes=noncompiler,
        source=str(source),source_candidate=sp['candidate_identity'],destination_candidate=dp['candidate_identity'],
        prepared_at_utc=datetime.now(timezone.utc).isoformat(),source_integration_sha256=sha(source/'integration_inputs.json'),
        destination_integration_sha256=sha(destination/'integration_inputs.json'),
        all_staged_input_sha256=sm['staged_input_sha256'],enabled_inputs=sm['enabled_inputs'],
        synthesis_artifacts_sha256=files,source_log_sha256=sha(source/'synthesis.log'),
        tool_sha256=sha(__file__),fresh_synthesis_run=False,new_candidate_requires_fresh_audit=True,hardware_tested=False)
    new.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(old,new);shutil.copyfile(source/'synthesis.log',destination/'synthesis.log')
    if any(sha(new/p)!=h for p,h in files.items())or sha(destination/'synthesis.log')!=receipt['source_log_sha256']:
        raise ValueError('reused artifact changed during copy')
    (destination/'synthesis-reuse.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);p.add_argument('--audit-tool-only',action='store_true');a=p.parse_args()
    print(json.dumps(reuse(a.source,a.destination,audit_tool_only=a.audit_tool_only),indent=2))
