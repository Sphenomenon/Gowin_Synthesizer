#!/usr/bin/env python3
"""Unselected maintained file owner against real SPI/FAT16/FAT32 disks."""
import argparse,concurrent.futures,hashlib,json,re,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
NATIVE='rtl/tf_audio/storage/workstation_tf_file_reader.sv'
PROVENANCE='rtl/tf_audio/storage/workstation_tf_file_reader.provenance.json'
ORIGIN='rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v'
SECTOR='rtl/tf_audio/storage/workstation_tf_sd_sector_reader.sv'
SESSION='rtl/tf_audio/storage/workstation_tf_spi_session.sv'
CARD='sim/tf_audio/workstation_tf_file_wire_card.sv'
TB='sim/tf_audio/workstation_tf_file_reader_wire_tb.sv'
LOCKS={ORIGIN:'57ee8873418fe2fa00e40782e1509495c8eb779e11d4175884a79f741fcc0441',SECTOR:'8f1961c951f3622ed6253bf0b1c42879f5b1950bc6a9e4a5ef40b5a01b546110',SESSION:'704e9b62caa4ef79c01f1d2b4c1c61b2e2bd55f93c83ae90bb573c9e71c0a6c8'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def provenance(root=ROOT,*,direct_crc_source_adaptation=False,direct_fat_cache_source_adaptation=False):
 p=json.loads((root/PROVENANCE).read_text());original=(root/ORIGIN).read_bytes();native=(root/NATIVE).read_bytes()
 actual_native_sha256=hashlib.sha256(native).hexdigest();adaptation=None;restored={}
 if direct_crc_source_adaptation or direct_fat_cache_source_adaptation:
  import sys
  sys.path.insert(0,str(root))
  from tools.workstation_tf_sd_crc16_provenance import validate_adaptation
  adaptation,restored=validate_adaptation(root,fat_cache_source_adaptation=direct_fat_cache_source_adaptation)
  native=restored[NATIVE]
 if hashlib.sha256(original).hexdigest()!=p['origin_sha256'] or hashlib.sha256(native).hexdigest()!=p['native_sha256']:raise ValueError('file-owner source identity drift')
 s=original.decode()
 for e in p['forward_edits']:
  if s.count(e['before'])!=e['count']:raise ValueError('file-owner exact forward anchor drift')
  s=s.replace(e['before'],e['after'])
 if (p['header']+s+p['suffix']).encode()!=native:raise ValueError('unexpected maintained file-owner difference')
 s=native.decode();assert s.startswith(p['header']) and s.endswith(p['suffix']);s=s[len(p['header']):-len(p['suffix'])]
 for e in reversed(p['forward_edits']):
  if s.count(e['after'])!=e['count']:raise ValueError('file-owner exact reverse anchor drift')
  s=s.replace(e['after'],e['before'])
 if s.encode()!=original:raise ValueError('file-owner reverse restoration mismatch')
 for name,value in LOCKS.items():
  actual=hashlib.sha256(restored[name]).hexdigest() if name in restored else sha(root/name)
  if actual!=value:raise ValueError('locked reader/transport drift: '+name)
 return dict(exact_forward_and_reverse=True,edits=len(p['forward_edits']),original_sha256=sha(root/ORIGIN),native_sha256=actual_native_sha256,original_manifest_native_sha256=p['native_sha256'],explicit_DIRECT_crc_source_adaptation=adaptation,GPL_notices_and_original_bytes_retained=True)
def le(a,o,v,n):a[o:o+n]=int(v).to_bytes(n,'little')
def disk(folder,fs=16,mbr=False,fault=None,large=False,eoc=0xfffffff9):
 base=8 if mbr else 0;root_entries=4113 if large else 17;root_n=(root_entries+15)//16 if fs==16 else 0
 spf=17 if fs==16 else 513;clusters=4096 if fs==16 else 65536;data_offset=1+spf+root_n;total=data_offset+clusters
 first_data=base+data_offset;root=base+1+spf if fs==16 else first_data
 blocks={};boot=bytearray(512);boot[0]=0xeb;boot[2]=0x90;le(boot,11,512,2);boot[13]=1;le(boot,14,1,2);boot[16]=1
 le(boot,17,root_entries if fs==16 else 0,2);le(boot,19,total if fs==16 else 0,2);le(boot,32,total if fs==32 else 0,4)
 le(boot,22,spf if fs==16 else 0,2);le(boot,36,spf if fs==32 else 0,4);le(boot,44,0xa0000002 if fs==32 else 0,4);boot[86]=ord('2');boot[510:]=b'\x55\xaa'
 if fault=='bps':le(boot,11,1024,2)
 if fault=='spc0':boot[13]=0
 if fault=='spc3':boot[13]=3
 if fault=='nfats':boot[16]=3
 if fault=='reserved0':le(boot,14,0,2)
 if fault=='total0':le(boot,19,0,2);le(boot,32,0,4)
 if fault=='smallfat':le(boot,22,1 if fs==16 else 0,2);le(boot,36,1 if fs==32 else 0,4)
 if fault=='fatflags':le(boot,40,0x81,2)
 if fault=='fatversion':le(boot,42,1,2)
 if fault=='rootcluster':le(boot,44,1,4)
 if fault=='dbrsig':boot[511]=0
 if fault=='geometry_overflow':le(boot,32,0xffffffff,4)
 blocks[base]=boot
 if mbr:
  b=bytearray(512);b[450]=0x0e if fs==16 else 0x0c;le(b,454,base,4);le(b,458,total,4);b[510:]=b'\x55\xaa'
  if fault=='mbrjmp':b[0]=0xeb;b[2]=0x90
  if fault=='mbrsig':b[510]=0
  if fault=='partition_type':b[450]=0x83
  if fault=='partition_start':le(b,454,0,4)
  if fault=='partition_size':le(b,458,0,4)
  if fault=='partition_overflow':le(b,458,0xffffffff,4)
  blocks[0]=b
 elif fault=='mbrsig':boot[510]=0
 fat=bytearray(512)
 def entry(k,value):le(fat,k*(2 if fs==16 else 4),value,2 if fs==16 else 4)
 end=0xfff9 if fs==16 else eoc
 for k,v in ((0,0xfff8 if fs==16 else 0x0ffffff8),(1,0xffff if fs==16 else 0x0fffffff),(2,9),(3,0xb0000007 if fs==32 else 7),(4,end),(7,end),(9,end)):entry(k,v)
 if fault=='early_eoc':entry(3,end)
 if fault=='free_cluster':entry(3,0)
 if fault=='bad_cluster':entry(3,0xfff7 if fs==16 else 0xfffffff7)
 if fault=='reserved_cluster':entry(3,0xfff0 if fs==16 else 0xfffffff0)
 if fault=='range_cluster':entry(3,6000 if fs==16 else 70000)
 if fault=='cycle':entry(7,3)
 if fault=='self_cycle':entry(7,7)
 if fault=='root_bad':entry(2,1)
 if fault=='root_cycle':entry(2,2)
 blocks[base+1]=fat
 def directory():
  d=bytearray(512)
  for off in range(0,512,32):d[off]=0xe5
  return d
 def dent(d,slot,name,cluster,size):
  off=slot*32;d[off:off+11]=name;d[off+11]=0x20;le(d,off+20,(cluster>>16)&0xffff,2);le(d,off+26,cluster&0xffff,2);le(d,off+28,size,4)
 size0=0 if fault in ('empty','empty_bad_cluster') else 700
 if fs==16:
  for i in range(root_n):blocks[root+i]=directory()
  dent(blocks[root],0,b'FIRST   WAV',(1 if fault=='empty_bad_cluster' else 0) if size0==0 else 0xab000003,size0)
  dent(blocks[root+root_n-1],0,b'SECOND  WAV',4,257)
  # Slot after declared partial root count must never enter the playlist.
  dent(blocks[root+root_n-1],1,b'PHANTOM WAV',5,8)
 else:
  blocks[root]=directory();blocks[first_data+7]=directory()
  dent(blocks[root],0,b'FIRST   WAV',(1 if fault=='empty_bad_cluster' else 0) if size0==0 else 0xa0000003,size0)
  dent(blocks[first_data+7],0,b'SECOND  WAV',0xb0000004,257)
 if fault=='no_tracks':
  for lba in ([root+i for i in range(root_n)] if fs==16 else [root,first_data+7]):blocks[lba]=directory()
 for cluster,start,length,track in ((3,0,512,0),(7,512,188,0),(4,0,257,1)):
  d=bytearray([0xcc]*512)
  for i in range(length):d[i]=((start+i)*13+0x31 if track==0 else i*7+0xa0)&255
  blocks[first_data+cluster-2]=d
 folder.mkdir(parents=True,exist_ok=False);ordered=sorted(blocks);assert len(ordered)<=512
 image=bytearray(262144);lbas=[0xffffffff]*512
 for i,lba in enumerate(ordered):lbas[i]=lba;image[i*512:(i+1)*512]=blocks[lba]
 (folder/'image.hex').write_text('\n'.join(f'{v:02x}' for v in image)+'\n');(folder/'lbas.hex').write_text('\n'.join(f'{v:08x}' for v in lbas)+'\n')
 manifest=dict(fs=fs,MBR=mbr,fault=fault,root_entries=root_entries,root_sectors=root_n,logical_total_sectors=total,first_data=first_data,blocks={str(k):hashlib.sha256(v).hexdigest() for k,v in sorted(blocks.items())},file0_bytes=size0,file1_bytes=257)
 (folder/'disk.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest

def scenarios():
 s=[('fat16_super',dict(fs=16),{}),('fat16_mbr',dict(fs=16,mbr=True),{}),('fat32_super',dict(fs=32),{}),('fat32_mbr',dict(fs=32,mbr=True),{}),('fat32_MBR_JMP',dict(fs=32,mbr=True,fault='mbrjmp'),{}),('fat16_large_root',dict(fs=16,large=True),dict(MAX_ROOT=300))]
 for k in range(0x8,0x10):s.append(('fat32_EOC_'+hex(k)[2:],dict(fs=32,eoc=0xfffffff0+k),{}))
 for fault in ('mbrsig','partition_type','partition_start','partition_size','partition_overflow'):
  s.append((fault,dict(fs=16,mbr=True,fault=fault),dict(MODE=1,EXPECT_ERROR=3)))
 for fault in ('bps','spc0','spc3','nfats','reserved0','total0','smallfat','dbrsig'):
  s.append(('fat16_'+fault,dict(fs=16,mbr=(fault=='dbrsig'),fault=fault),dict(MODE=1,EXPECT_ERROR=4)))
 for fault in ('fatflags','fatversion','rootcluster','geometry_overflow'):
  s.append(('fat32_'+fault,dict(fs=32,fault=fault),dict(MODE=1,EXPECT_ERROR=4)))
 for fs in (16,32):
  for fault,code in (('early_eoc',6),('free_cluster',5),('bad_cluster',5),('reserved_cluster',5),('range_cluster',5),('cycle',9),('self_cycle',9)):
   s.append((f'fat{fs}_{fault}',dict(fs=fs,fault=fault),dict(MODE=2,EXPECT_ERROR=code)))
 s.extend([('root_bad',dict(fs=32,fault='root_bad'),dict(MODE=1,EXPECT_ERROR=5)),('root_cycle_limit',dict(fs=32,fault='root_cycle'),dict(MODE=1,EXPECT_ERROR=7,MAX_ROOT=4)),('empty',dict(fs=16,fault='empty'),dict(MODE=3,SIZE0=0)),('empty_bad_cluster',dict(fs=16,fault='empty_bad_cluster'),dict(MODE=2,EXPECT_ERROR=5,SIZE0=0)),('invalid_track',dict(fs=16),dict(MODE=4,EXPECT_ERROR=8)),('no_tracks',dict(fs=16,fault='no_tracks'),dict(MODE=4,EXPECT_ERROR=8,EXPECT_TRACKS=0)),('missing_init',dict(fs=16),dict(MODE=5,EXPECT_ERROR=2)),('idle_probe_removal',dict(fs=16),dict(MODE=6,EXPECT_ERROR=1,PROBE=2000))])
 for k in (1,2,3):s.append(('file_transport_'+str(k),dict(fs=16),dict(MODE=2,EXPECT_ERROR=1,INITIAL_FAULT_KIND=k,INITIAL_FAULT_LBA=21)))
 return s

def run(output,only=None,*,direct_crc_source_adaptation=False,direct_fat_cache_source_adaptation=False):
 output.mkdir(parents=True,exist_ok=False);proof=provenance(direct_crc_source_adaptation=direct_crc_source_adaptation,direct_fat_cache_source_adaptation=direct_fat_cache_source_adaptation);sources=[NATIVE,PROVENANCE,ORIGIN,SECTOR,SESSION,CARD,TB,'sim/tf_audio/run_workstation_tf_file_reader_wire.py','rtl/tf_audio/storage/tang_mp3/LICENSE','rtl/tf_audio/storage/WORKSTATION_TF_FILE_READER_CONTRACT.md','rtl/tf_audio/storage/workstation_tf_sd_sector_reader.provenance.json']
 if direct_crc_source_adaptation or direct_fat_cache_source_adaptation:sources += ['rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.adaptation.json','tools/workstation_tf_sd_crc16_provenance.py','rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.sv']
 if direct_fat_cache_source_adaptation:sources += ['rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.adaptation.json','tools/workstation_tf_fat_cache_provenance.py','rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.sv','rtl/tf_audio/workstation_tf_direct_native_v1.sv','rtl/tf_audio/workstation_tf_direct_runtime_service.sv']
 hashes={p:sha(ROOT/p) for p in sources};result=dict(schema=1,passed=False,source_sha256=hashes,provenance=proof,wire_model='Real mode-0 SPI edges and constructed sparse FAT16/FAT32 disks; no DUT hierarchy force/deposit or session stub',profile_selected=False,CRC_validated=False,FAT_cache_implemented=False,PCM_ingress_implemented=False,no_DDR_profile=False,throughput_qualified=False,m03_complete=False,synthesis=False,pnr=False,hardware_tested=False,sram_programmed=False,flash_written=False,cases={},negative_controls={})
 def execute(case,config,parameters,source=None,expected_failure=None):
  folder=output/case;manifest=disk(folder,**config);path=source or ROOT/NATIVE
  cmd=['iverilog','-g2012','-Wall','-s','tb_workstation_tf_file_reader_wire','-o',str(folder/'sim.vvp')]
  cmd+=['-Ptb_workstation_tf_file_reader_wire.'+k+'='+str(v) for k,v in parameters.items()];cmd +=[str(path),str(ROOT/SECTOR),str(ROOT/SESSION),str(ROOT/CARD),str(ROOT/TB)]
  c=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(folder/'compile.log').write_text(c.stdout+c.stderr)
  if c.returncode:raise RuntimeError(case+' compile: '+c.stdout+c.stderr)
  argv=['vvp',str(folder/'sim.vvp'),'+IMAGE='+str(folder/'image.hex'),'+LBAS='+str(folder/'lbas.hex')];p=subprocess.run(argv,capture_output=True,text=True,timeout=240);log=p.stdout+p.stderr;(folder/'run.log').write_text(log)
  record=dict(parameters=parameters,disk=manifest,compile_argv=cmd,run_argv=argv,returncode=p.returncode,source_sha256=sha(path),compile_log_sha256=sha(folder/'compile.log'),run_log_sha256=sha(folder/'run.log'),run_log=log,metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)})
  if expected_failure:
   record.update(expected_failure=expected_failure,rejected=p.returncode!=0 and expected_failure in log)
   if not record['rejected']:raise RuntimeError(case+' negative escaped or unrelated failure: '+log)
  elif p.returncode or 'PASS workstation_tf_file_reader_wire:' not in log:raise RuntimeError(case+' failed: '+log)
  print(('PASS negative ' if expected_failure else 'PASS ')+case,flush=True);return case,record
 try:
  cases=scenarios();cases=[x for x in cases if only is None or x[0] in only]
  if not cases:raise ValueError('No selected fixture')
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   for name,record in pool.map(lambda args:execute(*args),cases):result['cases'][name]=record
  if only is None:
   text=(ROOT/NATIVE).read_text()
   def mutate(a,b):
    if text.count(a)!=1:raise ValueError('negative anchor drift')
    return text.replace(a,b)
   controls=[
    ('application_launch_overlap',mutate('!search_fat && !track_applied && card_stat==8', '!search_fat && card_stat==8'),dict(fs=16),{},'data sector overlaps track application'),
    ('sector_allow_bypass',mutate('    sector_allow && !start_req','    1\'b1 && !start_req'),dict(fs=16),{},'sector reservation contract'),
    ('early_EOF',mutate('else if(next_eoc) fail(ERR_EARLY_EOC);','else if(next_eoc) begin playing<=0;eof<=1;filesystem_state<=READY;end'),dict(fs=16,fault='early_eoc'),dict(MODE=2,EXPECT_ERROR=6),'error masqueraded as EOF'),
    ('FAT32_reserved_high_bits',mutate("{4'd0,target_cluster[27:0]}",'target_cluster'),dict(fs=32),{},'unexpected file error'),
    ('FAT16_cursor_wrap',mutate('rootdir_offset<=rootdir_offset+1;read_sector_no<=rootdir_sector+rootdir_offset+1;',"rootdir_offset<=(rootdir_offset+1)&16'h00ff;read_sector_no<=rootdir_sector+rootdir_offset+1;"),dict(fs=16,large=True),dict(MAX_ROOT=300),'mount failed'),
    ('last_cluster_not_checked',mutate('if(next_eoc) begin playing<=0;eof<=1;filesystem_state<=READY;end','if(1\'b1) begin playing<=0;eof<=1;filesystem_state<=READY;end'),dict(fs=16,fault='cycle'),dict(MODE=2,EXPECT_ERROR=9),'error masqueraded as EOF'),
   ]
   leaked=mutate('!probe_pending && !file_error && !stop && !stop_req && ~search_fat && fptr < file_size)', '!probe_pending && !file_error && !stop && !stop_req && fptr < file_size)')
   controls.append(('metadata_leak',leaked,dict(fs=16),{},'metadata/stale/unreserved file byte'))
   stopped=text.replace('assign outen=outen_q && rstn && !file_error && !stop && !stop_req;','assign outen=outen_q && rstn && !file_error;').replace('!probe_pending && !file_error && !stop && !stop_req && ~search_fat','!probe_pending && !file_error && ~search_fat')
   controls.append(('stop_late_byte',stopped,dict(fs=16),{},'metadata/stale/unreserved file byte'))
   for name,mutated,config,parameters,failure in controls:
    p=output/(name+'.sv');p.write_text(mutated);key,record=execute(name,config,parameters,p,failure);result['negative_controls'][key]=record
  if {p:sha(ROOT/p) for p in hashes}!=hashes:raise ValueError('source inputs changed during test')
  result['source_inputs_unchanged']=True;result['passed']=True
 finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--case',action='append');p.add_argument('--direct-crc-source-adaptation',action='store_true');p.add_argument('--direct-fat-cache-source-adaptation',action='store_true');a=p.parse_args();run(a.output.resolve(),a.case,direct_crc_source_adaptation=a.direct_crc_source_adaptation,direct_fat_cache_source_adaptation=a.direct_fat_cache_source_adaptation)
