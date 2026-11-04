#!/usr/bin/env python3
"""Real public SPI/FAT/WAV/PCM oracle for unselected native direct composition."""
from pathlib import Path
import argparse,collections,concurrent.futures,hashlib,importlib.util,json,re,struct,subprocess
ROOT=Path(__file__).resolve().parents[2]
SIM=ROOT/'sim/tf_audio';RTL=ROOT/'rtl/tf_audio'
SOURCES=[RTL/'workstation_tf_direct_native_v1.sv',RTL/'workstation_tf_direct_ingress_v1.sv',RTL/'storage/workstation_tf_file_reader.sv',RTL/'storage/workstation_tf_sd_sector_reader.sv',RTL/'storage/workstation_tf_spi_session.sv',RTL/'storage/workstation_tf_wav_pcm_decoder_v1.sv',RTL/'storage/workstation_tf_wav_chunk_parser_v1.sv']
TB=SIM/'workstation_tf_direct_native_wire_tb.sv';CARD=SIM/'workstation_tf_file_wire_card.sv'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def le(buf,offset,value,width):buf[offset:offset+width]=value.to_bytes(width,'little')
def load_builder():
 spec=importlib.util.spec_from_file_location('direct_oracle',SIM/'run_workstation_tf_direct_ingress.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module.build
BUILD=load_builder()
def disk(folder,fs,partition,rate,frames0,frames1,mode):
 base=8 if partition else 0;spf=17 if fs==16 else 513;root_n=2 if fs==16 else 0;clusters=4096 if fs==16 else 65536
 data_base=base+1+spf+root_n;total=1+spf+root_n+clusters;blocks={};boot=bytearray(512);boot[0]=0xeb;boot[2]=0x90;le(boot,11,512,2);boot[13]=1;le(boot,14,1,2);boot[16]=1
 le(boot,17,32 if fs==16 else 0,2);le(boot,19,total if fs==16 else 0,2);le(boot,32,total if fs==32 else 0,4);le(boot,22,spf if fs==16 else 0,2);le(boot,36,spf if fs==32 else 0,4);le(boot,44,2 if fs==32 else 0,4);boot[86]=ord('2');boot[510:]=b'\x55\xaa';blocks[base]=boot
 if partition:
  mbr=bytearray(512);mbr[450]=0x0e if fs==16 else 0x0c;le(mbr,454,base,4);le(mbr,458,total,4);mbr[510:]=b'\x55\xaa';blocks[0]=mbr
 def fat(cluster,value):
  width=2 if fs==16 else 4;offset=cluster*width;lba=base+1+offset//512;buf=blocks.setdefault(lba,bytearray(512));le(buf,offset%512,value,width)
 end=0xfff9 if fs==16 else 0x0ffffff9;fat(0,end);fat(1,end)
 root=base+1+spf if fs==16 else data_base
 blocks[root]=bytearray(512)
 if fs==16:blocks[root+1]=bytearray(512)
 else:fat(2,end)
 raw_files=[];oracles=[]
 for index,count in enumerate((frames0,frames1)):
  actual_rate=(44100 if rate==48000 else 48000) if mode in (5,14,15,16) and index==0 else rate
  wav,oracle=BUILD(actual_rate,2,16,count,fmtlen=40 if index else 18)
  if index==1:
   data=wav.index(b'data')+8;mutable=bytearray(wav)
   for offset in range(count*4):mutable[data+offset]^=255
   wav=bytes(mutable);oracle=[x^0xffffffff for x in oracle]
  if mode==7 and index==0:wav=wav[:-7]
  if mode==9 and index==0:wav=b''
  chain=[3+index+i*4 for i in range((len(wav)+511)//512)]
  for i,cluster in enumerate(chain):fat(cluster,chain[i+1] if i+1<len(chain) else end);blocks[data_base+cluster-2]=bytearray(wav[i*512:(i+1)*512].ljust(512,b'\xcc'))
  entry=index*32;blocks[root][entry:entry+11]=(b'FIRST   WAV' if index==0 else b'SECOND  WAV');blocks[root][entry+11]=0x20;le(blocks[root],entry+26,chain[0] if chain else 0,2);le(blocks[root],entry+28,len(wav),4)
  raw_files.append(wav);oracles.append(oracle)
 folder.mkdir(parents=True,exist_ok=False);ordered=sorted(blocks);assert len(ordered)<=512
 image=bytearray(262144);lbas=[0xffffffff]*512
 for i,lba in enumerate(ordered):image[i*512:(i+1)*512]=blocks[lba];lbas[i]=lba
 (folder/'image.hex').write_text(''.join(f'{v:02x}\n' for v in image));(folder/'lbas.hex').write_text(''.join(f'{v:08x}\n' for v in lbas))
 for i,oracle in enumerate(oracles):(folder/f'oracle{i}.hex').write_text(''.join(f'{v:08x}\n' for v in oracle))
 manifest=dict(fs=fs,MBR=partition,rate=rate,mode=mode,file_lengths=list(map(len,raw_files)),frames=[frames0,frames1],blocks={str(lba):hashlib.sha256(data).hexdigest() for lba,data in sorted(blocks.items())})
 (folder/'disk.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');return manifest

def scenarios():
 result=[]
 for fs in (16,32):
  for partition in (False,True):
   for rate in (48000,44100):result.append((f'fat{fs}_{"mbr" if partition else "super"}_{rate}',fs,partition,rate,0,3800))
 for mode,name,count in [(1,'pause_full_backpressure',7000),(2,'live_switch_pending_cancel',3800),(3,'stop_payload_restart',3800),(4,'card_removal_reset',3800),(5,'rate_failure_drain_restart',3800),(6,'invalid_track_terminal',3800),(7,'truncated_WAV_restart',97),(8,'stop_apply_priority',3800),(9,'stop_empty_apply_EOF',0),(10,'pause_probe_removal',7000),(11,'stop_error_priority',3800),(12,'stop_pulse_drain_fence',3800),(13,'default_FAST12_supply_underrun',11000),(14,'stop_after_failed_drain',3800),(15,'stop_with_failed_drain_ACK',3800),(16,'failure_stop_overlap',3800)]:result.append((name,16,False,48000,mode,count))
 return result

def no_DDR_closure(binary):
 text=binary.read_text();nodes={};current=None
 for line in text.splitlines():
  m=re.match(r'(\S+) \.scope module, "([^"]+)" "([^"]+)" (.*);',line)
  if m:
   parent=re.search(r', (S_\w+)$',m[4]);current=m[1];nodes[current]=dict(instance=m[2],module=m[3],parent=parent[1] if parent else None,ports=[])
  elif '.scope ' in line:current=None
  elif current:
   port=re.search(r'\.port_info .* "([^"]+)";',line)
   if port:nodes[current]['ports'].append(port[1])
 roots=[key for key,node in nodes.items() if node['module']=='workstation_tf_direct_native_v1'];assert len(roots)==1
 def child(key):
  while key is not None:
   if key==roots[0]:return True
   key=nodes[key]['parent']
  return False
 closure=[node for key,node in nodes.items() if child(key)]
 counts=dict(collections.Counter(node['module'] for node in closure))
 expected={path.stem:1 for path in SOURCES}
 if counts!=expected:raise ValueError('unexpected composed module/request source '+str(counts))
 forbidden=[(node['module'],port) for node in closure for port in node['ports'] if re.search(r'(?:^|_)ddr(?:_|$)|(?:^|_)app_(?:cmd|addr|wdf)|memory_request',port,re.I)]
 if forbidden:raise ValueError('DDR request API appeared '+str(forbidden))
 return dict(scope='elaborated workstation_tf_direct_native_v1 and all seven RTL module instances only',module_counts=counts,port_count=sum(len(node['ports']) for node in closure),DDR_request_ports=[],DDR_request_sources=0,single_SD_sector_owner=counts['workstation_tf_sd_sector_reader']==1,single_SPI_session=counts['workstation_tf_spi_session']==1,VVP_sha256=sha(binary),whole_workstation_owner4_trace=False)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--case',action='append');ap.add_argument('--no-negatives',action='store_true');args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 inputs=[*SOURCES,TB,CARD,Path(__file__).resolve(),SIM/'run_workstation_tf_direct_ingress.py',RTL/'workstation_tf_direct_ingress.provenance.json',RTL/'storage/workstation_tf_file_reader.provenance.json']
 hashes={str(p):sha(p) for p in inputs};result=dict(schema=1,passed=False,input_sha256=hashes,cases={},negative_controls={},real_SPI_FAT_WAV_PCM=True,public_ports_only=True,profile_selected=False,whole_workstation_owner4_trace_verified=False,physical_EOF_success_verified=False,implementation_tools_invoked=False,hardware_operated=False,deployment_allowed=False)
 def execute(case,source=None,negative=None):
  name,fs,partition,rate,mode,count=case;folder=out/name;manifest=disk(folder,fs,partition,rate,count,97,mode)
  command=['iverilog','-g2012','-s','tb_workstation_tf_direct_native_wire','-o',str(folder/'sim.vvp'),'-Ptb_workstation_tf_direct_native_wire.MODE='+str(mode),'-Ptb_workstation_tf_direct_native_wire.RATE='+str(rate),'-Ptb_workstation_tf_direct_native_wire.FRAMES0='+str(count)]
  if mode==10:command+=['-Ptb_workstation_tf_direct_native_wire.PROBE=10000']
  command+=list(map(str,[source or SOURCES[0],*SOURCES[1:],TB,CARD]));p=subprocess.run(command,capture_output=True,text=True,timeout=60);(folder/'compile.log').write_text(p.stdout+p.stderr)
  if p.returncode:raise ValueError(name+' compile '+p.stdout+p.stderr)
  closure=no_DDR_closure(folder/'sim.vvp');(folder/'scope.json').write_text(json.dumps(closure,sort_keys=True,indent=2)+'\n')
  argv=['vvp',str(folder/'sim.vvp'),'+IMAGE='+str(folder/'image.hex'),'+LBAS='+str(folder/'lbas.hex'),'+ORACLE0='+str(folder/'oracle0.hex'),'+ORACLE1='+str(folder/'oracle1.hex')]
  p=subprocess.run(argv,capture_output=True,text=True,timeout=240);log=p.stdout+p.stderr;(folder/'run.log').write_text(log)
  if negative:
   if p.returncode==0 or negative not in log or 'timeout' in log:raise ValueError(name+' negative escaped/unrelated '+log)
  elif p.returncode or 'PASS direct_native_wire' not in log:raise ValueError(name+' failed '+log)
  record=dict(no_DDR_scope=closure,passed=not negative,rejected=bool(negative),disk=manifest,metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)},compile_argv=command,run_argv=argv,run_log_sha256=sha(folder/'run.log'),compile_log_sha256=sha(folder/'compile.log'))
  print(('PASS negative ' if negative else 'PASS ')+name,flush=True);return name,record
 try:
  lint=out/'source_lint.log'
  with lint.open('w') as stream:subprocess.run(['verilator','--lint-only','--timing','-Wno-fatal','--top-module','workstation_tf_direct_native_v1',*map(str,SOURCES)],check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=30)
  warnings=re.findall(r'^%Warning-([^:]+): ([^\n]+)',lint.read_text(),re.M)
  owned=[(kind,text) for kind,text in warnings if SOURCES[0].name+':' in text]
  if owned:raise ValueError('new owning wrapper lint warnings '+str(owned))
  result['owned_warnings']=owned;result['unchanged_dependency_warnings']=warnings
  legacy=(RTL/'workstation_tf_runtime_service.sv').read_text().split(');',1)[0]
  result['real_legacy_DDR_interface_control']=bool(re.search(r'output wire .*ddr_valid',legacy))
  if not result['real_legacy_DDR_interface_control']:raise ValueError('legacy DDR interface control absent')
  cases=[c for c in scenarios() if args.case is None or c[0] in args.case]
  if not cases:raise ValueError('empty case selection')
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   for name,record in pool.map(execute,cases):result['cases'][name]=record
  # Each source mutation is made only in the new evidence directory.
  if not args.no_negatives and args.case is None:
   text=SOURCES[0].read_text();by={c[0]:c for c in scenarios()}
   controls=[
    ('raw_request_pins','.generation_i(held_generation),.expected_rate_i(held_rate)','.generation_i(generation_i),.expected_rate_i(expected_rate_i)','fat16_super_48000','playback failed before wire PCM'),
    ('cancel_before_apply','.cancel_i(reader_stop)','.cancel_i(reader_stop || accept_fire)','live_switch_pending_cancel','request revoked old session before actual apply'),
    ('failed_drain_admission','(!failure_hold || quiet)',"1'b1",'rate_failure_drain_restart','failed source admitted before real cancellation drain'),
    ('invalid_slot_no_terminal','if(file_error_o && slot_pending)',"if(1'b0)",'invalid_track_terminal','invalid track slot lacked failure terminal'),
    ('stop_wait_removed','!stop_i && !stop_wait',"!stop_i && 1'b1",'stop_pulse_drain_fence','stop pulse admitted before CRC drain ACK'),
    ('ungated_file_EOF','assign file_eof_o=reader_eof && !reader_stop && !file_error_o;','assign file_eof_o=reader_eof;','stop_empty_apply_EOF','cancel/EOF or byte/EOF overlap'),
    ('rearm_held_failed_stop','!(failure_hold && quiet) && !file_error_o',"1'b1 && !file_error_o",'stop_after_failed_drain','post-failure-drain stop pulse stuck request readiness'),
    ('rearm_stop_on_ACK',' && !reader_cancelled','','stop_with_failed_drain_ACK','stop/ACK collision stuck request readiness'),
    ('failure_stop_late_rearm','if(ingress_failed_o)begin failure_hold<=1;failure_seen<=1;end',"if(1'b0)begin failure_hold<=1;failure_seen<=1;end",'failure_stop_overlap','failure/stop overlap did not retain one drain/stop terminal'),
    ('missing_cached_stop_terminal','else if(reader_cancelled || (failure_hold && quiet))stop_completed_o<=1;','else if(reader_cancelled)stop_completed_o<=1;','stop_after_failed_drain','post-failure-drain stop pulse stuck request readiness'),
    ('missing_failed_stop_terminal','if(file_error_o)begin stop_wait<=0;stop_failed_o<=1;stop_completed_o<=0;end','if(file_error_o)begin stop_wait<=0;stop_failed_o<=0;stop_completed_o<=0;end','stop_error_priority','stop/file-error terminal priority'),
   ]
   for name,old,new,case,error in controls:
    if text.count(old)!=1:raise ValueError('negative anchor drift '+name)
    path=out/(name+'.sv');path.write_text(text.replace(old,new));spec=list(by[case]);spec[0]='negative_'+name;key,record=execute(tuple(spec),path,error);result['negative_controls'][key]=record
  if args.case is None and not args.no_negatives:
   injected=out/'injected_DDR_source.sv';text=SOURCES[0].read_text();anchor='    reg slot_pending,'
   if text.count(anchor)!=1:raise ValueError('DDR closure negative anchor drift')
   injected.write_text(text.replace(anchor,'    injected_DDR_request_source forbidden(.ddr_valid_o());\n'+anchor)+'\nmodule injected_DDR_request_source(output wire ddr_valid_o);assign ddr_valid_o=1;endmodule\n')
   binary=out/'injected_DDR_source.vvp';subprocess.run(['iverilog','-g2012','-s','workstation_tf_direct_native_v1','-o',str(binary),*map(str,[injected,*SOURCES[1:]])],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
   try:no_DDR_closure(binary)
   except ValueError as error:result['injected_DDR_source_rejected']=dict(rejected=True,error=str(error))
   else:raise ValueError('injected actual elaborated DDR requester escaped')
  if {str(p):sha(p) for p in inputs}!=hashes:raise ValueError('source input drift')
  result['passed']=True
 finally:(out/'verification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
 print(json.dumps(dict(passed=True,cases=len(result['cases']),negative_controls=len(result['negative_controls']))))
if __name__=='__main__':main()
