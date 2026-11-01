#!/usr/bin/env python3
"""Check actual W audio-only ELF startup, retired MMIO and composition rejection.

The RV32 tests model a disconnected controller and an invalid controller ID.
They do not emulate a successful phone connection or measure real CPU cycles.
"""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools.workstation_classic_runtime import verify_build
from tools.ae350_worker_audio_audit import verify_composition
from tools.ae350_local_memory import symbol_values
from ae350_split_rv32 import SplitCpu
from ae350_rv32_startup import ModelError

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class AudioOnlyCpu(SplitCpu):
    def __init__(self,*args,bad_identity=False,**kwargs):
        super().__init__(*args,**kwargs)
        self.bad_identity=bad_identity;self.hci_reads=[]
    def read(self,address,width=4,*,fetch=False):
        if not fetch and 0xf8050200<=address<0xf8050280:
            if width!=4:raise ModelError('unexpected HCI access width')
            off=address-0xf8050200;self.hci_reads.append(off)
            # Neither case grants a successful link or accepts a command.
            return {0:0,4:0x01040114,8:int(self.bad_identity),12:int(self.bad_identity),112:276,120:0}.get(off,0)
        if not fetch and (0x10000000<=address<0x20000000 or 0xf8010000<=address<0xf8080000):
            raise ModelError('retired UI/recording/DDR read: '+hex(address))
        return super().read(address,width,fetch=fetch)
    def write(self,address,value,width=4):
        if 0x10000000<=address<0x20000000 or 0xf8010000<=address<0xf8080000:
            raise ModelError('unexpected UI/recording/media write while disconnected: '+hex(address))
        return super().write(address,value,width)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--firmware',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);fw=a.firmware.resolve()
    record=json.loads((fw/'build_metadata.json').read_text());verify_build(ROOT,fw,record)
    assert record['headless_worker'] and not record['recording_api_enabled']
    checked={str(x):sha(x)for x in fw.rglob('*')if x.is_file()}
    symbols=symbol_values((fw/'firmware.nm').read_text());image=(fw/'firmware.bin').read_bytes().ljust(131072,b'\0')
    executions=[]
    for bad in [False,True]:
        cpu=AudioOnlyCpu(image,symbols,bad_identity=bad)
        assert cpu.run()=='services_main'
        start=cpu.steps
        for _ in range(400000):
            if cpu.diagnostics.get(8,0)>=8:break
            cpu.step()
        else:raise ModelError('audio-only pump did not continue')
        assert not cpu.traps and cpu.diagnostics[4]==0x41554457 and cpu.hci_reads
        assert (0 in cpu.hci_reads)==bad
        executions.append(dict(case='invalid_HCI_identity'if bad else 'disconnected_controller',
            actual_instructions_after_loader=cpu.steps-start,heartbeat=cpu.diagnostics[8],
            HCI_reads=len(cpu.hci_reads),retired_MMIO_or_DDR_accesses=0,traps=0))
    negatives=[]
    for name,mutate in [
        ('retired_translation_unit',lambda r:r['compiled_sources'].append('ui_render.c')),
        ('missing_audio_only_define',lambda r:next(x for x in r['commands']if x['name'].startswith('compile-'))['argv'].remove('-DA138_WORKER_AUDIO_ONLY')),
        ('recording_claim',lambda r:r.update(single_recording_owner=True)),
        ('source_drift',lambda r:r['input_sha256'].update({'firmware/ae350/worker_audio_main.c':'0'*64}))]:
        changed=copy.deepcopy(record);mutate(changed)
        try:verify_composition(fw,ROOT,changed)
        except ValueError as e:negatives.append(dict(name=name,rejected=True,error=str(e)))
        else:raise ValueError('composition mutant survived: '+name)
    leak=out/'symbol-leak';leak.mkdir();(leak/'firmware.nm').write_text((fw/'firmware.nm').read_text()+'\na0001234 T ui_render_rows\n')
    try:verify_composition(leak,ROOT,record)
    except ValueError as e:negatives.append(dict(name='retired_ELF_symbol',rejected=True,error=str(e)))
    else:raise ValueError('retired symbol mutant survived')
    for name,mutate in [
        ('relabel_as_recording_worker',lambda r:r.update(headless_worker=False,runtime_policy='ae350_worker_session_classic_runtime_v1',recording_api_enabled=True)),
        ('relabel_as_default_runtime',lambda r:r.update(headless_worker=False,worker_demo=False,runtime_policy='ae350_classic_runtime_failclosed_v1',recording_api_enabled=True)),
        ('metadata_compile_commands_drift',lambda r:next(x for x in r['commands']if x['name'].startswith('compile-'))['argv'].remove('-DA138_WORKER_AUDIO_ONLY'))]:
        changed=copy.deepcopy(record);mutate(changed)
        try:verify_build(ROOT,fw,changed)
        except ValueError as e:negatives.append(dict(name=name,rejected=True,error=str(e)))
        else:raise ValueError('linked role mutant survived: '+name)
    # Removing only the opt-in guards must recover the complete prior source.
    current=(ROOT/'firmware/ae350/classic_runtime.c').read_text();previous=current
    for body in ['#include "ble_business_owner.h"','    a138_ble_business_firmware_init();','    a138_ble_business_firmware_pump();']:
        guard='#ifndef A138_WORKER_AUDIO_ONLY\n'+body+'\n#endif';assert previous.count(guard)==1
        previous=previous.replace(guard,body,1)
    assert hashlib.sha256(previous.encode()).hexdigest()=='11ec8dbfcf4ac0fe7b59d19bc39bab35107161033add8099ccb845acaba03b32'
    old=out/'classic_runtime_before.c';old.write_text(previous);cc=shutil.which('cc');assert cc
    preserved=[]
    for name,defines in [('default',[]),('recording_worker',['-DA138_SINGLE_BLE_RECORDING'])]:
        args=[cc,'-E','-P','-I'+str(ROOT/'firmware/ae350'),
              '-I'+str(fw/'adapted/decoder/include'),'-I'+str(fw/'adapted/decoder/srce'),*defines]
        before=subprocess.check_output([*args,str(old)],text=True)
        after=subprocess.check_output([*args,str(ROOT/'firmware/ae350/classic_runtime.c')],text=True)
        assert before.split()==after.split(),name
        preserved.append(name)
    for name,h in checked.items():assert sha(name)==h,name
    result=dict(schema='ae350_worker_audio_actual_ELF_checks_v1',passed=True,executions=executions,
        composition_negative_controls=negatives,default_preprocessed_branches_equal=preserved,
        exact_source_inverse=True,firmware_files_unchanged=checked,
        graph_callback_negative_controls=4,ELF_sha256=record['elf_sha256'],ROM_sha256=record['rom_sha256'],
        cycle_measurement=False,radio_or_audio_acceptance=False,hardware_tested=False)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='firmware_files_unchanged'},indent=2))

if __name__=='__main__':main()
