#!/usr/bin/env python3
"""Reproduce the dated, source-bound workstation evidence; never access hardware."""
from pathlib import Path
import argparse,hashlib,json,sys,shutil,subprocess,tempfile
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tools'))
from audit_workstation_timing import audit as timing_audit
from audit_workstation_cdc import audit as cdc_audit
from workstation_memory import audit as memory_audit
from workstation_sources import accepted_cnn_inputs,verify_cnn_inputs,TIMING85_BUILD,TIMING85_OVERLAYS
from workstation_cnn_cdc import transform as trace_transform,LINK as TRACE_LINK,select as trace_select
from workstation_timing_constraints import physical_constraints
from build_full_song_83_bp_ddr_isolation import FROZEN
from workstation_bus_timing import INPUTS,HELPER_SHA256,MODULES,expected_dma
from cnn_ddr_pipeline_patch import patch_hdmi,retime_tf_buffer_enable
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
parser=argparse.ArgumentParser();parser.add_argument('build',type=Path);parser.add_argument('--prepare',type=Path,required=True)
parser.add_argument('--functional-only',action='store_true',help='Validate source-bound functional evidence without claiming timing closure')
parser.add_argument('--vector-local-envelope',action='store_true',help='Require the fixed p34 per-voice RTL and real synthesized equivalence evidence')
a=parser.parse_args();build=a.build.resolve();prepare=a.prepare.resolve();stage=build/'Prj1'
p8=R/'results/workstation_scope83_timing85_20261018_051508_944162'
p7=R/'results/workstation_scope83_timing85_20261018_043944_494587'
p11=R/'results/workstation_scope83_timing85_20261018_075051_477454'
p6=R/'results/workstation_scope83_timing85_20261018_031221_737775'
base=R/'results/song_guide_full83_20261006_203125_607466'
if not a.functional_only:
 record=load(build/'tool_result.json');assert record['exit_code']==0 and record['inputs_unchanged']
inputs=load(build/'workstation_inputs.json');assert all(sha(stage/n)==h for n,h in inputs.items())
prepared=load(prepare/'workstation_inputs.json');assert all(sha(prepare/'Prj1'/n)==h for n,h in prepared.items())
logical=lambda m:{n:h for n,h in m.items() if not n.endswith(('.sdc','.pr','.p')) and n!='scripts/build.tcl'}
assert {n:h for n,h in logical(inputs).items() if not n.startswith('build/timing_reference')}==logical(prepared),'diagnostic differs from prepared logic'
normalize_tcl=lambda p:'\n'.join(x for x in p.read_text().splitlines() if not x.startswith(('set_option -inc_pnr','set_option -route_option','set_option -replicate_resources','set_option -place_option','set_option -opt_goal')))
assert normalize_tcl(stage/'scripts/build.tcl')==normalize_tcl(prepare/'Prj1/scripts/build.tcl')
vector_delta=None
if a.vector_local_envelope:
 from workstation_vector_timing import VECTOR,REFERENCE,BASE_SHA256,transform as local_envelope
 vector_reference=R/REFERENCE;vector_old=vector_reference/'Prj1'/VECTOR
 previous_inputs=load(vector_reference/'workstation_inputs.json')
 assert all(sha(vector_reference/'Prj1'/n)==h for n,h in previous_inputs.items()),'vector reference inputs drift'
 assert sha(vector_old)==BASE_SHA256
 assert (stage/VECTOR).read_text()==local_envelope(vector_old.read_text()),'vector change exceeds the exact local-envelope transform'
 old_logic=logical(previous_inputs);new_logic={n:h for n,h in logical(inputs).items() if not n.startswith('build/timing_reference')}
 assert {n for n in old_logic.keys()|new_logic.keys() if old_logic.get(n)!=new_logic.get(n)}=={VECTOR},'p34 changed more than the vector source'
 vector_event=R/'results/scope_event_ab_20261018_214306_268939'
 vector_net=R/'results/scope_synth_ab_20261018_214306_270701'
 for tested in [vector_event,vector_net]:
  tested_inputs=load(tested/'inputs.json');assert load(tested/'verification.json')['passed']
  assert tested_inputs[str(vector_old)]==BASE_SHA256,'wrong vector reference in equivalence test'
  assert tested_inputs[str(prepare/'Prj1'/VECTOR)]==sha(stage/VECTOR),'equivalence test selected a different new vector'
  assert all(sha(Path(n))==h for n,h in tested_inputs.items()),'stale vector equivalence inputs'
 vector_delta=dict(file=VECTOR,reference=REFERENCE,old_sha256=BASE_SHA256,new_sha256=sha(stage/VECTOR),added_cycles=0,
  event_equivalence=str(vector_event.relative_to(R)),synthesis_equivalence=str(vector_net.relative_to(R)),
  transform_sha256=sha(R/'tools/workstation_vector_timing.py'),cycles=213522,events=2656,stereo_frames=1776,
  proof='RTL all-voice states and real Gowin four-state netlist match p27 cycle by cycle; p27 retains existing regression evidence')
