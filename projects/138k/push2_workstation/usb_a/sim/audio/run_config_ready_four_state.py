#!/usr/bin/env python3
from pathlib import Path
import sys,re,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[2]
import argparse
ap=argparse.ArgumentParser(description='Complete real M/W configuration-ready four-state differential test and negative controls')
ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();PROJECT=args.project.resolve()
sys.path.insert(0,str(ROOT/'sim/audio'))
from run_runtime_controlled import runtime_sources
from prove_config_ready_cofactor import EVENT,REFERENCE,source_contract
source_contract()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
adaptation_records=[]
def adapt(text,name):
    import collections
    original=text
    declarations=[]
    names={
      'workstation_runtime_oscillator_engine.sv':['expression_select','maximum_voice_index','accepted_event','accepted_expression','accepted_sample','midi_valid','partial_busy','partial_valid','gain_valid','issue_active','sine_valid_i','sine_valid_o','gain_product_valid','envelope_product_valid','finalize_valid'],
      'workstation_runtime_delay_effect_ddr.sv':['wr_flush_pending','underflow_sticky'],
      'gw138k_event_workstation.sv':['legacy_active_mask','scope_enable'],
    }.get(name,[])
    for symbol in names:
      found=re.findall(r'^  (?:logic|wire) [^=;\n]*\b'+symbol+r'\b[^=;\n]*;\n',text,re.M)
      assert len(found)==1,(name,symbol,found)
      line=found[0];assert '='not in line
      text=text.replace(line,'',1);declarations.append(line)
    if declarations:
      match=re.search(r'\n\);\n',text);assert match
      text=text[:match.end()]+''.join(declarations)+text[match.end():]
    if name=='gw138k_event_workstation.sv':
      ds=[]
      for symbol in ['kind','a','b']:
        found=re.findall(r'^  wire \[[^\n]*?\b'+symbol+r' =[^;\n]*;\n',text,re.M);assert len(found)==1,(name,symbol,found)
        text=text.replace(found[0],'',1);ds.append(found[0])
      point='  logic [17:0] event_data;\n';assert text.count(point)==1;text=text.replace(point,point+''.join(ds))
    if name=='workstation_runtime_stereo_effects.sv':
      found=re.findall(r'^  wire \[1:0\] selected_id=[^;\n]*;\n',text,re.M);assert len(found)==1
      text=text.replace(found[0],'',1);point='  wire selected_ready=';assert text.count(point)==1;text=text.replace(point,found[0]+point)
    assert collections.Counter(re.findall(r'\S+',original))==collections.Counter(re.findall(r'\S+',text)),'tokens changed'
    if original!=text:adaptation_records.append({'name':name,'before_sha256':hashlib.sha256(original.encode()).hexdigest(),'after_sha256':hashlib.sha256(text.encode()).hexdigest(),'only_same_scope_declaration_reorder':True})
    return text
