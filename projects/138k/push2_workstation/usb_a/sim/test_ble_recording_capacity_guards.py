#!/usr/bin/env python3
"""Exercise real elaboration guards and the final physical DDR BL8 boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def run(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    names=('rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv',
        'rtl/bluetooth/cpu_owner/workstation_ble_record_data_service.sv',
        'rtl/memory/workstation_ble_raw_ddr_store.sv','rtl/memory/workstation_sdp.sv',
        'rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={n:sha(ROOT/n) for n in names};cases={}
    for kind in ('engine','service','store'):
        configs=[('zero',0,0,True),('beyond_physical',0x10000001,0,True),('physical_max',0x10000000,0,False)]
        if kind=='store':configs += [('last_BL8',8,0x0ffffff8,False),('past_last_BL8',9,0x0ffffff8,True)]
        for label,capacity,base,reject in configs:
            name=kind+'_'+label;stage=output/name;stage.mkdir()
            module={'engine':'workstation_ble_record_data_engine','service':'workstation_ble_record_data_service','store':'workstation_ble_raw_ddr_store'}[kind]
            parameters=f'.CAPACITY_FRAMES({capacity})'
            ports=''
            assertion=''
            if kind=='engine':
                parameters+=',.EXTERNAL_PCM(1),.EXTERNAL_SEAL_PROTOCOL(1),.EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(10000)'
                ports=".clk(1'b0),.resetn(1'b0),.enable(1'b0)"
                if not reject:assertion=f"force uut.recorded_frames=32'd{capacity}; #1; if(uut.object_bytes!==32'h40000000)$fatal(1,\"maximum frame-to-byte count overflow\");"
            elif kind=='store':parameters+=f",.BASE_APP(29'd{base})"
            fixture=stage/'guard.sv'
            fixture.write_text(f'module capacity_guard; {module} #({parameters}) uut({ports}); initial begin {assertion} #1; $display("PASS {name}"); $finish; end endmodule\n')
            binary=stage/'guard.vvp'
            compile_argv=['iverilog','-g2012','-s','capacity_guard','-o',str(binary),str(fixture),*[str(ROOT/n) for n in names]]
            compiled=subprocess.run(compile_argv,capture_output=True,text=True,timeout=60)
            (stage/'compile.log').write_text(compiled.stdout+compiled.stderr)
            if compiled.returncode:raise RuntimeError('guard compile failed: '+name)
            tested=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=30)
            text=tested.stdout+tested.stderr;(stage/'run.log').write_text(text)
            passed=(tested.returncode!=0 and 'FATAL:' in text) if reject else tested.returncode==0 and 'PASS '+name in text
            if not passed:raise RuntimeError('guard result drift: '+name+' '+text)
            cases[name]=dict(capacity_frames=capacity,base_native_words=base,expected_rejection=reject,passed=passed,
                compile_exit=compiled.returncode,run_exit=tested.returncode,run_log_sha256=sha(stage/'run.log'))
    unchanged=inputs=={n:sha(ROOT/n) for n in names}
    result=dict(schema=1,passed=unchanged,input_sha256=inputs,inputs_unchanged=unchanged,cases=cases,
        scope='Real RTL guard elaboration only; physical_max arithmetic is forced for boundary inspection, not a captured object.',
        synthesis=False,pnr=False,hardware_tested=False)
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    if not unchanged:raise RuntimeError('source changed during guard checks')
    print(json.dumps(dict(passed=True,cases=len(cases),negative_cases=sum(v['expected_rejection'] for v in cases.values()))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