# p11 differs from the tested p10 topology only by the exact diagnostic
# substitution, its source module and the project file's additional file entry.
p10_inputs=logical(load(p8/'workstation_inputs.json'));current_inputs=logical(inputs)
added=set(current_inputs)-set(p10_inputs)
# An immutable .pr physical reference is an input artifact, not design logic.
added={n for n in added if not n.startswith('build/timing_reference')}
assert added=={'rtl/timing/gw138k_level_cdc.sv'},added
changed={n for n in p10_inputs if p10_inputs[n]!=current_inputs.get(n)}
expected_changes={TRACE_LINK,'Prj1.gprj','constraints/tang_mega_138k.cst'}
if vector_delta:expected_changes.add(VECTOR)
assert changed==expected_changes,changed
assert (stage/'constraints/tang_mega_138k.cst').read_text()==(p8/'Prj1/constraints/tang_mega_138k.cst').read_text()+physical_constraints()
assert (stage/TRACE_LINK).read_text()==trace_transform((R/TIMING85_BUILD/'Prj1'/TRACE_LINK).read_text())
assert sha(stage/'rtl/timing/gw138k_level_cdc.sv')==sha(R/'rtl/timing/gw138k_level_cdc.sv')
import xml.etree.ElementTree as ET
new_project=ET.parse(stage/'Prj1.gprj');old_project=ET.parse(p8/'Prj1/Prj1.gprj')
files=new_project.getroot().find('FileList')
new_entry=[e for e in files if e.get('path')=='rtl/timing/gw138k_level_cdc.sv']
assert len(new_entry)==1;files.remove(new_entry[0])
assert ET.tostring(new_project.getroot())==ET.tostring(old_project.getroot()),'project changed beyond the diagnostic module'
meta=load(build/'build_metadata.json');source=load(build/'cnn_source_audit.json')
verify_cnn_inputs(stage,meta['music_sha256']);assert source['policy']=='full83_plus_clk50_timing85'
assert len(source['timing_overlays'])==6 and len(source['selected_sha256'])==73
raw_selection={n:sha(R/TIMING85_BUILD/'Prj1'/n) for n in meta['music_sha256']}
selected,trace_record=trace_select(R,raw_selection)
assert selected==meta['music_sha256']==source['selected_sha256']
assert source['local_transforms']==[trace_record]
assert all(sha(R/n)==h for n,h in source['live_sha256'].items())
for n,(staged,h) in FROZEN.items():
 assert sha(R/n)==h,'live frozen source changed: '+n
 expected=meta['bus_timing']['transformed_sha256'].get(staged,h)
 assert sha(stage/staged)==expected,'staged frozen source mismatch: '+staged
