#!/usr/bin/env python3
"""Real maintained TF DDR/WAV path + native policy/atomic transport regression."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from workstation_baselines import load_baseline

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    (output/'src/memory').mkdir(parents=True)
    shutil.copy2(ROOT/'rtl/ddr_address_map.vh',output/'src/memory/ddr_address_map.vh')
    fixtures=[]
    for track,rate in enumerate((48000,44100,32000,48000)):
        pcm=[(1000+track*100+index,-2000-track*100-index) for index in range(64)]
        stream=io.BytesIO()
        with wave.open(stream,'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(rate)
            wav.writeframes(b''.join(struct.pack('<hh',*pair) for pair in pcm))
        payload=bytearray(stream.getvalue())
        if track==3:payload[20]=3 # unsupported IEEE-float format, no fake PCM.
        assert len(payload)==300
        fixture=output/f'file{track}.hex'
        fixture.write_text(''.join(f'{value:02x}\n' for value in payload));fixtures.append(fixture)
    sources=[ROOT/name for name in (
        'rtl/tf_audio/workstation_tf_runtime_service.sv','rtl/tf_audio/workstation_tf_frame_bridge.sv',
        'rtl/music/music_async_fifo.sv','rtl/tf_audio/storage/tf_audio_ddr_path.v',
        'rtl/tf_audio/storage/tf_audio_ddr_dma.v','rtl/tf_audio/storage/tf_async_byte_fifo.v',
        'rtl/tf_audio/storage/tf_audio_decoder_ip.v','rtl/tf_audio/storage/tf_wav_chunk_parser.v',
        'rtl/tf_audio/storage/tf_wav_pcm_decoder.v','rtl/display_data/tf_audio_ddr_command_buffer.sv',
        'rtl/audio/scope_vec/scope_tf_transport.sv')]
    sources.append(Path(__file__).with_name('workstation_tf_runtime_service_tb.sv'))
    baseline=load_baseline(ROOT,'resource_rework_route0')
    reference_bytes=baseline.read_bytes('src/storage/tf_audio_ddr_path.v')
    reference=reference_bytes.decode()
    current=(ROOT/'rtl/tf_audio/storage/tf_audio_ddr_path.v').read_text()
    # Exact inverse of the bounded opt-in adapter; default constant folds to
    # the immutable original expressions. Drift or extra edits fail closed.
    edits=[('    parameter [27:0] HOTPLUG_STALL_TIMEOUT_CYCLES = 28\'d250_000_000,\n    parameter integer NATIVE_RESTART_HOLD = 0',
            '    parameter [27:0] HOTPLUG_STALL_TIMEOUT_CYCLES = 28\'d250_000_000'),
           ('    input  wire [255:0] app_rdata,\n    // Opt-in memory-domain held level. Stop new FIFO/DMA work while an\n    // accepted read response drains; never reset retained EOF toggles.\n    input  wire        native_memory_hold_i',
            '    input  wire [255:0] app_rdata'),
           ("    wire native_memory_hold=NATIVE_RESTART_HOLD ? native_memory_hold_i:1'b0;\n",''),
           ('.mem_ready            (memory_ready && !native_memory_hold)', '.mem_ready            (memory_ready)'),
           ('.fifo_in_empty        (in_empty || native_memory_hold)', '.fifo_in_empty        (in_empty)'),
           ('.fifo_out_full        (out_full || native_memory_hold)', '.fifo_out_full        (out_full)')]
    for changed,original in edits:
        if current.count(changed)!=1:raise ValueError('Default path identity anchor drift: '+changed[:50])
        current=current.replace(changed,original)
    if current.encode()!=reference_bytes:raise ValueError('Default path differs from immutable original')
    legacy_source=output/'tf_audio_ddr_path_legacy_reference.v'
    if reference.count('module tf_audio_ddr_path #(')!=1:raise ValueError('Original module identity drift')
    legacy_source.write_text(reference.replace('module tf_audio_ddr_path #(','module tf_audio_ddr_path_legacy_reference #('))
    scope_name='rtl/audio/scope_vec/scope_tf_transport.sv'
    scope_bytes=baseline.read_bytes(scope_name)
    scope_text=(ROOT/scope_name).read_text()
    scope_legacy=''.join(line for line in scope_text.splitlines(keepends=True)
                         if 'explicit_restart_o' not in line and 'file_cancel_o' not in line)
    scope_legacy=scope_legacy.replace('    output reg restart_o,cancel_analysis_o,error_o,\n',
                                      '    output reg restart_o,cancel_analysis_o,error_o\n')
    scope_legacy=scope_legacy.replace('                    end else begin restart_o<=1;wait_card<=0;error_o<=0;\n                    end\n',
                                      '                    end else begin restart_o<=1;wait_card<=0;error_o<=0;end\n')
    if scope_legacy.encode()!=scope_bytes:raise ValueError('Original scope behavior identity drift')
    scope_reference=output/'scope_tf_transport_legacy_reference.sv'
    scope_reference.write_text(scope_legacy.replace('module scope_tf_transport (','module scope_tf_transport_legacy_reference ('))
    sources.append(scope_reference)
    reference_tb=Path(__file__).with_name('tf_path_default_reference_tb.sv')
    reference_sources=sources+[legacy_source,reference_tb]
    inputs=sources+fixtures+[ROOT/'rtl/ddr_address_map.vh',Path(__file__).resolve(),reference_tb,legacy_source,
        baseline.manifest,ROOT/'baselines/index.json',ROOT/'tools/workstation_baselines.py',
        baseline.repository/baseline.descriptor['files']['src/storage/tf_audio_ddr_path.v']['source'],
        baseline.repository/baseline.descriptor['files'][scope_name]['source']]
    hashes={str(path):digest(path) for path in inputs}
    source_set={str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else 'fixture/'+path.name:digest(path) for path in inputs}
    source_set_sha=hashlib.sha256(json.dumps(source_set,sort_keys=True).encode()).hexdigest()
    result=dict(schema=1,passed=False,hardware_tested=False,profile_changed=False,
        identity='native-tf-runtime-service-v2-'+source_set_sha[:16],source_set_sha256=source_set_sha,
        validation_stage='offline-real-TF-DDR-WAV-policy-and-transport',input_sha256=hashes,
        legacy_reference=baseline.evidence(),legacy_path_sha256=hashlib.sha256(reference_bytes).hexdigest(),
        default_path_exact_reconstruction=True,
        default_scope_exact_reconstruction=True,legacy_scope_sha256=hashlib.sha256(scope_bytes).hexdigest(),
        limits='Real maintained path/DDR DMA/byte FIFOs/WAV decoder/85bit bridge. SD/FAT reader is a byte-boundary fixture; DDR is bounded ordered memory. DDR capacity fault is injected at its real producer. No streaming migration, complete top/profile, physical CDC, synthesis, P&R, JTAG or board acceptance.')
    try:
        compile_command=['iverilog','-g2012','-Wall','-I',str(output),'-s','tb_workstation_tf_runtime_service',
                         '-o',str(output/'service.vvp'),*map(str,sources)]
        result['compile_argv']=compile_command
        for stage,command in (('compile',compile_command),('run',['vvp',str(output/'service.vvp')])):
            process=subprocess.run(command,cwd=output,text=True,capture_output=True,timeout=90)
            log=process.stdout+process.stderr;(output/(stage+'.log')).write_text(log)
            result[stage+'_log_sha256']=digest(output/(stage+'.log'))
            if process.returncode:raise RuntimeError(stage+' failed:\n'+log[-9000:])
        log=(output/'run.log').read_text()
        if 'PASS tf_runtime_service:' not in log:raise ValueError('Missing verification marker')
        result['metrics']={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',log)}
        command=['iverilog','-g2012','-Wall','-I',str(output),'-s','tb_workstation_tf_runtime_service',
                 '-Ptb_workstation_tf_runtime_service.USE_COMMAND_BUFFER=1',
                 '-o',str(output/'buffered.vvp'),*map(str,sources)]
        result['buffered_compile_argv']=command
        for stage,command in (('buffered_compile',command),('buffered_run',['vvp',str(output/'buffered.vvp')])):
            process=subprocess.run(command,cwd=output,text=True,capture_output=True,timeout=90)
            buffered_log=process.stdout+process.stderr;(output/(stage+'.log')).write_text(buffered_log)
            result[stage+'_log_sha256']=digest(output/(stage+'.log'))
            if process.returncode:raise RuntimeError(stage+' failed:\n'+buffered_log[-6000:])
        buffered_log=(output/'buffered_run.log').read_text()
        if 'PASS tf_runtime_service:' not in buffered_log:raise ValueError('Missing buffered marker')
        result['buffered_metrics']={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',buffered_log)}
        command=['iverilog','-g2012','-Wall','-I',str(output),'-s','tb_tf_path_default_reference',
                 '-o',str(output/'default_reference.vvp'),*map(str,reference_sources)]
        result['default_reference_compile_argv']=command
        for stage,command in (('reference_compile',command),('reference_run',['vvp',str(output/'default_reference.vvp')])):
            process=subprocess.run(command,cwd=output,text=True,capture_output=True,timeout=90)
            reference_log=process.stdout+process.stderr;(output/(stage+'.log')).write_text(reference_log)
            result[stage+'_log_sha256']=digest(output/(stage+'.log'))
            if process.returncode:raise RuntimeError(stage+' failed:\n'+reference_log[-6000:])
        reference_log=(output/'reference_run.log').read_text()
        if 'PASS tf_path_default_reference:' not in reference_log:raise ValueError('Missing default reference marker')
        result['default_reference_metrics']={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',reference_log)}
        result['inputs_unchanged_during_run']=hashes=={str(path):digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:raise ValueError('Input drift')
        result['passed']=True;print(log,end='');print(buffered_log,end='');print(reference_log,end='')
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:run(args.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='gw138k-tf-runtime-') as directory:run(Path(directory)/'verification')

if __name__=='__main__':main()
