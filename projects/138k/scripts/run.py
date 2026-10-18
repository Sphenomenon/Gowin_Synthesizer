#!/usr/bin/env python3
"""Isolated migration simulation. Never writes either existing project's evidence."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[1]
ORIGINAL = WORKSPACE / 'fpga'
TEAM = WORKSPACE / 'Mega_138K/Dev/Prj1'

def audio_sources():
    files = [
        'rtl/audio/audio_math_pkg.sv', 'rtl/audio/sine_interp.sv',
        'rtl/audio/midi_step_rom.sv', 'rtl/audio/partial_step_generator_variable.sv',
        'rtl/audio/mode_timbre_rom.sv', 'rtl/audio/unified_oscillator_engine.sv',
        'rtl/audio/pitch_expression.sv', 'rtl/input/uart_rx.sv',
        'rtl/input/midi_stream_decoder.sv', 'rtl/audio/stereo_effects.sv',
        'rtl/audio/audio_workstation.sv', 'rtl/audio/spectrum_fft256.sv',
        'rtl/audio/audio_capture_fifo.sv', 'rtl/input/score_led_player.sv',
        'rtl/audio/audio_visual_extensions.sv',
    ]
    return ([ORIGINAL / f for f in files] +
            [TEAM / 'src/audio/pt8211_tx.v', TEAM / 'src/audio/pt8211_observer.v', TEAM / 'src/control/uart_tx.v'] +
            sorted((PROJECT / 'rtl').glob('*.sv')))

def rom_sources():
    return [ORIGINAL / p for p in [
        'sim/matlab/output/stage3_sine2048x24.mem',
        'sim/matlab/output/stage13_note_voice/stage13_midi_step.mem',
        'sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem',
        'sim/matlab/output/stage13_note_voice/stage13_ratio_q18.mem',
        'sim/matlab/output/stage15_unified_modes/stage15_mode_gain_q15.mem',
        'sim/data/audio_chain/pitch_bend_q20.mem', 'sim/data/audio_chain/fft_hann.mem',
        'sim/data/audio_chain/fft_tw_re.mem', 'sim/data/audio_chain/fft_tw_im.mem']]

def hashes(paths):
    return {str(p.relative_to(WORKSPACE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--test', choices=['clock','cdc','control_cdc','runtime','adapter','managed','all'], default='all')
    args = parser.parse_args()
    out = args.output or PROJECT/'results'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out = out.resolve(); out.mkdir(parents=True, exist_ok=False)
    inputs = audio_sources() + rom_sources() + list((PROJECT/'sim').glob('*.sv')) + [Path(__file__).resolve(),PROJECT/'rtl/gw138k_audio_clock.v']
    before = hashes(inputs)
    (out/'inputs.json').write_text(json.dumps(before,indent=2)+'\n')
    results=[]
    def run(name,command,cwd=ORIGINAL):
        with (out/(name+'.log')).open('w') as log:
            result=subprocess.run(list(map(str,command)),cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
        results.append({'name':name,'command':list(map(str,command)),'exit_code':result.returncode})
        print(name, 'PASS' if result.returncode==0 else 'FAIL',flush=True)
        (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        if result.returncode: raise SystemExit(f'{name} failed: {out/(name+".log")}')
    for test,top in [('clock','tb_audio_clock'),('cdc','tb_gw138k_stream_cdc'),('control_cdc','tb_gw138k_apb_cdc'),('runtime','tb_gw138k_runtime_uart'),('adapter','tb_gw138k_audio_adapter'),('managed','tb_gw138k_managed_audio')]:
        if args.test not in [test,'all']: continue
        if test=='clock': sources=[PROJECT/'rtl/gw138k_audio_clock.v']
        elif test=='cdc': sources=[PROJECT/'rtl/gw138k_stream_cdc.sv']
        elif test=='control_cdc': sources=[PROJECT/'rtl/gw138k_apb_cdc.sv']
        elif test=='runtime': sources=[PROJECT/'rtl/gw138k_runtime_uart.sv',TEAM/'src/control/uart_tx.v']
        else: sources=audio_sources()
        tb=PROJECT/'sim'/(top+'.sv')
        if test in ('adapter','managed'):
            run(test+'_compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',top,
                '--Mdir',out/('obj_'+test),*sources,tb])
            run(test,[out/('obj_'+test)/('V'+top)])
        else:
            run(test+'_compile',['iverilog','-g2012','-s',top,'-o',out/(top+'.vvp'),*sources,tb])
            run(test,['vvp',out/(top+'.vvp')])
        if 'PASS ' not in (out/(test+'.log')).read_text(): raise SystemExit(f'{test}: missing PASS marker')
    after=hashes(inputs)
    if before!=after: raise SystemExit('Inputs changed during validation; rerun against frozen sources')
    (out/'verification.json').write_text(json.dumps({'simulation_pass':True,'hardware_tested':False,
        'inputs_unchanged':True,'results':results},indent=2)+'\n')
    print(out)

if __name__=='__main__': main()
