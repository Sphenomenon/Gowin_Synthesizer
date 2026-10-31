#!/usr/bin/env python3
"""Unselected real security-command/event -> Classic gate proof; no board/Flash."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,sys

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

MUTANTS=(
 ('local-ssp-unchecked','security','if(n!=14u||!(p[12]&8u)||!(p[13]&128u))','if(n!=14u)'),
 ('host-ssp-unchecked','security','if(n!=16u||p[6]!=1u||p[7]<1u||!(p[8]&1u)||(p[8]&8u))','if(n!=16u)'),
 ('auth-status-is-success','security','case C_SIZE:\n        if(n!=9u','case C_AUTH:s->auth_done=1;break;\n    case C_SIZE:\n        if(n!=9u'),
 ('encryption-status-is-success','security','case C_SIZE:\n        if(n!=9u','case C_ENCRYPT:s->encrypted=1;break;\n    case C_SIZE:\n        if(n!=9u'),
 ('short-key-allowed','security','p[8]<7u||p[8]>16u','p[8]>16u'),
 ('negotiated-size-downgrade','security','((s->bond.revision||s->session_only)&&p[8]<s->bond.minimum_size)','0'),
 ('persist-failure-ignored','security','if(br!=A138_BOND_OK){wipe(&b,sizeof b);return fence(s,F_STORAGE);}','if(0){wipe(&b,sizeof b);return fence(s,F_STORAGE);}'),
 ('persist-busy-is-success','security','if(br==A138_BOND_BUSY){wipe(&b,sizeof b);','if(0){wipe(&b,sizeof b);'),
 ('stale-generation-event-accepted','security','else if(g!=s->generation)return stale(s);','else if(0)return stale(s);'),
 ('inactive-peer-event-replied','security','if(!s->active){if(g!=0u)return stale(s);}','if(!s->active){if(0)return stale(s);}'),
 ('bond-peer-unchecked','security','b->revision!=0u&&same(b->peer,peer)','b->revision!=0u'),
 ('new-key-type-unchecked','security','!s->remote_io_seen||p[24]!=4u||','!s->remote_io_seen||'),
 ('duplicate-key-replaced','security','if(s->bond.type!=p[24]||memcmp(s->bond.key,p+8,16)!=0)close_link(s,0x05);','if(0)close_link(s,0x05);'),
 ('transport-retirement-ignored','security','if(c->accepted&&c->transport_done&&c->response_done)','if(c->accepted&&c->response_done)'),
 ('command-owner-unchecked','security','if(owner!=2u)return A138_SECURITY_STALE;','if(0)return A138_SECURITY_STALE;'),
 ('accept-before-send','security','!s->request_pending||!s->accept_sent||','!s->request_pending||'),
 ('no-physical-deadline','security','if(s->count&&(uint32_t)(now-s->queue[s->head].started_ms)>=A138_SECURITY_COMMAND_MS)','if(0)'),
 ('no-observer-fence','security','void a138_security_observer_reset(struct a138_security *s){if(s&&s->started)(void)fence(s,F_UNCERTAIN);}','void a138_security_observer_reset(struct a138_security *s){(void)s;}'),
 ('missing-revocation','security','if(s->active)(void)a138_classic_security(s->classic,s->generation,s->generation,0);','if(0)(void)a138_classic_security(s->classic,s->generation,s->generation,0);'),
 ('disconnect-reason-is-status','security','s->close_reason=why==0x13u?0x13u:0x05u;','s->close_reason=why;'),
 ('interrupted-new-key-retained','security','s->io_pending=0;s->new_key=0;s->key_used=0;s->key_loaded=0;','s->io_pending=0;s->key_used=0;s->key_loaded=0;'),
 ('io-reply-deadline-ignored','security','if(s->io_pending&&(uint32_t)(now-s->io_started_ms)>=A138_SECURITY_COMMAND_MS)','if(0)'),
 ('inactive-acl-reopens-close','security','if(!s->active||e!=s->epoch||g!=s->generation)return A138_CLASSIC_STALE;','if(e!=s->epoch||g!=s->generation)return A138_CLASSIC_STALE;'),
 ('inactive-close-resurrected','security','if(!s->active)return;\n    revoke(s);','revoke(s);'),
 ('avdtp-gate-removed','classic','if(!s->security_ready){result=3;s->security_violation=1;}','if(0){result=3;s->security_violation=1;}'),
 ('session-io-bonds','security','b[8]=s->session_only?0:4;','b[8]=4;'),
 ('session-deferred-io-bonds','security','p[8]=s->session_only?0:4;','p[8]=4;'),
 ('session-key-retained','security','wipe(s->bond.key,sizeof s->bond.key);s->new_key=0;','s->new_key=0;'),
 ('session-observer-key-retained','security','if(s->session_only)wipe(s->bond.key,sizeof s->bond.key);','if(0)wipe(s->bond.key,sizeof s->bond.key);'),
)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--riscv-prefix',default='/opt/homebrew/bin/riscv64-elf');a=p.parse_args()
 u=Path(__file__).resolve().parents[1];repo=u.parents[3];fw=u/'firmware/ae350';out=a.output.resolve()
 if out==repo or repo in out.parents:p.error('evidence must be outside repository')
 out.mkdir(parents=True,exist_ok=False);commands=[]
 def run(argv,name,ok=True):
  r=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=300)
  (out/(name+'.log')).write_text(r.stdout+r.stderr);commands.append(dict(argv=list(map(str,argv)),returncode=r.returncode))
  if ok and r.returncode:raise RuntimeError((name,r.returncode,r.stdout,r.stderr))
  return r
 security=fw/'classic_security.c';classic=fw/'classic_service.c';fixture=u/'sim/ae350_security_fixture.c';cc=Path(shutil.which('cc')).resolve()
 selected=[security,fw/'classic_security.h',classic,fw/'classic_service.h',fixture,Path(__file__).resolve()]
 before={str(x.relative_to(u)):sha(x)for x in selected}
 common=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(fw)];baseline={}
 for tag,flags in(('native',[]),('sanitized',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])):
  run([*common,*flags,security,classic,fixture,'-o',out/tag],tag+'-compile');r=run([out/tag],tag+'-run')
  if 'runtime error:'in r.stderr or 'Sanitizer'in r.stderr:raise RuntimeError('sanitizer finding')
  match=re.search(r'classic security source-stage: (\d+) checks passed',r.stdout)
  if not match:raise RuntimeError('missing actual fixture success')
  baseline[tag]=dict(checks=int(match[1]),valid_envelope_fuzz_cases=4000,summary=r.stdout.strip())
 session_only_baseline={}
 for tag,flags in(('native',[]),('sanitized',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])):
  name='worker-session-'+tag
  run([*common,*flags,'-DA138_SINGLE_BLE_RECORDING','-Wno-unused-function',security,classic,fixture,'-o',out/name],name+'-compile')
  r=run([out/name],name+'-run')
  if 'runtime error:'in r.stderr or 'Sanitizer'in r.stderr:raise RuntimeError('session sanitizer finding')
  match=re.search(r'classic security source-stage: (\d+) checks passed',r.stdout);assert match
  session_only_baseline[tag]=dict(checks=int(match[1]),summary=r.stdout.strip(),persistent_store_calls=0)
 texts=dict(security=security.read_text(),classic=classic.read_text());mutants={}
 for name,which,old,new in MUTANTS:
  text=texts[which]
  if text.count(old)!=1:raise RuntimeError('mutation anchor drift: '+name)
  m=out/(name+'.c');m.write_text(text.replace(old,new));exe=out/name
  sources=[m,classic]if which=='security'else[security,m]
  run([*common,'-Wno-unused-parameter','-Wno-unused-but-set-variable',*sources,fixture,'-o',exe],name+'-compile')
  r=run([exe],name+'-run',False)
  if not r.returncode or 'check 'not in r.stderr:raise RuntimeError('mutant survived or did not reach assertion: '+name)
  mutants[name]=dict(rejected=True,source_sha256=sha(m),failure=r.stderr.strip())
 # The retired-generation early return and the inactive-close guard overlap.
 # Removing only the former is deliberately expected to pass; do not count a
 # masked single deletion as a killed behavioral mutant. Removing both must
 # reproduce the actual historical late-failure/reconnect regression.
 early='if(c->generation&&(!s->active||c->generation!=s->generation)){retire(s);return A138_SECURITY_OK;}'
 inactive='if(!s->active)return;\n    revoke(s);'
 if texts['security'].count(early)!=1 or texts['security'].count(inactive)!=1:raise RuntimeError('overlapping guard anchor drift')
 masked_text=texts['security'].replace(early,'if(0){retire(s);return A138_SECURITY_OK;}')
 masked=out/'masked-retired-generation.c';masked.write_text(masked_text)
 run([*common,masked,classic,fixture,'-o',out/'masked-retired-generation'],'masked-retired-generation-compile')
 r=run([out/'masked-retired-generation'],'masked-retired-generation-run')
 if baseline['native']['summary']!=r.stdout.strip():raise RuntimeError('masked control changed actual fixture coverage')
 controls={'retired-generation-single-deletion':dict(expected_pass=True,passed=True,source_sha256=sha(masked),masking_guard='close_link refuses inactive contexts',summary=r.stdout.strip())}
 name='late-failure-double-missing';m=out/(name+'.c');m.write_text(masked_text.replace(inactive,'revoke(s);'))
 run([*common,m,classic,fixture,'-o',out/name],name+'-compile');r=run([out/name],name+'-run',False)
 if not r.returncode or 'check 'not in r.stderr:raise RuntimeError('historical double-missing mutant survived')
 mutants[name]=dict(rejected=True,source_sha256=sha(m),failure=r.stderr.strip(),scope='both retired-generation early return and inactive-close guard removed')
 run([sys.executable,'-B',u/'sim/run_ae350_delay_reporting.py','--output',out/'prior-delay','--riscv-prefix',a.riscv_prefix],'prior-delay')
 prior=json.loads((out/'prior-delay/verification.json').read_text())
 include=out/'rv32-include';include.mkdir();(include/'string.h').write_text('#include <stddef.h>\nvoid *memset(void *,int,size_t);\nvoid *memcpy(void *,const void *,size_t);\nint memcmp(const void *,const void *,size_t);\n')
 flags=['-march=rv32im_zicsr_zifencei','-mabi=ilp32','-msmall-data-limit=0','-O2','-ffreestanding','-Wall','-Wextra','-Werror','-fno-builtin','-fstack-usage','-fcallgraph-info=su','-I'+str(fw),'-I'+str(include)]
 obj=out/'classic_security.o';run([a.riscv_prefix+'-gcc',*flags,'-c',security,'-o',obj],'rv32-security-compile')
 size=run([a.riscv_prefix+'-size','-A',obj],'rv32-security-size').stdout
 symbols=run([a.riscv_prefix+'-nm','-u',obj],'rv32-security-undefined').stdout
 budget_source=out/'security_objects.c';budget_source.write_text('#include "classic_security.h"\nstruct a138_security owner;\nstruct a138_security_command command;\nstruct a138_bond bond;\n')
 run([a.riscv_prefix+'-gcc',*flags,'-c',budget_source,'-o',out/'security_objects.o'],'rv32-security-object-compile')
 objects=run([a.riscv_prefix+'-nm','-S',out/'security_objects.o'],'rv32-security-object-size').stdout
 sections={m[1]:int(m[2])for m in re.finditer(r'^(\.\S+)\s+(\d+)\s+',size,re.M)}
 frames=[dict(function=line.split('\t')[0].split(':')[-1],bytes=int(line.split('\t')[1]),kind=line.split('\t')[2])for line in(out/'classic_security.su').read_text().splitlines()]
 budget=dict(sections=sections,text_rodata_bytes=sum(v for k,v in sections.items()if k.startswith(('.text','.rodata'))),
  objects={name:int(count,16)for count,name in re.findall(r'\b([0-9a-f]+) B (owner|command|bond)\b',objects)},
  maximum_function_frame=max(x['bytes']for x in frames),function_frames=frames,undefined_symbols=[line.split()[-1]for line in symbols.splitlines()],
  scope='Incremental RV32 object, not aggregate firmware fit, whole-call-chain/callback stack, cycles, service deadline or hardware proof')
 inputs={**prior['inputs'],**before}
 for n,h in inputs.items():
  if sha(u/n)!=h:raise RuntimeError('source drift during verification: '+n)
 report=dict(schema='ae350-classic-security-source-stage-v1',selected_in_production=False,native_transport_wired=False,hardware_tested=False,
  physical_key_backend_implemented=False,flash_written=False,phone_interoperability_verified=False,security_policy='SSP Mode4 Level2; NoInputNoOutput; GeneralBonding; no MITM/SC/legacy pairing',
  inputs=inputs,tools=prior['tools'],baseline=baseline,session_only_baseline=session_only_baseline,mutants=mutants,masked_controls=controls,security_rv32_budget=budget,classic_rv32_budget=prior['rv32_budget'],
  delay=prior['baseline'],prior_classic=prior['prior_wire'],prior_mutants=prior['prior_mutants'],delay_mutants=len(prior['mutants']),sbc_reference_cases=prior['prior_decoder_cases'],commands=commands)
 report['outputs']={str(f.relative_to(out)):sha(f)for f in sorted(out.rglob('*'))if f.is_file()}
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report[k]for k in('schema','baseline','security_rv32_budget','classic_rv32_budget')},indent=2))
if __name__=='__main__':main()
