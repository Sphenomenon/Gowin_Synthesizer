#!/usr/bin/env python3
"""Publication, key/content, cancellation and late-result FAT cache controls."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
RTL=ROOT/'rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.sv'
TB=ROOT/'sim/tf_audio/tb_workstation_tf_fat_cache_local.sv'
NATIVE=ROOT/'rtl/tf_audio/workstation_tf_direct_native_v1.sv'
NATIVE_SOURCES=[NATIVE,ROOT/'rtl/tf_audio/workstation_tf_direct_ingress_v1.sv',
    *[ROOT/('rtl/tf_audio/storage/'+name+'.sv') for name in (
        'workstation_tf_file_reader','workstation_tf_sd_sector_reader','workstation_tf_spi_session',
        'workstation_tf_sd_crc16_v1','workstation_tf_wav_pcm_decoder_v1','workstation_tf_wav_chunk_parser_v1')],RTL]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inputs={str(x):sha(x) for x in [*NATIVE_SOURCES,TB,Path(__file__).resolve()]}
    report=dict(schema=1,passed=False,input_sha256=inputs,cases={},negative_controls={},configuration_rejects={},
                synthesis=False,pnr=False,hardware_operated=False,physical_BSRAM_count_proven=False)
    def execute(name,source,error=None):
        binary=out/(name+'.vvp');cmd=['iverilog','-g2012','-s','tb_workstation_tf_fat_cache_local','-o',str(binary),str(source),str(TB)]
        c=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/(name+'.compile.log')).write_text(c.stdout+c.stderr)
        if c.returncode:raise ValueError(c.stdout+c.stderr)
        r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30);log=r.stdout+r.stderr
        (out/(name+'.run.log')).write_text(log)
        if error:
            if r.returncode==0 or error not in log or 'timeout' in log:raise ValueError(name+' negative escaped/unrelated '+log)
        elif r.returncode or 'PASS fat_cache_local' not in log:raise ValueError(name+' failed '+log)
        return dict(passed=error is None,rejected=bool(error),returncode=r.returncode,compile_argv=cmd,
                    source_sha256=sha(source),VVP_sha256=sha(binary),run_log=log)
    try:
        report['cases']['complete_publication_and_lifecycle']=execute('positive',RTL)
        source=RTL.read_text()
        for name,before,after,error in [
            ('early_publication','valid<=0;fill_live<=1;', 'valid<=1;fill_live<=1;', 'incomplete CRC-boundary publication'),
            ('wrong_LBA_key','valid && key_lba==lookup_lba_i', 'valid', 'cache LBA hit mismatch'),
            ('invalid_count_or_order','fill_count==512 && !fill_order_error && !fill_byte_valid_i', "1'b1", 'short fill published'),
            ('ignore_lifecycle','else if(invalidate_i)begin', "else if(1'b0)begin", 'cache LBA hit mismatch'),
            ('byte_order','{fill_byte_i,assembled_low}', '{assembled_low,fill_byte_i}', 'cache lookup oracle mismatch'),
        ]:
            if source.count(before)!=1:raise ValueError('mutation anchor drift '+name)
            path=out/(name+'.sv');path.write_text(source.replace(before,after))
            report['negative_controls'][name]=execute(name,path,error)
        for name,crc,cache in [('cache_without_CRC',0,1),('invalid_cache_value',1,2)]:
            binary=out/(name+'.vvp')
            cmd=['iverilog','-g2012','-s',NATIVE.stem,'-o',str(binary),
                 '-P'+NATIVE.stem+'.VERIFY_DATA_CRC='+str(crc),
                 '-P'+NATIVE.stem+'.FAT_SECTOR_CACHE='+str(cache),*map(str,NATIVE_SOURCES)]
            c=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
            if c.returncode:raise ValueError(name+' compile '+c.stdout+c.stderr)
            r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
            log=r.stdout+r.stderr;(out/(name+'.run.log')).write_text(log)
            if r.returncode==0 or 'native FAT cache requires explicit CRC verification' not in log:
                raise ValueError(name+' configuration escaped '+log)
            report['configuration_rejects'][name]=dict(rejected=True,returncode=r.returncode,
                compile_argv=cmd,VVP_sha256=sha(binary),run_log=log)
        assert inputs=={str(x):sha(x) for x in [*NATIVE_SOURCES,TB,Path(__file__).resolve()]}
        report.update(inputs_unchanged=True,passed=True)
    finally:(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=1,negative_controls=5,configuration_rejects=2)))
if __name__=='__main__':main()
