#!/usr/bin/env python3
"""Independent Python CRC oracle and actual native SD SPI-wire regression.

Writes only a fresh evidence directory. Legacy fixtures, manifests, vendor
sources and profiles are not modified. CRC-before-PCM isolation is not claimed.
"""
from pathlib import Path
import argparse,binascii,concurrent.futures,hashlib,json,re,subprocess

ROOT=Path(__file__).resolve().parents[2]
SIM=ROOT/'sim/tf_audio';STORAGE=ROOT/'rtl/tf_audio/storage'
CHECKER=STORAGE/'workstation_tf_sd_crc16_v1.sv'
SECTOR=STORAGE/'workstation_tf_sd_sector_reader.sv'
SESSION=STORAGE/'workstation_tf_spi_session.sv'
CARD=SIM/'workstation_tf_sd_crc_wire_card.sv'
TB=SIM/'tb_workstation_tf_sd_crc_wire.sv'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vectors(folder,kind):
    payload=bytes(512) if kind=='zero' else bytes([255])*512 if kind=='ff' else bytes(
        ((i*73+(i//8)*19)^0xa5)&255 for i in range(512))
    crc=binascii.crc_hqx(payload,0)
    if kind=='zero':assert crc==0
    if kind=='ff':assert crc==0x7fa1
    assert kind!='pattern' or crc!=0xffff
    image=payload+bytes(262144-512)
    (folder/'image.hex').write_text(''.join(f'{v:02x}\n' for v in image))
    (folder/'lbas.hex').write_text('00000000\n'+'ffffffff\n'*511)
    (folder/'crc16.hex').write_text(f'{crc:04x}\n'+'0000\n'*511)
    (folder/'oracle.hex').write_text(''.join(f'{v:02x}\n' for v in payload))
    return dict(pattern=kind,payload_sha256=hashlib.sha256(payload).hexdigest(),
                crc16=crc,crc16_hex=f'{crc:04x}',oracle='Python binascii.crc_hqx(payload, 0)',
                crc_excludes_token_and_received_CRC_bytes=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--no-negatives',action='store_true')
    args=ap.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    assert binascii.crc_hqx(b'123456789',0)==0x31c3
    files=[CHECKER,SECTOR,SESSION,CARD,TB,Path(__file__).resolve()]
    before={str(p):sha(p) for p in files}
    result=dict(schema=1,passed=False,input_sha256=before,cases={},negative_controls={},
        public_real_SPI_only=True,native_controller_count=1,native_session_count=1,
        independent_python_crc_oracle=True,CRC_before_PCM_isolation_proven=False,
        missing_CRC_scope='Both clocked CRC byte slots sample pull-up FF; payload oracle CRC is B1CF, not FFFF. Does not prove every physical missing-CRC case.',
        stop_semantics_tested=False,profile_selected=False,implementation_tools_invoked=False,
        hardware_operated=False,release_ready=False,deployment_allowed=False)

    def execute(name,parameters,kind='pattern',checker=CHECKER,sector=SECTOR,expected_failure=None):
        folder=output/name;folder.mkdir()
        oracle=vectors(folder,kind)
        command=['iverilog','-g2012','-s','tb_workstation_tf_sd_crc_wire','-o',str(folder/'sim.vvp')]
        command+=['-Ptb_workstation_tf_sd_crc_wire.'+key+'='+str(value) for key,value in parameters.items()]
        command+=list(map(str,[checker,sector,SESSION,CARD,TB]))
        compiled=subprocess.run(command,capture_output=True,text=True,timeout=60)
        (folder/'compile.log').write_text(compiled.stdout+compiled.stderr)
        if compiled.returncode:raise ValueError(name+' compile failed '+compiled.stdout+compiled.stderr)
        argv=['vvp',str(folder/'sim.vvp'),'+IMAGE='+str(folder/'image.hex'),'+LBAS='+str(folder/'lbas.hex'),
              '+CRC16='+str(folder/'crc16.hex'),'+ORACLE='+str(folder/'oracle.hex')]
        executed=subprocess.run(argv,capture_output=True,text=True,timeout=180)
        log=executed.stdout+executed.stderr;(folder/'run.log').write_text(log)
        if expected_failure:
            if not executed.returncode or expected_failure not in log or 'timeout' in log:
                raise ValueError(name+' negative escaped/unrelated '+log)
        elif executed.returncode or 'PASS tf_sd_crc_wire' not in log:
            raise ValueError(name+' failed '+log)
        record=dict(passed=not bool(expected_failure),rejected=bool(expected_failure),parameters=parameters,
            oracle=oracle,compile_argv=command,run_argv=argv,returncode=executed.returncode,
            checker_sha256=sha(checker),sector_sha256=sha(sector),compile_log_sha256=sha(folder/'compile.log'),
            run_log_sha256=sha(folder/'run.log'),run_log=log,
            metrics={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',log)})
        print(('PASS rejected ' if expected_failure else 'PASS ')+name,flush=True)
        return name,record

    try:
        cases=[('correct_pattern',{},'pattern'),('correct_zero',{},'zero'),
               ('correct_ff_div12',dict(READ_DIV=12),'ff'),
               ('correct_SDV2',dict(CARD_KIND=1),'pattern'),
               ('correct_SDV1',dict(CARD_KIND=2),'pattern')]
        cases += [(name,dict(FAULT=fault),'pattern') for fault,name in (
            (1,'corrupt_payload'),(2,'bad_CRC_high'),(3,'bad_CRC_low'),(4,'missing_CRC_pullup'))]
        cases.append(('explicit_legacy_unchecked',dict(VERIFY_CRC=0,FAULT=2),'pattern'))
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for name,record in pool.map(lambda case:execute(*case),cases):result['cases'][name]=record
        if not args.no_negatives:
            text=CHECKER.read_text()
            mutations=[('wrong_polynomial',"16'h1021","16'h8408",0,1),
                       ('wrong_seed','payload_crc<=0;','payload_crc<=16\'hffff;',0,2),
                       ('skip_payload_byte','byte_index_i>=16\'d2','byte_index_i>=16\'d3',0,1),
                       ('CRC_compare_bypass','{crc_high,byte_i}==payload_crc',"1'b1",2,1)]
            for name,old,new,fault,count in mutations:
                if text.count(old)!=count:raise ValueError('negative anchor drift '+name)
                path=output/(name+'.sv');path.write_text(text.replace(old,new))
                key,record=execute('negative_'+name,dict(FAULT=fault),checker=path,
                                   expected_failure='CRC verdict mismatch')
                record['exact_mutation_anchor_count']=count
                result['negative_controls'][key]=record
        result['inputs_unchanged']=before=={str(p):sha(p) for p in files}
        if not result['inputs_unchanged']:raise ValueError('CRC wire source drift during verification')
        result['passed']=True
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
