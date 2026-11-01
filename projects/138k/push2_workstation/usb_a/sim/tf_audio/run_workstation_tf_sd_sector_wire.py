#!/usr/bin/env python3
"""Verify an unselected native SD owner against a real SPI-wire card model."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
NATIVE='rtl/tf_audio/storage/workstation_tf_sd_sector_reader.sv'
NATIVE_SESSION='rtl/tf_audio/storage/workstation_tf_spi_session.sv'
PROVENANCE='rtl/tf_audio/storage/workstation_tf_sd_sector_reader.provenance.json'
SESSION='rtl/tf_audio/storage/tang_mp3/vendor/tf_spi_session.v'
HISTORICAL='rtl/tf_audio/storage/tang_mp3/vendor/tf_sd_spi_sector_reader.v'
FIXTURE='sim/tf_audio/workstation_tf_sd_sector_wire_tb.sv'
LOCKS={
    SESSION:'69af9d24a02f8472b87f114dce58e05d5032daeea21f7aca201ef08ea6ac1cbc',
    HISTORICAL:'259bedb80a6a54cf2048ae6cb2f40ec384108ae2743acb49b8acb70abf126504',
    'rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v':'57ee8873418fe2fa00e40782e1509495c8eb779e11d4175884a79f741fcc0441',
    'rtl/tf_audio/storage/tf_sd_audio_pcm_player.v':'41733261ca506cf3c2f53c23f5b329bd45bbd809a9eb7e888fcaad28eb708f18',
}

def sha(data):return hashlib.sha256(data).hexdigest()

def replace_once(text,anchor,replacement):
    if text.count(anchor)!=1:raise ValueError('Negative-control anchor drift: '+anchor)
    return text.replace(anchor,replacement)

def run(output,*,direct_crc_source_adaptation=False,direct_fat_cache_source_adaptation=False):
    output.mkdir(parents=True,exist_ok=False)
    maintained=[NATIVE,NATIVE_SESSION,PROVENANCE,FIXTURE,str(Path(__file__).resolve().relative_to(ROOT))]
    hashes={name:sha((ROOT/name).read_bytes()) for name in maintained+list(LOCKS)}
    for name,expected in LOCKS.items():
        if hashes[name]!=expected:raise ValueError('Immutable dependency drift: '+name)
    provenance=json.loads((ROOT/PROVENANCE).read_text())
    adaptation=None
    legacy_sector_hash=hashes[NATIVE]
    if direct_crc_source_adaptation or direct_fat_cache_source_adaptation:
        import sys
        sys.path.insert(0,str(ROOT))
        from tools.workstation_tf_sd_crc16_provenance import restored_basis,MANIFEST
        basis,adaptation=restored_basis(ROOT,NATIVE,fat_cache_source_adaptation=direct_fat_cache_source_adaptation)
        legacy_sector_hash=sha(basis)
        for relative in (MANIFEST,'tools/workstation_tf_sd_crc16_provenance.py',
                         'rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.sv'):
            hashes[relative]=sha((ROOT/relative).read_bytes())
        if direct_fat_cache_source_adaptation:
            for relative in ('rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.adaptation.json','tools/workstation_tf_fat_cache_provenance.py','rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.sv','rtl/tf_audio/workstation_tf_direct_native_v1.sv','rtl/tf_audio/workstation_tf_direct_runtime_service.sv','rtl/tf_audio/storage/workstation_tf_file_reader.sv'):
                hashes[relative]=sha((ROOT/relative).read_bytes())
    if provenance['native_sector_sha256']!=legacy_sector_hash or provenance['native_session_sha256']!=hashes[NATIVE_SESSION]:
        raise ValueError('Maintained source provenance drift')
    if provenance['session_origin_sha256']!=hashes[SESSION] or provenance['sector_origin_sha256']!=hashes[HISTORICAL]:
        raise ValueError('Provenance origin mismatch')
    expected=provenance['session_header']+(ROOT/SESSION).read_text()
    for edit in provenance['session_forward_edits']:
        if expected.count(edit['before'])!=edit['count']:raise ValueError('Session adaptation anchor drift')
        expected=expected.replace(edit['before'],edit['after'])
    expected+=provenance['session_suffix']
    if expected!=(ROOT/NATIVE_SESSION).read_text():raise ValueError('Unexpected native session adaptation')
    identity=sha(json.dumps(hashes,sort_keys=True).encode())
    result=dict(schema=1,passed=False,identity='native-tf-sd-sector-wire-v1-'+identity[:16],
        source_set_sha256=identity,source_sha256=hashes,
        source_policy='maintained unselected sector/session owners with explicit R1-valid adaptation; original vendor/session/baseline/profile untouched',
        wire_model='SPI edges only, real card initialization; no DUT hierarchy force/deposit or SPI-session stub',
        exact_session_provenance_verified=True,
        explicit_DIRECT_crc_source_adaptation=adaptation,
        CRC_verification_enabled_in_this_default_regression=False,
        profile_selected=False,file_reader_integration=False,no_DDR_playback_implemented=False,
        wav_decoder_changed=False,m03_complete=False,synthesis=False,pnr=False,
        hardware_tested=False,sram_programmed=False,flash_written=False,cases={})

    def execute(name,source,parameters,expected_failure=None):
        command=['iverilog','-g2012','-Wall','-s','tb_workstation_tf_sd_sector_wire',
            '-o',str(output/(name+'.vvp'))]
        command+=['-Ptb_workstation_tf_sd_sector_wire.'+key+'='+str(value) for key,value in parameters.items()]
        command += [str(source),str(ROOT/NATIVE_SESSION),str(ROOT/SESSION),str(ROOT/FIXTURE)]
        compiled=subprocess.run(command,cwd=output,capture_output=True,text=True,timeout=60)
        compile_log=compiled.stdout+compiled.stderr
        (output/(name+'_compile.log')).write_text(compile_log)
        if compiled.returncode:raise RuntimeError(name+' compile failed: '+compile_log)
        run_command=['vvp',str(output/(name+'.vvp'))]
        executed=subprocess.run(run_command,cwd=output,capture_output=True,text=True,timeout=180)
        log=executed.stdout+executed.stderr
        (output/(name+'_run.log')).write_text(log)
        case=dict(compile_argv=command,run_argv=run_command,parameters=parameters,
            source_sha256=sha(source.read_bytes()),returncode=executed.returncode,
            compile_log_sha256=sha(compile_log.encode()),compile_log=compile_log,
            run_log_sha256=sha(log.encode()),run_log=log,
            metrics={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',log)})
        if expected_failure:
            case['expected_failure']=expected_failure
            case['rejected']=executed.returncode!=0 and expected_failure in log
            if not case['rejected']:raise RuntimeError(name+' negative escaped: '+log)
            print('PASS rejected '+name+': '+expected_failure,flush=True)
        else:
            if executed.returncode or 'PASS workstation_tf_sd_sector_wire:' not in log:
                raise RuntimeError(name+' failed: '+log)
            print(log.splitlines()[0],flush=True)
        return name,case

    try:
        scenarios=[('sdhc_div'+str(divider),ROOT/NATIVE,dict(READ_DIV=divider)) for divider in (12,6,3,2,0,255)]
        scenarios += [
            ('sdv2_byte_addressed',ROOT/NATIVE,dict(READ_DIV=2,CARD_KIND=1)),
            ('sdv1_byte_addressed',ROOT/NATIVE,dict(READ_DIV=2,CARD_KIND=2)),
            ('production_patience_div12',ROOT/NATIVE,dict(READ_DIV=12,WAIT_CLOCKS=8320000,FULL_PATIENCE_ONLY=1)),
            ('production_patience_div2',ROOT/NATIVE,dict(READ_DIV=2,WAIT_CLOCKS=8320000,FULL_PATIENCE_ONLY=1)),
        ]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for name,case in pool.map(lambda args:execute(*args),scenarios):result['cases'][name]=case

        native=(ROOT/NATIVE).read_text()
        negatives=[
            ('fixed_40000_byte_wait_negative',replace_once(native,'midcycle<=TOKEN_BYTES;',
                "midcycle<=24'd40_000;"),dict(READ_DIV=2,WAIT_CLOCKS=8320000,FULL_PATIENCE_ONLY=1),'read completion/error'),
            ('old_255_byte_tail_negative',replace_once(native,".stopcycle(8'd0)",
                ".stopcycle((cardstate==READING) ? 8'd255 : 8'd0)"),dict(READ_DIV=12),'wire transaction mismatch'),
            ('payload_address_negative',replace_once(native,"raddr<=9'd1-rindex_session[8:0];",
                "raddr<=9'd0-rindex_session[8:0];"),dict(READ_DIV=12),'payload/address mismatch'),
        ]
        # Test-only port/name shim for the frozen historical owner. It keeps
        # its complete controller and real session, and must fail the same
        # wire monitor because one request emits two CMD17/payload/CRC sets.
        historical=(ROOT/HISTORICAL).read_text()
        historical=replace_once(historical,'module tf_sd_spi_sector_reader #(',
            'module workstation_tf_sd_sector_reader #(\n    parameter integer TOKEN_WAIT_CLOCKS=8320000,')
        historical=replace_once(historical,'output wire          debug_rvalid_session\n);',
            'output wire          debug_rvalid_session,\n    output wire read_error,\n    output wire [1:0] read_error_code\n);\nassign read_error=0;\nassign read_error_code=0;')
        negatives.append(('historical_duplicate_wire_negative',historical,
            dict(READ_DIV=12,WAIT_CLOCKS=500000,FIRST_TOKEN_DELAY=8,HOLD_ARGUMENT=1),'wire transaction mismatch'))
        no_r1_guard=replace_once(native,"READING: if(cmdrsp_valid && cmdrsp==8'h00 && rwrsp==8'hfe)",
            "READING: if(cmdrsp==8'h00 && rwrsp==8'hfe)")
        no_r1_guard=replace_once(no_r1_guard,"if(cardstate==READING && cmdrsp_valid && cmdrsp==8'h00 && rwrsp==8'hfe &&",
            "if(cardstate==READING && cmdrsp==8'h00 && rwrsp==8'hfe &&")
        negatives.append(('no_R1_valid_guard_negative',no_r1_guard,
            dict(READ_DIV=2),'terminal failure mismatch'))
        for name,source_text,parameters,expected_failure in negatives:
            path=output/(name+'.sv');path.write_text(source_text)
            key,case=execute(name,path,parameters,expected_failure)
            result['cases'][key]=case
        for name,parameters in (
            ('invalid_init_low',dict(INIT_DIV=1)),('invalid_init_high',dict(INIT_DIV=256)),
            ('invalid_fast_low',dict(READ_DIV=1)),('invalid_fast_high',dict(READ_DIV=256)),
            ('invalid_wait_zero',dict(WAIT_CLOCKS=0)),
            ('invalid_wait_overflow',dict(READ_DIV=2,WAIT_CLOCKS=2147483647)),
        ):
            expected='divider must be' if 'init' in name or 'fast' in name else 'token wait does not fit'
            key,case=execute(name,ROOT/NATIVE,parameters,expected)
            result['cases'][key]=case
        result['default_50MHz_token_budget']=[dict(divider=divider,
            token_bytes=(8320000+16*(divider+1)-1)//(16*(divider+1)),
            lower_bound_wait_clocks=((8320000+16*(divider+1)-1)//(16*(divider+1)))*16*(divider+1),
            configured_wait_ms=166.4) for divider in (12,6,3,2)]
        result['source_inputs_unchanged_during_run']=hashes=={
            name:sha((ROOT/name).read_bytes()) for name in hashes}
        if not result['source_inputs_unchanged_during_run']:raise ValueError('Input drift during verification')
        result['passed']=True
    finally:
        (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--direct-crc-source-adaptation',action='store_true',
        help='explicit DIRECT source branch: strictly recover old source hashes before original provenance validation; tests still use VERIFY_DATA_CRC=0')
    parser.add_argument('--direct-fat-cache-source-adaptation',action='store_true',
        help='explicit newer chain: invert FAT cache then unchanged CRC adaptation; DUT still uses both defaults zero')
    args=parser.parse_args()
    run(args.output.resolve(),direct_crc_source_adaptation=args.direct_crc_source_adaptation,direct_fat_cache_source_adaptation=args.direct_fat_cache_source_adaptation)