current=REFERENCE.read_text()
(out/'current_reference.sv').write_text(re.sub(r'\bgw138k_event_workstation\b','gw138k_event_workstation_current_reference',adapt(current,'gw138k_event_workstation.sv')))
tb='''`timescale 1ns/1ps
module complete_case #(parameter bit SYNTH=1)(output reg finished=0);
reg clk=0,rst=0,rate_commit=0,event_rate=0,sample=0,busy=0,history=0;
reg lifecycle=0,event_v=0,mode_v=0,failed=0,quiet=1,fx_ready=1;
reg [17:0] ev=0;wire actual_ready,reference_ready;
'''
ports='.clk_i(clk),.rst_ni(rst),.sample_ce_i(sample),.rate_commit_i(rate_commit),.event_rate_commit_i(event_rate),.rate_44100_i(1\'b0),.history_clear_i(history),.rate_ready_o(READY),.cpu_event_valid_i(1\'b0),.cpu_event_i(18\'d0),.midi_byte_valid_i(1\'b0),.midi_byte_i(8\'d0),.pc_byte_valid_i(1\'b0),.pc_byte_i(8\'d0),.pcm_left_i(32\'sd0),.pcm_right_i(32\'sd0),.delay_peer_heartbeat_i(1\'b0),.delay_dma_fault_i(1\'b0),.delay_mem_clk_i(clk),.delay_mem_rst_ni(rst),.delay_dwr_pop_i(1\'b0),.delay_drd_push_i(1\'b0),.delay_drd_data_i(65\'d0)'
params='#(.TIMING_OPTIMIZED(1),.REQUEST_DRIVEN_RENDER(1),.RUNTIME_RATE_ENABLE(1),.RUNTIME_EFFECTS_ENABLE(1),.EVENT_CONFIG_COFACTOR_ENABLE(1),.SYNTH_ENGINES_ENABLE(SYNTH),.D_ONLY_ENABLE(!SYNTH))'
tb+='gw138k_event_workstation '+params+' actual('+ports.replace('READY','actual_ready')+');\n'
tb+='gw138k_event_workstation_current_reference '+params+' reference('+ports.replace('READY','reference_ready')+');\n'
force={'runtime_configuration.busy':'busy','runtime_configuration.failed':'failed','runtime_configuration.pipeline_quiet':'quiet','fx_fault':"1'b0",'fx_config_ready':'fx_ready','usb_lifecycle':'lifecycle','native_clear':"1'b0",'pending':"1'b0",'releasing':"1'b0",'load_busy':"1'b0",'mix_busy':"1'b0",'vec_busy':"1'b0",'mode_pending':'mode_v','mode_ready':"1'b1",'event_valid':'event_v','event_data':'ev','allocated':"32'd0",'core_event_ready':"1'b1",'core_expression_ready':"1'b1",'scope_enable':"1'b0",'deferred_current':"1'b1",'runtime_quiescent':"1'b1",'vec_ready':"1'b1",'fx_sample_slot_ready':"1'b1",'synth_joined':"1'b0",'vec_joined':"1'b0"}
tb+='integer checks=0,unknown_checks=0,idle_event_checks=0,held_checks=0;integer k,e;\n'
tb+='function automatic digit4(input integer value);begin case(value&3)0:digit4=0;1:digit4=1;2:digit4=1\'bx;3:digit4=1\'bz;endcase end endfunction\n'
tb+='''task check;begin #2;
if(actual_ready !== reference_ready || actual.dispatch!==reference.dispatch || actual.core_ce!==reference.core_ce || actual.parameter_commit!==reference.parameter_commit || actual.engine_rate_commit!==reference.engine_rate_commit)
$fatal(1,"COMPLETE_MODULE mismatch synth=%0d check=%0d rate=%b eventrate=%b sample=%b busy=%b actual=%b reference=%b event=%b kind=%0d",SYNTH,checks,rate_commit,event_rate,sample,busy,actual_ready,reference_ready,event_v,ev[17:14]);
checks=checks+1;if(rate_commit===1'bx || rate_commit===1'bz)unknown_checks=unknown_checks+1;
if(rate_commit===1'b0 && event_v && sample===1'b0)idle_event_checks=idle_event_checks+1;
if(rate_commit===1'b1 && event_rate===1'b1 && busy===1'b0)held_checks=held_checks+1;
end endtask
initial begin
'''
for inst in ('actual','reference'):
 for path,val in force.items():tb+='force '+inst+'.'+path+'='+val+';\n'
