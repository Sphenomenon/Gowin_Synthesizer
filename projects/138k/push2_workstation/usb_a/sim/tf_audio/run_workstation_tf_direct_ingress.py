#!/usr/bin/env python3
"""Independent WAV byte/PCM oracle for the unselected direct ingress v1."""
from pathlib import Path
import argparse,hashlib,itertools,json,re,struct,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def chunk(tag,data):return tag+struct.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')
def build(rate,channels,bits,count,fmtlen=16,metadata=True):
    raw=bytearray();oracle=[]
    for i in range(count):
        pair=[]
        for ch in range(channels):
            n=(i*1931+ch*23887)&65535
            if i<5:n=[0x8000,0xffff,0,1,0x7fff][i]^(0x1234 if ch else 0)
            signed=n if n<32768 else n-65536
            if bits==8:
                value=((signed>>8)+128)&255;raw.append(value);decoded=(value-128)<<8
            else:
                value=((signed&65535)<<(bits-16))|((i*73+ch*19)&((1<<(bits-16))-1))
                raw.extend(value.to_bytes(bits//8,'little'));decoded=int.from_bytes(value.to_bytes(bits//8,'little'), 'little',signed=True)>>(bits-16)
            pair.append(decoded&65535)
        if channels==1:pair.append(pair[0])
        oracle.append(pair[0]|(pair[1]<<16))
    fmt=struct.pack('<HHIIHH',1,channels,rate,rate*channels*(bits//8),channels*(bits//8),bits)
    if fmtlen==18:fmt+=b'\0\0'
    if fmtlen==40:fmt=struct.pack('<H',0xfffe)+fmt[2:]+struct.pack('<HHI',22,bits,3)+bytes.fromhex('0100000000001000800000aa00389b71')
    body=b'WAVE'+(chunk(b'JUNK',b'abc')+chunk(b'zero',b'') if metadata else b'')+chunk(b'fmt ',fmt)+chunk(b'data',bytes(raw))
    if metadata:body+=chunk(b'LIST',b'tail!')
    return b'RIFF'+struct.pack('<I',len(body))+body,oracle

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--positive-only',action='store_true');args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    owner=ROOT/'rtl/tf_audio/workstation_tf_direct_ingress_v1.sv'
    parser=ROOT/'rtl/tf_audio/storage/workstation_tf_wav_chunk_parser_v1.sv';decoder=parser.with_name('workstation_tf_wav_pcm_decoder_v1.sv')
    tb=Path(__file__).with_name('tb_workstation_tf_direct_ingress.sv');provenance=ROOT/'rtl/tf_audio/workstation_tf_direct_ingress.provenance.json'
    old=[parser.with_name(x) for x in ('tf_wav_chunk_parser.v','tf_wav_pcm_decoder.v','tf_audio_decoder_ip.v')]
    contract=ROOT/'rtl/tf_audio/WORKSTATION_TF_DIRECT_INGRESS_V1_CONTRACT.md'
    legacy_tbs=[tb.with_name(x+'.sv') for x in ('tb_tf_wav_chunk_parser','tb_tf_wav_pcm_decoder','tb_tf_wav_formats')]
    manifest=json.loads(provenance.read_text());patches=[ROOT/d['review_diff'] for d in manifest['derivations']]
    inputs=[owner,parser,decoder,tb,provenance,contract,Path(__file__).resolve(),*old,*legacy_tbs,*patches]
    before={str(p):sha(p) for p in inputs};result=dict(schema=1,passed=False,input_sha256=before,independent_python_PCM_oracle=True,
        real_maintained_WAV_kernel=True,selected_profile=False,implementation_tools_invoked=False,hardware_operated=False,release_ready=False,deployment_allowed=False,cases=[],negative_controls=[])
    vectors=[]
    def add(label,data,oracle,rate=48000,mode=0,failure=0):vectors.append(dict(label=label,data=data,oracle=oracle,rate=rate,mode=mode,failure=failure))
    for index,(rate,ch,bits) in enumerate(itertools.product((48000,44100),(1,2),(8,16,24,32))):
        data,oracle=build(rate,ch,bits,97,fmtlen=(16,18,40)[index%3]);add(f'{rate}_{ch}ch_{bits}bit',data,oracle,rate)
    data,oracle=build(48000,2,32,10000)
    for mode,label in [(1,'pause_backpressure'),(2,'cancel_restart_wrap'),(3,'real_underrun_restart'),(4,'unreserved_sector'),(5,'file_error'),(6,'overflow_fault_injection'),(7,'start_with_file_error')]:add(label,data,oracle,mode=mode)
    data,oracle=build(48000,1,8,0);add('empty_data',data,oracle)
    data,oracle=build(48000,1,8,1);add('one_frame_odd_pad',data,oracle)
    data,oracle=build(44100,2,16,13);add('rate_mismatch',data,oracle,48000,failure=5)
    data,oracle=build(48000,2,16,13);add('invalid_session_rate',data,oracle,32000,failure=5)
    data,oracle=build(32000,2,16,13);add('unsupported_file_rate',data,oracle,48000,failure=5)
    data,oracle=build(48000,2,24,13)
    for label,raw in [('empty_file',b''),('short_header',b'RIF'),('truncated_data',data[:70]),('truncated_tail',data[:-1]),('extra_after_RIFF',data+b'!'),('short_RIFF_size',data[:4]+struct.pack('<I',4)+data[8:])]:add(label,raw,oracle,failure=4)
    def fmt_bad(label,change):
        raw=bytearray(data);at=raw.index(b'fmt ')+8;change(raw,at);add(label,bytes(raw),oracle,failure=4)
    fmt_bad('float_codec',lambda raw,at:raw.__setitem__(slice(at,at+2),struct.pack('<H',3)))
    fmt_bad('invalid_channels_17',lambda raw,at:raw.__setitem__(slice(at+2,at+4),struct.pack('<H',17)))
    fmt_bad('invalid_bits_20',lambda raw,at:raw.__setitem__(slice(at+14,at+16),struct.pack('<H',20)))
    fmt_bad('rate_high_alias',lambda raw,at:raw.__setitem__(slice(at+4,at+8),struct.pack('<I',0x10000000+48000)))
    ext,ext_oracle=build(48000,2,16,13,fmtlen=40);bad=bytearray(ext);bad[bad.index(b'fmt ')+8+39]^=1;add('non_PCM_extensible_GUID',bytes(bad),ext_oracle,failure=4)
    # A complete container with an incomplete stereo frame must fail, even
    # though its RIFF/data byte sizes themselves match the actual file.
    good,_=build(48000,2,16,0,metadata=False);body=good[8:-8]+chunk(b'data',b'\x11\x22\x33');add('partial_PCM_frame',b'RIFF'+struct.pack('<I',len(body))+body,[],failure=4)
    good,orc=build(48000,1,16,3,metadata=False);body=good[8:]+chunk(b'data',b'\x34\x12');add('multiple_data_chunks',b'RIFF'+struct.pack('<I',len(body))+body,orc+[0x12341234])
    short,orc=build(48000,2,16,3,metadata=False);body=short[8:]+b'JUNK'+struct.pack('<I',0xffffffff)+b'!';add('chunk_size_odd_overflow',b'RIFF'+struct.pack('<I',len(body))+body,orc,failure=4)
    for vector in vectors:
        folder=out/vector['label'];folder.mkdir();(folder/'input.hex').write_text(''.join(f'{b:02x}\n' for b in vector['data']));(folder/'oracle.hex').write_text(''.join(f'{n:08x}\n' for n in vector['oracle']))
        vector['folder']=folder
    def compile_source(label,source,parser_source=None):
        binary=out/(label+'.vvp');cmd=['iverilog','-g2012','-s','tb_workstation_tf_direct_ingress','-o',str(binary),*map(str,[source,parser_source or parser,decoder,tb])]
        with (out/(label+'_compile.log')).open('w') as f:subprocess.run(cmd,check=True,stdout=f,stderr=subprocess.STDOUT,timeout=30)
        return binary
    def run(label,binary,vector,negative=False):
        folder=vector['folder'];cmd=['vvp',str(binary),'+input='+str(folder/'input.hex'),'+oracle='+str(folder/'oracle.hex'),'+length='+str(len(vector['data'])),'+frames='+str(len(vector['oracle'])),'+rate='+str(vector['rate']),'+mode='+str(vector['mode']),'+failure='+str(vector['failure'])]
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=45);(out/(label+'_run.log')).write_text(p.stdout)
        if negative:
            if p.returncode==0 or 'FATAL:' not in p.stdout or 'watchdog' in p.stdout:raise ValueError('negative was not rejected by a behavioral assertion: '+label+' '+p.stdout)
            result['negative_controls'].append(dict(label=label,rejected=True,case=vector['label'],error=p.stdout.strip()));return
        if p.returncode or 'PASS direct_ingress' not in p.stdout:raise ValueError(label+': '+p.stdout)
        metrics=dict((k,int(v)) for k,v in re.findall(r'(\w+)=(\d+)',p.stdout))
        result['cases'].append(dict(label=label,passed=True,metrics=metrics,input_bytes=len(vector['data']),oracle_frames=len(vector['oracle']),input_hex_sha256=sha(folder/'input.hex'),oracle_hex_sha256=sha(folder/'oracle.hex')))
        print(label+': '+p.stdout.strip(),flush=True)
    try:
        for d in manifest['derivations']:
            original=ROOT/d['original'];derived=ROOT/d['derived'];patch=ROOT/d['review_diff']
            if sha(original)!=d['original_sha256'] or sha(derived)!=d['derived_sha256'] or sha(patch)!=d['review_diff_sha256']:raise ValueError('WAV derivation drift')
            with tempfile.TemporaryDirectory() as temp:
                rebuilt=Path(temp)/derived.name
                subprocess.run(['patch','--batch','--silent','-o',str(rebuilt),'-i',str(patch),str(original)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                if sha(rebuilt)!=sha(derived):raise ValueError('WAV patch not reversible')
        result['exact_derivation_reconstruction']=True
        with (out/'source_lint.log').open('w') as f:subprocess.run(['verilator','--lint-only','--timing','-Wno-fatal','--top-module','workstation_tf_direct_ingress_v1',*map(str,[owner,parser,decoder])],check=True,stdout=f,stderr=subprocess.STDOUT,timeout=30)
        warnings=re.findall(r'^%Warning[^\n]*',(out/'source_lint.log').read_text(),re.M)
        if warnings:raise ValueError('new source lint warnings: '+str(warnings))
        result['source_lint_warnings']=warnings
        result['legacy_regressions']=[]
        for old_tb in legacy_tbs:
            binary=out/(old_tb.stem+'.vvp')
            with (out/(old_tb.stem+'_compile.log')).open('w') as f:subprocess.run(['iverilog','-g2012','-s',old_tb.stem,'-o',str(binary),*map(str,[*old[:2],old_tb])],check=True,stdout=f,stderr=subprocess.STDOUT,timeout=30)
            legacy=subprocess.run(['vvp',str(binary)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
            (out/(old_tb.stem+'_run.log')).write_text(legacy.stdout)
            if 'PASS '+old_tb.stem not in legacy.stdout or 'FAIL' in legacy.stdout:raise ValueError('legacy WAV regression failure '+old_tb.stem)
            result['legacy_regressions'].append(dict(test=old_tb.stem,passed=True))
        binary=compile_source('positive',owner)
        for vector in vectors:run(vector['label'],binary,vector)
        if not args.positive_only:
            text=owner.read_text();by_name={v['label']:v for v in vectors}
            variants=[
                ('sector_reservation_removed','used_bytes<=BYTE_DEPTH-512-SECTOR_PIPELINE_MARGIN','used_bytes<BYTE_DEPTH','pause_backpressure'),
                ('decoder_held_byte_bypassed','.in_byte(byte_held)', '.in_byte(file_byte_i)','48000_1ch_8bit'),
                ('PCM_last_removed','pcm_mem[pcm_wr]<={flush_tail,pending_pair}','pcm_mem[pcm_wr]<={1\'b0,pending_pair}','one_frame_odd_pad'),
                ('pause_consumes_head','active_o && !pause_i && pcm_held_valid','active_o && pcm_held_valid','pause_backpressure'),
                ('underrun_not_latched','failure_now=UNDERRUN;','failure_now=0;','real_underrun_restart'),
                ('short_file_prefill_blocked','(tail_queued && used_frames!=0)','1\'b0','one_frame_odd_pad'),
                ('post_tail_reports_underrun','!local_tail_drained_o && !empty_o && !pcm_held_valid','!empty_o && !pcm_held_valid','one_frame_odd_pad'),
                ('byte_overflow_fence_removed','else if(file_byte_valid_i && used_bytes>=BYTE_DEPTH && !decoder_take)failure_now=BYTE_OVERFLOW;','else if(1\'b0)failure_now=BYTE_OVERFLOW;','overflow_fault_injection'),
                ('start_file_error_ignored','failed_o<=file_error_i ||','failed_o<=1\'b0 ||','start_with_file_error'),
                ('rate_mismatch_accepted','format_ready_o && file_rate_o!=session_rate','format_ready_o && 1\'b0','rate_mismatch'),
            ]
            for label,old_text,new_text,case in variants:
                if text.count(old_text)!=1:raise ValueError('negative anchor drift '+label)
                path=out/(label+'.sv');path.write_text(text.replace(old_text,new_text));run(label,compile_source(label,path),by_name[case],True)
            parser_text=parser.read_text();anchor="                    if(chunk_end>({2'b0,riff_size}+34'd8))error_o<=1;"
            if parser_text.count(anchor)!=1:raise ValueError('parser boundary negative drift')
            path=out/'chunk_size_boundary_removed.sv';path.write_text(parser_text.replace(anchor,''))
            run('chunk_size_boundary_removed',compile_source('chunk_size_boundary_removed',owner,path),by_name['chunk_size_odd_overflow'],True)
        if before!={str(p):sha(p) for p in inputs}:raise ValueError('source drift')
        result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(result['cases']),negative_controls=len(result['negative_controls']))))
if __name__=='__main__':main()
