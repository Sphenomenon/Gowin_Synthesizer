"""Exact actual-ROM callback/stack closure for the explicit fail-closed runtime."""
from pathlib import Path
import hashlib,json,re,collections,copy
from tools.ae350_local_memory import call_chain_report,direct_long_calls
from tools.ae350_rom_split_audit import verify_tables
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def analyze(output,root):
 out,root=Path(output),Path(root);d=json.loads((out/'verification.json').read_text())
 if d.get('runtime_owner')is not True or d.get('source_text_overlay')is not False:
  raise ValueError('actual versioned runtime required')
 worker=d.get('worker_demo')is True
 worker_review=json.loads((root/'tools/ae350_worker_recording_indirect_review.json').read_text())if worker else None
 if worker:
  for rel,h in worker_review['input_sha256'].items():
   if d['input_sha256'].get(rel)!=h or sha(root/rel)!=h:raise ValueError('worker recording callback source changed: '+rel)
  compilers=[h for name,h in d['tool_sha256'].items()if name.endswith('-gcc')]
  variants=[v for v in worker_review['machine_reviews']if compilers==[v['compiler_sha256']]]
  if len(variants)!=1:raise ValueError('worker callback compiler binary is not reviewed')
  worker_machine=variants[0]['prior_machine_sites']
 dis=(out/'firmware.dis').read_text();legacy=json.loads((root/'tools/ae350_ble_business_indirect_review.json').read_text())
 prior={}
 for site in legacy['sites']:prior.setdefault(site['caller'],[]).append(site)
 for name in ['audio_clock_service.c','recording_service.c','business_mailbox.c','ble_business_owner.c']:
  rel='firmware/ae350/'+name
  if legacy['input_sha256'][rel]!=d['input_sha256'][rel]:
   # The opt-in additions do not alter a single byte of the inherited owner.
   # Default builds retain their original exact callback machine-site checks.
   text=(root/rel).read_text()
   inherited=re.sub(r'^#ifdef A138_SINGLE_BLE_RECORDING\n.*?^#endif\n','',text,flags=re.M|re.S)if name=='ble_business_owner.c' else text
   if hashlib.sha256(inherited.encode()).hexdigest()!=legacy['input_sha256'][rel]:raise ValueError('prior callback owner changed: '+name)
 targets={name:sorted(set(x for row in rows for x in row['targets']))for name,rows in prior.items()}
 for name in ['rx_identity','rx_retirement','a138_hci_step','a138_hci_tx_retire','a138_hci_rx_release',
              'pcm_key','pcm_command','pcm_submit','pcm_cancel','pcm_poll']:
  targets[name]=['hci_mmio_read','hci_mmio_write']
 targets.update({'a138_security_pump':['unavailable_load','unavailable_replace','unavailable_delete'],
  'a138_security_event':['unavailable_load'],'cancel_media':['pcm_cancel'],
  'a138_clock_probe':['mmio_read','mmio_write'],
  'a138_clock_submit':['mmio_read','mmio_write'],
  'a138_clock_poll':['mmio_read','mmio_write'],
  'runtime_pass.part.0':['pcm_poll','pcm_submit'],'fail_runtime':['hci_mmio_write'],
  'OI_SBC_ComputeBitAllocation':['monoBitAllocation','dualBitAllocation','stereoBitAllocation'],
  'DecodeBody.part.0':['OI_SBC_ReadSamplesJoint4','OI_SBC_ReadSamplesJoint8'],
  'OI_SBC_SynthFrame':['OI_SBC_SynthFrame_4SB','OI_SBC_SynthFrame_80']})
 if worker:
  # The session-only source branch contains no durable-store callbacks at all.
  targets.pop('a138_security_pump');targets.pop('a138_security_event')
 long=direct_long_calls(dis);sites=[];all_sites=[];caller=None
 for line in dis.splitlines():
  h=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
  if h:caller=h[1]
  m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+',line)
  if m and int(m[2],16)&0x7f==0x67 and int(m[2],16)!=0x8067 and int(m[1],16)not in long:
   row=dict(caller=caller,address='0x'+m[1],instruction=m[2]);all_sites.append(row)
   if caller in targets:sites.append(dict(**row,targets=targets[caller]))
 for caller,old in prior.items():
  actual=[s['instruction']for s in sites if s['caller']==caller]
  expected=worker_machine[caller]if worker else[s['instruction']for s in old]
  if actual!=expected:raise ValueError('prior callback machine sites changed: '+caller)
 inputs=dict(d['input_sha256'])
 for f in(out/'adapted').rglob('*'):
  if f.is_file():inputs['external/adapted/'+str(f.relative_to(out/'adapted'))]=sha(f)
 review=dict(schema=1,input_sha256=inputs,disassembly_sha256=hashlib.sha256(dis.encode()).hexdigest(),
  source_target_review='''Actual source roots are versioned ui_main services_main -> background init/pump -> classic_runtime firmware init/pump and the retained BLE owner. There is one static firmware_runtime and one static firmware_media. hci_transport's sole installed bus is a138_hci_mmio_bus; PCM's bus is the same constructor at F806. Each bus callback site is conservatively given both hci_mmio_read/write targets even when its source member fixes one. PCM clock bus is the retained a138_clock_mmio_bus, whose actual constructor installs the static mmio_read/mmio_write in audio_clock_service.c. The newly reachable clock probe/submit/poll sites are conservatively given both targets; their source hash is unchanged from the reviewed legacy clock source. The sole actual media constructor installs pcm_poll,pcm_submit,pcm_cancel, never the host-test callbacks. runtime_pass's two sites conservatively include both poll and submit. cancel_media fixes pcm_cancel. fail_runtime's exact-epoch write fixes hci_mmio_write. The actual firmware installs unavailable_load/replace/delete, all bounded functions returning ERROR, and then explicitly disables GeneralBonding because no durable backend exists. No runtime method changes those pointer values after init; the security owner copies that exact store on start. Their union conservatively bounds each security-pump store site, including disabled branches, and event load fixes unavailable_load. This is NOT a persistent backend claim. Public caller-configurable test constructors are not additional actual firmware roots. Existing clock/recording/business callback source identities and previously reviewed ordered machine JALR bytes remain equal to the prior reviewed owners. SBC balloc/SpecializedReadSamples/SynthFrame tables are checked word-for-word in this ELF; format/channel/subband bounds remain checked by the SBC service. All other reachable unresolved JALR, missing/dynamic frames, recursion and overflow fail closed. Interrupts remain disabled. Memory corruption, arbitrary replacement of configuration pointers, actual CPU cycles/DDR waits and physical watermark are outside this conservative source/machine stack bound.''',sites=sites)
 if worker:
  review['source_target_review']='''Worker source selects one actual ui_main root, one static Classic runtime/media and one static BLE business owner. Session-only constructor binds actual PCM poll/submit/cancel callbacks and no durable-store callback. Its preprocessor branch removes durable load/replace/delete calls; the actual security firmware advertises NoBonding and does not claim persistent keys. hci_transport/PCM bus sites conservatively include hci_mmio_read/write; clock sites conservatively include mmio_read/write. Existing recording callbacks retain record_mmio_read/write and business callbacks retain business_mmio_read/write, as installed by their exact static firmware constructors. CPU/UI REC requests share the BLE owner's sequence, object/task IDs and physical descriptor slot; no new PCM storage or callback constructor is introduced. All worker source identities and ordered original-family callback instructions are pinned in ae350_worker_recording_indirect_review.json. Default owner bytes after removing opt-in blocks must still equal the original reviewed SHA. SBC tables are checked word-for-word in this ELF. Missing or unknown reachable JALR sites, unknown targets, dynamic stack frames, recursion and reserved-stack overflow fail closed. Interrupts remain disabled. No measured CPU-cycle, DDR-wait, hardware-watermark, radio, audio or deployment acceptance is inferred.'''
 (out/'runtime_indirect_review.json').write_text(json.dumps(review,indent=2)+'\n')
 frames=[]
 for f in sorted(out.glob('*.su')):
  for line in f.read_text().splitlines():
   fn,n,kind=line.split('\t');frames.append(dict(function=fn,bytes=int(n),kind=kind))
 stack=call_chain_report(out,frames,dis,16384,reviewed_indirect_calls=review,input_sha256=inputs)
 controls=[]
 for name,mutate,capacity in [
  ('missing-machine-site',lambda r:r['sites'].pop(),16384),
  ('unknown-callback-target',lambda r:r['sites'][0].update(targets=['unreviewed_target']),16384),
  ('source-identity-drift',lambda r:r['input_sha256'].update({next(iter(inputs)):'0'*64}),16384),
  ('reserved-stack-overflow',lambda r:None,1)]:
  changed=copy.deepcopy(review);mutate(changed)
  try:call_chain_report(out,frames,dis,capacity,reviewed_indirect_calls=changed,input_sha256=inputs)
  except ValueError as error:controls.append(dict(name=name,rejected=True,error=str(error)))
  else:raise ValueError('runtime stack audit negative control survived: '+name)
 required=['a138_classic_runtime_firmware_init','a138_classic_runtime_firmware_pump','a138_hci_step',
   'a138_hci_offer','a138_hci_tx_retire','a138_hci_rx_release','a138_security_start','a138_security_tick',
   'a138_security_pump','a138_security_event','a138_security_response','a138_classic_acl',
   'a138_sbc_begin','a138_sbc_decode','OI_CODEC_SBC_DecodeFrame','a138_ble_business_firmware_pump',
   'pcm_poll','pcm_submit','pcm_cancel','a138_clock_submit','a138_clock_poll']
 if worker:
  required+=['a138_classic_runtime_init_session','a138_security_start_session',
   'a138_ble_record_firmware_submit','a138_ble_record_firmware_poll','a138_ble_record_firmware_facts']
  required.remove('a138_security_start')
 missing=set(required)-set(stack['reachable_functions'])
 if missing:raise ValueError('actual runtime roots missing: '+str(sorted(missing)))
 if(out/'undefined.log').read_text().strip():raise ValueError('linked undefined symbols')
 tables=verify_tables(out)
 result=dict(schema='ae350-classic-runtime-stack-v1',input_sha256=inputs,capacity=d['capacity'],stack=stack,
   required_actual_roots=required,actual_callback_tables=tables,audit_negative_controls=controls,all_nonreturn_JALR_sites=len(all_sites),
   reviewed_JALR_sites=len(sites),compiler_stack_frames=frames,
   ELF_sha256=sha(out/'firmware.elf'),BIN_sha256=sha(out/'firmware.bin'),
   worker_recording_proxy=worker,source_text_overlay=False,no_GC=True,no_LTO=True,durable_backend=False,physical_watermark=False,
   CPU_cycles_measured=False,native_candidate_selected=False,hardware_acceptance=False)
 (out/'runtime_callgraph_verification.json').write_text(json.dumps(result,indent=2)+'\n');return result