accepted_cnn_inputs(base/'Prj1',load(base/'workstation_inputs.json'))
ref=R/TIMING85_BUILD;accepted_cnn_inputs(ref/'Prj1',load(ref/'workstation_inputs.json'))
bus=meta['bus_timing'];assert bus['original_sha256']==INPUTS and bus['helper_sha256']==HELPER_SHA256
assert bus['module_sha256']==MODULES and not bus['flash_boot'] and bus['new_ddr_clients']==bus['added_bsram']==0
for n,fn in {'src/storage/tf_audio_ddr_dma.v':expected_dma,'src/memory/tf_audio_ddr_command_buffer.sv':retime_tf_buffer_enable,'src/video/hdmi_display.v':lambda s:patch_hdmi(s,buffered_clients=True)}.items():
 assert sha(base/'Prj1'/n)==INPUTS[n]
 assert (stage/n).read_text()==fn((base/'Prj1'/n).read_text())
 assert sha(stage/n)==bus['transformed_sha256'][n]
for n,h in MODULES.items():assert sha(stage/'rtl/timing'/n)==sha(R/'rtl/timing'/n)==h
old=load(R/'reports/current_workstation_sources_20261018/source_verification.json')
assert sha(R/'LATEST_WORKSTATION.json')==old['latest_workstation_sha256'];assert not meta['user_code_assigned']
out=R/'reports/workstation_timing_20261018';out.mkdir(exist_ok=True)
if not a.functional_only:
 timing=timing_audit(build);assert timing['timing_closed'],timing['problems']
 cdc=cdc_audit(build);assert cdc['passed'],cdc['errors']
 memory=memory_audit(build,'full');assert memory['pnr_bsram']<=262  # p10 adds one tuning ROM; independent 340-device-capacity gate remains
 from check_video_pll_init import inspect_video_pll_init
 pll_errors,pll_evidence=inspect_video_pll_init((stage/'impl/pnr/Prj1.sdf').read_text(),(stage/'impl/pnr/Prj1.vo').read_text(),stage)
 assert not pll_errors,pll_errors
 pll=dict(passed=True,errors=pll_errors,evidence=pll_evidence,hardware_tested=False)
 with tempfile.TemporaryDirectory(prefix='timing_scope_') as scratch:
  scope_path=Path(scratch)/'scope.json'
  subprocess.run([sys.executable,str(R/'tools/audit_scope_routes.py'),str(build),'--output',str(scope_path)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,text=True)
  scope_routes=load(scope_path);assert scope_routes['passed']
 for filename,data in [('workstation_timing.json',timing),('workstation_cdc.json',cdc)]:
  (build/filename).write_text(json.dumps(data,indent=2)+'\n')
 for name,data in [('timing.json',timing),('cdc.json',cdc),('memory.json',memory),('pll_init.json',pll),('scope_routes.json',scope_routes)]:
  (out/name).write_text(json.dumps(data,indent=2)+'\n')
 for name in ['workstation_inputs.json','build_metadata.json','cnn_source_audit.json','tool_result.json']:
  shutil.copy2(build/name,out/name)
tests={
 'timing_equivalence':(R/'results/timing_equivalence_20261018_051919_684168',p8/'Prj1'),
 'capture_equivalence':(R/'results/capture_input_ab_20261018_044145_637416',p7/'Prj1'),
 'vector_event_equivalence':(R/'results/scope_event_ab_20261018_051127_599809',R/'results/workstation_scope83_timing85_20261018_051101_623476/Prj1'),
 'vector_synthesis_equivalence':(R/'results/scope_synth_ab_20261018_051127_574785',R/'results/workstation_scope83_timing85_20261018_051101_623476/Prj1'),
 'workstation_regression':(p11/'current_regression_20261018_075619_078329',p11/'Prj1'),
 'diagnostic_cdc':(R/'results/workstation_scope83_timing85_20261018_141031_252897/cnn_trace_cdc_20261018_141043_793821',R/'results/workstation_scope83_timing85_20261018_141031_252897/Prj1'),
 'attach':(out/'attach_fixtures',p8/'Prj1'),
}
if vector_delta:
 tests['vector_event_equivalence']=(vector_event,prepare/'Prj1')
 tests['vector_synthesis_equivalence']=(vector_net,prepare/'Prj1')
 current_regression=next((p for p in sorted(prepare.glob('current_regression_*/verification.json'),reverse=True)
                          if load(p)['passed'] and len(load(p)['tests'])==18),None)
 if not a.functional_only:assert current_regression is not None,'p34 fresh 18-gate regression incomplete'
 if current_regression:tests['workstation_regression']=(current_regression.parent,prepare/'Prj1')
 vector_delta['fresh_18_gate_regression_passed']=current_regression is not None
 (out/'vector_local_envelope_equivalence.json').write_text(json.dumps(vector_delta,indent=2)+'\n')
bindings={}
archived_inputs=load(out/'attach_fixture_archive.json')
def verify_test_inputs(hashes,project):
 matched={}
 for n,h in hashes.items():
  p=Path(n) if Path(n).is_absolute() else R/n
  if str(p) in archived_inputs:
   entry=archived_inputs[str(p)];archived=R/entry['archived_path']
   assert entry['sha256']==h and sha(archived)==h,'changed archived test input: '+str(p)
   if p.exists():assert sha(p)==h,'stale original test input: '+str(p)
   p=archived
  # Old regression fixtures use the old vector. Accept that one file only
  # through the independently tested p27 -> p34 cycle-equivalent transform.
  if vector_delta and p==R/VECTOR and h==BASE_SHA256:p=vector_old
  assert sha(p)==h,'stale test input: '+str(p)
  overlays={'rtl/audio/gw138k_event_workstation.sv':'src/ae350/gw138k_event_workstation.sv','rtl/audio/gw138k_usb_lifecycle_merge.sv':'src/usb_a/gw138k_usb_lifecycle_merge.sv','rtl/audio/push2_controls.sv':'src/push2/push2_controls.sv','rtl/push2_usb_a_control.sv':'src/usb_a/push2_usb_a_control.sv','rtl/display_data/push2_surface_pixels.sv':'src/push2/push2_surface_pixels.sv'}
  name=None
  if vector_delta and p==vector_old:name=VECTOR
  elif p.is_relative_to(project):name=str(p.relative_to(project))
  elif p.is_relative_to(R) and str(p.relative_to(R)) in overlays:name=overlays[str(p.relative_to(R))]
  elif p.is_relative_to(R) and (stage/p.relative_to(R)).is_file() and not str(p.relative_to(R)).startswith('results/'):name=str(p.relative_to(R))
  elif p.is_relative_to(R/'rtl/push2') and (stage/'src/usb_a'/p.name).exists():name='src/usb_a/'+p.name
  elif p.is_relative_to(R/'rtl/push2') and (stage/'src/push2'/p.name).exists():name='src/push2/'+p.name
  if name is not None:
   if vector_delta and name==VECTOR and h==BASE_SHA256:
    assert sha(stage/name)==vector_delta['new_sha256'],'vector equivalence chain drift'
   else:assert sha(stage/name)==h,'untested final file: '+name
   matched[name]=h
 return matched
for name,(path,project) in tests.items():
 d=load(path/'verification.json');assert d['passed'],name
 shutil.copy2(path/'verification.json',out/(name+'.json'))
 bindings[name]={}
 for candidate in ['inputs.json','inputs_sha256.json','tf_inputs_sha256.json']:
  p=path/candidate
  if p.exists():
   bindings[name].update(verify_test_inputs(load(p),project))
   shutil.copy2(p,out/(name+'_'+candidate))
 (out/(name+'_location.txt')).write_text(str(path)+'\n')
scope_file=tests['workstation_regression'][0].parent/load(tests['workstation_regression'][0]/'verification.json')['scope_merge']
scope=load(scope_file);assert scope['passed'];bindings['scope_merge']=verify_test_inputs(scope['inputs'],tests['workstation_regression'][1])
shutil.copy2(scope_file,out/'scope_merge.json')
net=tests['vector_synthesis_equivalence'][0];assert sha(net/'Prj1/impl/gwsynthesis/Scope.vg')==load(net/'verification.json')['netlist_sha256']
for original in [stage/'rtl/audio/scope_vec/scope_vec_engine.sv',*sorted((stage/'rtl/audio/scope_vec/data').glob('*.mem')),stage/'sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem']:
 assert sha(original)==sha(net/'Prj1'/original.relative_to(stage))
for filename in ['ddr_bus_timing.json','tf_bus_timing_corrected_hash.json','tf_buffer_timing.json']:
 d=load(p7/filename);assert d['passed'],filename
 shutil.copy2(p7/filename,out/filename)
 # Bus tests exercised this exact p7 selected topology and source content.
 for n in ['src/storage/tf_audio_ddr_dma.v','src/memory/tf_audio_ddr_command_buffer.sv','src/video/hdmi_display.v','rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv','rtl/timing/basic_pitch_ddr_client_queues.sv']:
  assert sha(stage/n)==sha(p7/'Prj1'/n),'rerun bus tests: '+n
 assert load(p7/'tf_bus_timing_corrected_hash.json')['staged_source_sha256']==sha(stage/'src/storage/tf_audio_ddr_dma.v')
# The shared-DDR top wiring is byte-for-byte the tested p7 top once the
# independent USB MMIO register wrapper is removed.
top=(stage/'src/push2/gw138k_push_workstation_top.v').read_text()
start=top.index('    wire host_mmio_select,host_mmio_write,host_mmio_ready;')
end=top.index('    wire [223:0] usb_words;',start)
top=top[:start]+top[end:]
for port in ['select','write','address','wdata','ready','rdata']:
 top=top.replace(f'.mmio_{port}(host_mmio_{port})',f'.mmio_{port}(mmio_{port})')
assert top==(p7/'Prj1/src/push2/gw138k_push_workstation_top.v').read_text()
for filename in ['tf_read_total_source_bound.json','tf_read_availability_source_bound.json']:
 d=load(out/filename)
 assert d['passed'] and d['source_bound'] and d['patched_source_sha256']==sha(stage/'src/storage/tf_audio_ddr_dma.v')
(out/'test_source_bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
if a.functional_only:
 result=dict(passed=True,timing_closed=None,build=str(build.relative_to(R)),prepare=str(prepare.relative_to(R)),hardware_tested=False,source_bound_test_groups=len(bindings),local_cnn_transforms=source['local_transforms'])
 if vector_delta:result['vector_local_envelope_equivalence']=vector_delta
 (out/'current_functional_verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));sys.exit(0)
summary=dict(timing_closed=True,cdc_passed=True,pll_init_passed=True,scope_routes_passed=True,build=str(build.relative_to(R)),prepare=str(prepare.relative_to(R)),source_policy=source['policy'],local_cnn_transforms=source['local_transforms'],internal_physical_locality=True,io_pin_constraints_unchanged=True,input_count=len(inputs),synthesis_bsram=memory['bsram'],pnr_bsram=memory['pnr_bsram'],clock_targets_unchanged=True,accepted_full83_inputs_unchanged=True,timing85_inputs_unchanged=True,live_cnn_unchanged=True,frozen_live_sources_unchanged=True,staged_hdmi_has_bounded_transport_transform=True,latest_workstation_unchanged=True,regression_gates=18,hardware_tested=False,user_code_assigned=False,tests={n:str(p) for n,(p,_) in tests.items()})
if vector_delta:summary['vector_local_envelope_equivalence']=vector_delta
(out/'verification.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
