#!/usr/bin/env python3
"""Unselected Delay Reporting source proof + complete preceding Classic/SBC regressions."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,sys

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
MUTANTS=(
 ('basic-capability-leak','if (DELAY_REPORTING_SUPPORTED && (signal==12u || (signal==4u && s->delay_selected)))','if (DELAY_REPORTING_SUPPORTED && (signal==2u || signal==12u || (signal==4u && s->delay_selected)))'),
 ('missing-all-capability','if (DELAY_REPORTING_SUPPORTED && (signal==12u || (signal==4u && s->delay_selected)))','if (DELAY_REPORTING_SUPPORTED && signal==4u && s->delay_selected)'),
 ('local-seid-used','p[2]=s->remote_seid;','p[2]=SEP;'),
 ('delay-byte-order','putbe(p+3,s->delay_value);','putle(p+3,s->delay_value);'),
 ('clock-gate-removed','if (!s->clock_valid || !s->delay_valid)','if (0)'),
 ('no-initial-report','s->delay_phase=s->delay_selected ? A138_CLASSIC_DELAY_QUEUED : A138_CLASSIC_DELAY_NONE;','s->delay_phase=A138_CLASSIC_DELAY_NONE;'),
 ('early-complete-at-tx','s->delay_phase=A138_CLASSIC_DELAY_WAIT; s->delay_started_ms=s->clock_ms;','s->delay_phase=A138_CLASSIC_DELAY_COMPLETE; s->delay_started_ms=s->clock_ms;'),
 ('wrong-label-accepted','s->delay_phase!=A138_CLASSIC_DELAY_WAIT || label!=s->delay_label','s->delay_phase!=A138_CLASSIC_DELAY_WAIT'),
 ('wrong-opcode-accepted','if (signal!=13u) return delay_fail(s,A138_CLASSIC_DELAY_BAD_RESPONSE);','if (0) return delay_fail(s,A138_CLASSIC_DELAY_BAD_RESPONSE);'),
 ('reject-accepted','return delay_fail(s,A138_CLASSIC_DELAY_REJECTED);','s->delay_phase=A138_CLASSIC_DELAY_COMPLETE; return A138_CLASSIC_OK;'),
 ('bad-accept-length','if (message_type!=2u || n)','if (message_type!=2u)'),
 ('wait-deadline-ignored','s->delay_phase==A138_CLASSIC_DELAY_TX || s->delay_phase==A138_CLASSIC_DELAY_WAIT','s->delay_phase==A138_CLASSIC_DELAY_TX'),
 ('tx-deadline-ignored','s->delay_phase==A138_CLASSIC_DELAY_TX || s->delay_phase==A138_CLASSIC_DELAY_WAIT','s->delay_phase==A138_CLASSIC_DELAY_WAIT'),
 ('clock-regression-ignored','if (s->clock_valid && (uint32_t)(now-s->clock_ms)>=0x80000000u)','if (0)'),
 ('label-wrap-allowed','if (s->delay_labels_used>=16u)','if (0)'),
 ('busy-value-overwritten','if (s->delay_selected && (s->tx_bytes || s->rx_complete || s->delay_phase!=A138_CLASSIC_DELAY_COMPLETE))','if (0)'),
 ('start-before-peer-accept','(!s->delay_selected || s->delay_phase==A138_CLASSIC_DELAY_COMPLETE)','1'),
 ('fragment-message-type-ignored',' || s->avdtp_message_type!=message_type',''),
)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--riscv-prefix',default='/opt/homebrew/bin/riscv64-elf');a=p.parse_args()
 u=Path(__file__).resolve().parents[1];repo=u.parents[3];fw=u/'firmware/ae350';out=a.output.resolve()
 if out==repo or repo in out.parents:p.error('evidence must be outside repository')
 out.mkdir(parents=True,exist_ok=False)
 commands=[]
 def run(argv,name,ok=True):
  r=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=300)
  (out/(name+'.log')).write_text(r.stdout+r.stderr);commands.append({'argv':list(map(str,argv)),'returncode':r.returncode})
  if ok and r.returncode:raise RuntimeError((name,r.returncode,r.stdout,r.stderr))
  return r
 source=fw/'classic_service.c';fixture=u/'sim/ae350_delay_fixture.c';cc=Path(shutil.which('cc')).resolve()
 selected=[source,fw/'classic_service.h',fixture,u/'sim/ae350_classic_fixture.c',Path(__file__).resolve(),u/'sim/run_ae350_classic_service.py']
 before={str(x.relative_to(u)):sha(x)for x in selected}
 common=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(fw)]
 baseline={}
 for tag,flags in(('native',[]),('sanitized',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])):
  run([*common,*flags,source,fixture,'-o',out/tag],tag+'-compile');r=run([out/tag],tag+'-run')
  if 'runtime error:'in r.stderr or 'Sanitizer'in r.stderr:raise RuntimeError('sanitizer finding')
  match=re.search(r'delay reporting source-stage: (\d+) checks passed',r.stdout)
  if not match:raise RuntimeError('missing actual fixture success')
  baseline[tag]={'checks':int(match[1]),'summary':r.stdout.strip()}
 text=source.read_text();mutants={}
 for name,old,new in MUTANTS:
  if text.count(old)!=1:raise RuntimeError('mutation anchor drift: '+name)
  m=out/(name+'.c');m.write_text(text.replace(old,new));exe=out/name
  run([*common,'-Wno-unused-parameter','-Wno-unused-but-set-variable',m,fixture,'-o',exe],name+'-compile')
  r=run([exe],name+'-run',False)
  if not r.returncode or 'check 'not in r.stderr:raise RuntimeError('mutant survived or did not reach assertion: '+name)
  mutants[name]={'rejected':True,'source_sha256':sha(m),'failure':r.stderr.strip()}
 run([sys.executable,'-B',u/'sim/run_ae350_classic_service.py','--output',out/'prior-classic','--riscv-prefix',a.riscv_prefix],'prior-classic')
 prior=json.loads((out/'prior-classic/verification.json').read_text())
 for n,h in before.items():
  if sha(u/n)!=h:raise RuntimeError('source drift during verification: '+n)
 for n,h in prior['inputs'].items():
  if sha(u/n)!=h:raise RuntimeError('prior source drift: '+n)
 inputs={**prior['inputs'],**before}
 report={'schema':'ae350-delay-reporting-source-stage-v1','selected_in_production':False,'hardware_tested':False,'actual_delay_measured':False,'connection_security_implemented':False,
 'inputs':inputs,'tools':prior['tool_identity'],'baseline':baseline,'mutants':mutants,'prior_wire':prior['wire_results'],'prior_mutants':len(prior['killed_behavioral_mutants']),
 'prior_decoder_cases':prior['actual_decoder_cases'],'rv32_budget':prior['rv32_budget'],'commands':commands}
 report['outputs']={str(f.relative_to(out)):sha(f)for f in sorted(out.rglob('*'))if f.is_file()}
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report[k]for k in('schema','baseline','prior_wire','prior_mutants','rv32_budget')},indent=2))
if __name__=='__main__':main()