tb+='''#2;rst=1;
// Four-valued request and stored-busy controls on complete real modules.
// Queued NoteOn/Off/pressure/parameter and pending mode cover live arbitration.
for(e=0;e<6;e=e+1)begin
case(e)0:begin event_v=0;mode_v=0;ev=0;end
1:begin event_v=1;mode_v=0;ev={4'd1,7'd60,7'd100};end
2:begin event_v=1;mode_v=0;ev={4'd0,7'd60,7'd0};end
3:begin event_v=1;mode_v=0;ev={4'd5,7'd60,7'd81};end
4:begin event_v=1;mode_v=0;ev={4'd2,7'd120,7'd0};end
5:begin event_v=1;mode_v=1;ev={4'd2,7'd80,7'd2};end endcase
for(k=0;k<256;k=k+1)begin rate_commit=digit4(k);event_rate=digit4(k>>2);busy=digit4(k>>4);sample=digit4(k>>6);history=0;lifecycle=0;failed=0;quiet=1;fx_ready=1;check();end
end
// Exhaust actual veto inputs with a held external fence; retain X/Z.
event_v=1;mode_v=1;ev={4'd1,7'd63,7'd99};rate_commit=1;event_rate=1;sample=0;busy=0;
for(k=0;k<256;k=k+1)begin lifecycle=digit4(k);failed=digit4(k>>2);quiet=digit4(k>>4);fx_ready=digit4(k>>6);check();end
if(unknown_checks==0 || idle_event_checks==0 || held_checks==0)$fatal(1,"coverage missing");
$display("PASS COMPLETE_MODULE_FOUR_STATE synth=%0d checks=%0d unknown_rate=%0d idle_event=%0d held_request=%0d",SYNTH,checks,unknown_checks,idle_event_checks,held_checks);finished=1;
end
endmodule
module tb;
wire m_done,w_done;complete_case #(.SYNTH(1)) m(m_done);complete_case #(.SYNTH(0)) w(w_done);
initial begin wait(m_done && w_done);$display("PASS COMPLETE_MODULE_ALL_FOUR_STATE");$finish;end
initial begin #1000000;$fatal(1,"timeout");end
endmodule
'''
(out/'tb.sv').write_text(tb)
base_sources=runtime_sources(PROJECT,out/'tb.sv')
base_sources=[p for p in base_sources if p != ROOT/'rtl/audio/gw138k_event_workstation.sv']+[out/'current_reference.sv']
maintained_names={p.name for p in base_sources if p.is_relative_to(ROOT)}
base_sources=[p for p in base_sources if not (p.parent==PROJECT/'rtl/audio/delay_ddr' and p.name in maintained_names)]
unadapted_inputs=list(base_sources)
adapted_sources=[]
for index,p in enumerate(base_sources):
 if p.name in ['workstation_runtime_oscillator_engine.sv','workstation_runtime_stereo_effects.sv','workstation_runtime_delay_effect_ddr.sv']:
  target=out/('compatibility-'+p.name);target.write_text(adapt(p.read_text(),p.name));adapted_sources.append(target)
 else:adapted_sources.append(p)
base_sources=adapted_sources
variant=EVENT.read_text()
mutants={'positive':variant,'wrong_casex_unknown_rate':variant.replace('case ({rate_commit_i,busy,event_rate_commit_i})','casex ({rate_commit_i,busy,event_rate_commit_i})'),'wrong_no_event_fence':variant.replace("case ({rate_commit_i,busy,event_rate_commit_i})\n        3'b101:","case ({rate_commit_i,busy})\n        2'b10:"),'wrong_idle_ready_ignores_event':variant.replace("case ({rate_commit_i,busy,event_rate_commit_i})\n        3'b101:","case ({busy})\n        1'b0:"),'wrong_lifecycle_veto_removed':variant.replace('!usb_lifecycle && fx_config_ready;','fx_config_ready;'),'wrong_fault_veto_removed':variant.replace("3'b101: public_rate_ready=rst_ni && !runtime_fault && pipeline_quiet", "3'b101: public_rate_ready=rst_ni && pipeline_quiet")}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'passed':False,'scope':'complete real M/W event modules, original/current reference, forced stored-state/queued-event boundary operands, four-state controls; full sequential service miter separate','cases':[],'hardware_accepted':False,'physical_timing_verified':False}
try:
 for label,text in mutants.items():
  d=out/label;d.mkdir();(v:=d/'gw138k_event_workstation.sv').write_text(adapt(text,'gw138k_event_workstation.sv'))
  cmd=['iverilog','-g2012','-s','tb','-o',str(d/'test.vvp'),'-I'+str(ROOT),'-I'+str(PROJECT),*map(str,base_sources),str(v)]
  cp=subprocess.run(cmd,cwd=PROJECT,capture_output=True,text=True,timeout=120);(d/'compile.log').write_text(cp.stdout+cp.stderr)
  assert cp.returncode==0,label+' compile '+cp.stderr[-2000:]
  run=subprocess.run(['vvp',str(d/'test.vvp')],cwd=PROJECT,capture_output=True,text=True,timeout=120);(d/'run.log').write_text(run.stdout+run.stderr)
  if label=='positive':assert run.returncode==0 and 'PASS COMPLETE_MODULE_ALL_FOUR_STATE'in run.stdout,run.stdout+run.stderr
  else:assert run.returncode!=0 and 'COMPLETE_MODULE mismatch'in run.stdout,label+' did not fail '+run.stdout
  result['cases'].append({'label':label,'exit':run.returncode,'source_sha256':sha(v),'run_log':str(d/'run.log'),'output':run.stdout});print(label,run.returncode,flush=True)
 result['passed']=True
finally:
 result['declaration_adaptations']=adaptation_records;result['input_sha256']={str(p):sha(p)for p in list(dict.fromkeys(base_sources+unadapted_inputs+[ROOT/'rtl/audio/gw138k_event_workstation.sv',REFERENCE,Path(__file__).resolve()]))};(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
