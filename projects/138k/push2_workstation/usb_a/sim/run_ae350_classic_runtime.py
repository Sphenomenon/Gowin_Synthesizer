#!/usr/bin/env python3
"""Actual fail-closed CPU runtime against checked asynchronous MMIO, not RTL/board."""
from pathlib import Path
import argparse,base64,hashlib,json,re,shutil,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.prepare_ae350_sbc import prepare

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

MUTANTS=(
 ('transport-private-copy','hci_transport.c','memcpy(t->tx,data,bytes);','memset(t->tx,0,bytes);'),
 ('accept-at-commit','hci_transport.c','t->tx_phase=3;','t->tx_phase=3;t->accepted=1;'),
 ('shared-token-reused','hci_transport.c','t->tx_token=++t->next_token;','t->tx_token=token;++t->next_token;'),
 ('completion-latch-not-cleared','hci_transport.c','t->accepted=t->transport_done=t->response_done=t->rejected=t->uncertain=0;\n    return 1;','return 1;'),
 ('command-early-ack','hci_transport.c','t->accepted&&t->transport_done&&t->response_done','t->accepted&&t->transport_done'),
 ('rx-ticket-unchecked','hci_transport.c','e!=epoch||k!=ticket','e!=epoch'),
 ('rx-retirement-not-refreshed','hci_transport.c','if(rx_identity(t,r->epoch,r->ticket))(void)rx_retirement(t);','(void)0;'),
 ('ignore-transport-uncertainty','hci_transport.c','t->uncertain=1;t->fault=A138_HCI_FAULT_UNCERTAIN;','t->uncertain=0;'),
 ('no-runtime-clock-tick','classic_runtime.c','a138_security_tick(&r->security,r->transport.epoch,r->transport.now_ms)!=A138_SECURITY_OK','0'),
 ('assume-br-capacity','classic_runtime.c','p->generation,t->available,p->data,p->bytes','p->generation,1,p->data,p->bytes'),
 ('response-token-unchecked','classic_runtime.c','p->token!=t->tx_token||','0||'),
 ('no-physical-fence','classic_runtime.c','(void)r->transport.bus.write(r->transport.bus.context,CLASSIC_FENCE,r->transport.epoch);','(void)0;'),
 ('media-generation-unchecked','classic_runtime.c','f.generation!=c->generation||','0||'),
 ('permanent-drift-ignored','classic_runtime.c','||!f.drift_managed',''),
 ('uncertain-pcm-retried','classic_runtime.c','submitted!=A138_CLASSIC_REJECTED||','0||'),
)
PCM_MUTANTS=(
 ('implemented-src-is-verification','if(!(caps&8u))return 1;','if(!(caps&4u))return 1;'),
 ('partial-block-accepted','if(d->offset!=d->frames)return A138_CLASSIC_REJECTED;','if(0)return A138_CLASSIC_REJECTED;'),
 ('free-slot-overwritten','if(!(free_mask&(1u<<d->slot)))return A138_CLASSIC_REJECTED;','if(0)return A138_CLASSIC_REJECTED;'),
 ('mono-right-not-duplicated','pcm[at*channels+(channels==2u)]','pcm[at*channels+1u]'),
 ('block-sequence-not-advanced','++d->next_sequence;','(void)0;'),
 ('old-context-cancels-new','&&s==stream)',')'),
 ('clock-busy-is-failure','if(submitted==A138_CLK_PENDING||submitted==A138_CLK_UNARMED)return 0;','if(0)return 0;'),
 ('pending-source-revokes-stream','if((status&192u)!=192u)return 0;','if((status&192u)!=192u||status&48u)return 0;'),
 ('old-owner-failure-blocks-fresh-arm','if(d->armed&&(status&8u))','if(status&8u)'),
)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);fw=ROOT/'firmware/ae350';commands=[]
 adaptation=prepare(ROOT,out/'adapted');dec=out/'adapted/decoder'
 names=['hci_transport.c','classic_runtime.c','classic_security.c','classic_service.c','sbc_decoder_service.c',
        'ble_business_owner.c','business_mailbox.c','recording_service.c','pcm_media.c','audio_clock_service.c']
 sources=[fw/n for n in names]+sorted((dec/'srce').glob('*.c'))
 cc=Path(shutil.which('cc')).resolve();flags=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',
       '-Wno-unused-parameter','-DA138_BLE_BUSINESS','-I'+str(fw),'-I'+str(dec/'include'),'-I'+str(dec/'srce')]
 fixture=ROOT/'sim/ae350_runtime_fixture.c'
 inputs={str(x.relative_to(ROOT)):sha(x)for x in [fixture,Path(__file__).resolve(),ROOT/'tools/prepare_ae350_sbc.py',
      ROOT/'sim/fixtures/ae350_sbc_reference.json',ROOT/'sim/ae350_pcm_media_fixture.c',ROOT/'sim/ae350_clock_service_host.c',
      *[fw/n for n in names],*sorted(fw.glob('*.h'))]}
 def run(argv,name,ok=True):
  r=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=120)
  (out/(name+'.log')).write_text(r.stdout+r.stderr);commands.append(dict(argv=list(map(str,argv)),returncode=r.returncode))
  if ok and r.returncode:raise RuntimeError((name,r.returncode,r.stdout,r.stderr))
  return r
 for tag,extra in [('native',[]),('sanitized',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])]:
  run([*flags,*extra,fixture,*sources,'-o',out/tag],tag+'-compile')
 cases=[]
 for row in json.loads((ROOT/'sim/fixtures/ae350_sbc_reference.json').read_text())['cases']:
  name=row['name'];sbc=out/(name+'.sbc');sbc.write_bytes(base64.b64decode(row['sbc_base64']))
  reference=base64.b64decode(row['reference_pcm_le_base64']);summaries={};raw=None
  for tag in ['native','sanitized']:
   pcm=out/(name+'-'+tag+'.pcm');result=run([out/tag,sbc,pcm],name+'-'+tag)
   if 'Sanitizer'in result.stderr or 'runtime error:'in result.stderr:raise RuntimeError('sanitizer finding')
   match=re.search(r'classic runtime: (\d+) checks passed',result.stdout)
   assert match;summaries[tag]=int(match[1])
   if raw is not None:assert raw==pcm.read_bytes()
   raw=pcm.read_bytes()
  assert raw and len(raw)<=len(reference)
  values=struct.unpack('<'+'h'*(len(raw)//2),raw);refs=struct.unpack('<'+'h'*(len(raw)//2),reference[:len(raw)])
  maximum=max(abs(x-y)for x,y in zip(values,refs));assert maximum<=8,(name,maximum)
  cases.append(dict(name=name,checks=summaries,decoded_first_frame_samples=len(values),maximum_lsb_error=maximum,
      input_sha256=sha(sbc),output_sha256=hashlib.sha256(raw).hexdigest()))
 mutants={}
 for name,which,old,new in MUTANTS:
  original=fw/which;text=original.read_text();assert text.count(old)==1,(name,text.count(old))
  mutated=out/(name+'.c');mutated.write_text(text.replace(old,new));exe=out/name
  run([*flags,'-Wno-unused-but-set-variable',fixture,*[mutated if f==original else f for f in sources],'-o',exe],name+'-compile')
  result=run([exe,out/(cases[0]['name']+'.sbc'),out/(name+'.pcm')],name+'-run',False)
  assert result.returncode and 'check 'in result.stderr,(name,result.stdout,result.stderr)
  mutants[name]=dict(killed=True,sha256=sha(mutated),failure=result.stderr.strip())
 for n,h in inputs.items():assert sha(ROOT/n)==h,n
 pcm_baseline={};pcm_mutants={};pcm_fixture=ROOT/'sim/ae350_pcm_media_fixture.c'
 for tag,extra in [('native',[]),('sanitized',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])]:
  exe=out/('pcm-'+tag);run([*flags,*extra,pcm_fixture,fw/'pcm_media.c',fw/'audio_clock_service.c','-o',exe],'pcm-'+tag+'-compile')
  result=run([exe],'pcm-'+tag+'-run');match=re.search(r'PCM media adapter: (\d+) checks passed',result.stdout);assert match
  assert 'Sanitizer'not in result.stderr and 'runtime error:'not in result.stderr
  pcm_baseline[tag]=dict(checks=int(match[1]),summary=result.stdout.strip())
 text=(fw/'pcm_media.c').read_text()
 for name,old,new in PCM_MUTANTS:
  assert text.count(old)==1,(name,text.count(old));mutated=out/(name+'.c');mutated.write_text(text.replace(old,new));exe=out/name
  run([*flags,'-Wno-unused-but-set-variable',pcm_fixture,mutated,fw/'audio_clock_service.c','-o',exe],name+'-compile')
  result=run([exe],name+'-run',False);assert result.returncode and 'FAIL line'in result.stderr,(name,result.stdout,result.stderr)
  pcm_mutants[name]=dict(killed=True,sha256=sha(mutated),failure=result.stderr.strip())
 for n,h in inputs.items():assert sha(ROOT/n)==h,n
 report=dict(schema='ae350-classic-runtime-mmio-v1',inputs=inputs,adaptation=adaptation,cases=cases,mutants=mutants,
    pcm_baseline=pcm_baseline,pcm_mutants=pcm_mutants,
    compiler=dict(path=str(cc),sha256=sha(cc)),commands=commands,
    per_pass_checked_mmio_access_bound=64,maximum_new_decodes_per_pass=1,
    scope='asynchronous checked-MMIO model plus actual C security/Classic/SBC and runtime; media context injected only for scheduling tests',
    native_RTL_verified=False,physical_media_backend=False,durable_bond_backend=False,selected_profile=False,
    CPU_cycles_measured=False,phone_interoperability=False,hardware_tested=False)
 report['outputs']={str(f.relative_to(out)):sha(f)for f in sorted(out.rglob('*'))if f.is_file()}
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(cases=cases,killed_mutants=len(mutants),scope=report['scope']),indent=2))

if __name__=='__main__':main()
