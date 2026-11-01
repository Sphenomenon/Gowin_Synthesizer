#!/usr/bin/env python3
"""Real native STOP through payload/CRC/CS release, with independent CRCs.

Uses the existing Python FAT/WAV oracle builder without altering it or its
historical card model. New HDL uses one actual native/file/sector/session chain.
"""
from pathlib import Path
import argparse,binascii,concurrent.futures,hashlib,importlib.util,json,re,subprocess

ROOT=Path(__file__).resolve().parents[2]
SIM=ROOT/'sim/tf_audio';RTL=ROOT/'rtl/tf_audio';STORAGE=RTL/'storage'
SOURCES=[RTL/'workstation_tf_direct_native_v1.sv',RTL/'workstation_tf_direct_ingress_v1.sv',
         STORAGE/'workstation_tf_file_reader.sv',STORAGE/'workstation_tf_sd_sector_reader.sv',
         STORAGE/'workstation_tf_spi_session.sv',STORAGE/'workstation_tf_wav_pcm_decoder_v1.sv',
         STORAGE/'workstation_tf_wav_chunk_parser_v1.sv',STORAGE/'workstation_tf_sd_crc16_v1.sv']
CARD=SIM/'workstation_tf_sd_crc_wire_card.sv';TB=SIM/'tb_workstation_tf_sd_crc_stop_wire.sv'
BUILDER=SIM/'run_workstation_tf_direct_native_wire.py'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_builder():
    spec=importlib.util.spec_from_file_location('crc_stop_disk_oracle',BUILDER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.disk


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--no-negatives',action='store_true')
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    assert binascii.crc_hqx(b'123456789',0)==0x31c3
    builder=load_builder()
    inputs=[*SOURCES,CARD,TB,BUILDER,SIM/'run_workstation_tf_direct_ingress.py',Path(__file__).resolve()]
    before={str(p):sha(p) for p in inputs}
    result=dict(schema=1,passed=False,input_sha256=before,cases={},negative_controls={},
        real_SPI_FAT_WAV_PCM=True,public_ports_only=True,native_controller_count=1,native_session_count=1,
        continuous_independent_48k_deadlines=True,exact_payload_CRC_CS_drain_checked=True,
        CRCbad_STOP_must_fail=True,explicit_owner_reset_remount_and_request=True,
        physical_card_identity_or_hotplug_verified=False,CRC_before_PCM_isolation_proven=False,
        implementation_tools_invoked=False,hardware_operated=False,release_ready=False,deployment_allowed=False)

    def execute(name,phase,sources=None,expected_failure=None):
        folder=out/name;manifest=builder(folder,16,False,48000,3800,97,0)
        image=bytes(int(v,16) for v in (folder/'image.hex').read_text().split())
        lbas=[int(v,16) for v in (folder/'lbas.hex').read_text().split()]
        assert image[lbas.index(21)*512:lbas.index(21)*512+4]==b'RIFF'
        crcs=[binascii.crc_hqx(image[i*512:(i+1)*512],0) for i in range(512)]
        (folder/'crc16.hex').write_text(''.join(f'{v:04x}\n' for v in crcs))
        selected=SOURCES if sources is None else sources
        command=['iverilog','-g2012','-s','tb_workstation_tf_sd_crc_stop_wire','-o',str(folder/'sim.vvp'),
                 '-Ptb_workstation_tf_sd_crc_stop_wire.STOP_PHASE='+str(phase),*map(str,[*selected,CARD,TB])]
        p=subprocess.run(command,capture_output=True,text=True,timeout=60)
        (folder/'compile.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise ValueError(name+' compile '+p.stdout+p.stderr)
        argv=['vvp',str(folder/'sim.vvp'),'+IMAGE='+str(folder/'image.hex'),'+LBAS='+str(folder/'lbas.hex'),
              '+CRC16='+str(folder/'crc16.hex'),'+ORACLE1='+str(folder/'oracle1.hex')]
        p=subprocess.run(argv,capture_output=True,text=True,timeout=180);log=p.stdout+p.stderr
        (folder/'run.log').write_text(log)
        if expected_failure:
            if p.returncode==0 or expected_failure not in log or 'timeout' in log:
                raise ValueError(name+' negative escaped/unrelated '+log)
        elif p.returncode or 'PASS tf_sd_crc_stop_wire' not in log:raise ValueError(name+' failed '+log)
        record=dict(passed=not bool(expected_failure),rejected=bool(expected_failure),stop_phase=phase,
            phase_names=['payload_byte_511','CRC_high','CRC_low','CS_release'],bad_CRC=phase>=4,disk=manifest,
            CRC_table_sha256=sha(folder/'crc16.hex'),oracle='Python binascii.crc_hqx(each full sector, 0)',
            source_sha256={str(p):sha(p) for p in selected},compile_argv=command,run_argv=argv,returncode=p.returncode,
            compile_log_sha256=sha(folder/'compile.log'),run_log_sha256=sha(folder/'run.log'),run_log=log,
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)})
        print(('PASS rejected ' if expected_failure else 'PASS ')+name,flush=True)
        return name,record

    try:
        cases=[('CRCgood_STOP_'+str(i),i) for i in range(4)]+[('CRCbad_STOP_'+str(i),i) for i in range(4,8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for name,record in pool.map(lambda c:execute(*c),cases):result['cases'][name]=record
        if not args.no_negatives:
            mutations=[('CRC_compare_bypass',7,'{crc_high,byte_i}==payload_crc',"1'b1",4,
                        'CRCbad+STOP must report one failed stop'),
                       ('stop_wait_removed',0,'!stop_i && !stop_wait',"!stop_i && 1'b1",0,
                        'pending CRC STOP fence escaped before actual drain')]
            for name,index,old,new,phase,error in mutations:
                text=SOURCES[index].read_text()
                if text.count(old)!=1:raise ValueError('CRC STOP negative anchor drift '+name)
                path=out/(name+'.sv');path.write_text(text.replace(old,new,1))
                sources=list(SOURCES);sources[index]=path
                key,record=execute('negative_'+name,phase,sources,error)
                result['negative_controls'][key]=record
        result['inputs_unchanged']=before=={str(p):sha(p) for p in inputs}
        if not result['inputs_unchanged']:raise ValueError('CRC STOP source drift during run')
        result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
