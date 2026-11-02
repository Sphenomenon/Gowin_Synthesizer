#!/usr/bin/env python3
"""Compare guarded macro-off W ELF/BIN/ROM against explicit frozen inputs.

This is an offline regression experiment. It does not relax an old production
source review or use reconstructed bytes as production compilation inputs.
The reference root must be supplied explicitly; no historical cache fallback.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_w_media_firmware as firmware
from tools import workstation_task3_w_paired_firmware as paired
from tools.stage_usb_firmware import compiler_prefix

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(output,legacy_root,prefix=None):
    output,legacy_root=Path(output).resolve(),Path(legacy_root).resolve()
    if output.is_relative_to(ROOT.parents[3]) or output.is_relative_to(legacy_root):
        raise ValueError('evidence must be outside repository and frozen reference root')
    if legacy_root==ROOT:raise ValueError('a separate explicit frozen source root is required')
    # The immutable old review must admit the frozen source bytes. The current
    # guarded source is independently reviewed by the new batch policy only.
    firmware.verify_sources(legacy_root)
    reviewed,_=firmware.verify_sources(ROOT,phone_batch=True)
    if sha(legacy_root/paired.PARENT_REVIEW)!=paired.PARENT_REVIEW_SHA256:
        raise ValueError('frozen reference review identity drift')
    before={rel:sha(ROOT/rel)for rel in reviewed['input_sha256']}
    paths=[p for folder in ('firmware/ae350','tools') for p in sorted((legacy_root/folder).rglob('*'))if p.is_file()]
    paths.append(legacy_root/'rtl/ddr_address_map.vh')
    reference_before={str(p.relative_to(legacy_root)):sha(p)for p in paths}
    output.mkdir(parents=True,exist_ok=False)
    baseline=output/'frozen_paired';macrooff=output/'guarded_macrooff'
    report=dict(schema='task3-phone-batch-disabled-real-ELF-v1',passed=False,
        legacy_root=str(legacy_root),legacy_inputs_sha256=reference_before,
        current_source_sha256=before,runner_sha256=sha(__file__),commands=[],
        old_production_source_review_relaxed=False,source_text_substitution_in_production=False,
        hardware_tested=False,ROM_capacity_bytes=131072)
    prefix=compiler_prefix(prefix)
    if not Path(prefix).is_absolute():prefix=str(Path(shutil.which(prefix+'-gcc')).resolve()).removesuffix('-gcc')

    def command(name,argv,cwd):
        result=subprocess.run(list(map(str,argv)),cwd=cwd,text=True,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        log=output/(name+'.log');log.write_text(result.stdout)
        report['commands'].append(dict(name=name,argv=list(map(str,argv)),
            returncode=result.returncode,log_sha256=sha(log)))
        if result.returncode:raise RuntimeError('firmware experiment failed: '+str(log))
        return result.stdout

    try:
        script=('from pathlib import Path; import sys; sys.path.insert(0,sys.argv[1]); '
            'from tools.workstation_task3_w_media_firmware import build; '
            'build(Path(sys.argv[2]),sys.argv[3],Path(sys.argv[1]),paired_source=True)')
        command('frozen-build',[sys.executable,'-c',script,legacy_root,baseline,prefix],legacy_root)
        old=json.loads((baseline/'verification.json').read_text())
        if not old['passed'] or old['policy']!=paired.POLICY:
            raise ValueError('frozen paired ELF did not pass its own original audit')
        macrooff.mkdir()
        for name in (*firmware.SOURCES,*firmware.HEADERS):
            source=ROOT/'firmware/ae350'/name
            target=macrooff/name
            if 'firmware/ae350/'+name==paired.SOURCE:target.write_text(paired.adapt(source.read_text()))
            else:shutil.copyfile(source,target)
        for name in ('stdlib.h','string.h'):shutil.copyfile(baseline/name,macrooff/name)
        shutil.copytree(baseline/'adapted',macrooff/'adapted')
        for row in old['commands']:
            argv=[arg.replace(str(baseline),str(macrooff))for arg in row['argv']]
            if any(arg.startswith('-DA138_TASK3_PHONE_BATCH')for arg in argv):
                raise ValueError('macro-off reference unexpectedly enables batch')
            text=command('macrooff-'+row['name'],argv,macrooff)
            saved={'size':'firmware.size','nm':'firmware.nm','objdump':'firmware.dis'}.get(row['name'])
            if saved:(macrooff/saved).write_text(text)
        raw=(macrooff/'firmware.bin').read_bytes()
        if len(raw)>131072:raise ValueError('macro-off ROM128 overflow')
        padded=raw.ljust(131072,b'\0')
        (macrooff/'boot.mem').write_text(''.join(f'{int.from_bytes(padded[i:i+4],"little"):08x}\n'for i in range(0,131072,4)))
        compared=['firmware.elf','firmware.bin','boot.mem',
            *(Path(name).stem+'.o'for name in old['compiled_sources'])]
        report['artifact_comparison']={name:dict(frozen_sha256=sha(baseline/name),
            guarded_sha256=sha(macrooff/name),identical=(baseline/name).read_bytes()==(macrooff/name).read_bytes())for name in compared}
        if not all(row['identical']for row in report['artifact_comparison'].values()):
            raise ValueError('disabled batch changed actual ELF/BIN/ROM or TU objects')
        report['current_sources_unchanged']=before=={rel:sha(ROOT/rel)for rel in before}
        report['legacy_sources_unchanged']=reference_before=={str(p.relative_to(legacy_root)):sha(p)for p in paths}
        if not report['current_sources_unchanged'] or not report['legacy_sources_unchanged']:
            raise ValueError('firmware experiment sources changed during verification')
        report.update(passed=True,old_review_sha256=paired.PARENT_REVIEW_SHA256,
            frozen_audit_sha256=sha(baseline/'media_callgraph_verification.json'),
            frozen_capacity=old['capacity'],conservative_stack_bytes=old['conservative_stack_bytes'],
            every_TU_object_identical=True,ELF_BIN_ROM_identical=True,
            baseline_sources_compiled_as_frozen=True,macrooff_sources_compiled_as_current=True)
    finally:(output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],verification=str(output/'verification.json'))))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--legacy-root',type=Path,required=True)
    parser.add_argument('--riscv-prefix')
    args=parser.parse_args()
    run(args.output,args.legacy_root,args.riscv_prefix)
