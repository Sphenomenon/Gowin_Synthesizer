#!/usr/bin/env python3
"""Conditional recognition policy with real playback, USB owner and Flash guard."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline

REFERENCE='df2a822f5694c99bdba5d03b66b642a16f687673'
PREFIX='projects/138k/push2_workstation/usb_a/'
PLAYBACK='rtl/services/workstation_playback_service.sv'
OWNER='rtl/push2_usb_a_control.sv'
def sha(data):return hashlib.sha256(data).hexdigest()


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    names=[PLAYBACK,OWNER,'rtl/workstation/gw138k_push_workstation_top.v',
        'rtl/workstation/workstation_usb2_input.sv','rtl/workstation/workstation_profile_no_cnn_runtime.sv',
        'tools/workstation_recognition_policy.py','sim/architecture/tb_workstation_recognition_playback.sv',
        'sim/usb2/tb_workstation_no_cnn_owner.sv','sim/tb_pl_guide.sv',str(Path(__file__).relative_to(ROOT))]
    hashes={name:sha((ROOT/name).read_bytes()) for name in names}
    original=subprocess.check_output(['git','show',REFERENCE+':'+PREFIX+PLAYBACK],cwd=ROOT.parents[3]).decode()
    golden=output/'playback_reference.sv'
    assert original.count('module workstation_playback_service #(')==1
    golden.write_text(original.replace('module workstation_playback_service #(','module recognition_playback_reference #('))
    baseline=load_baseline(ROOT,'resource_rework_route0')
    support=[]
    for name in ('src/migration/gw138k_stream_cdc.sv','src/usb_host/gw138k_usb_event_fifo.v',
                 'src/push2/push2_midi_rx.sv','src/video/video_font_5x7.v'):
        target=output/Path(name).name;target.write_bytes(baseline.read_bytes(name));support.append(target)
    usb=[ROOT/OWNER,ROOT/'rtl/audio/push2_controls.sv',ROOT/'rtl/display_data/push2_surface_pixels.sv',
        *[ROOT/'rtl/push2'/name for name in ('push2_playlist_hold.sv','push2_song_menu.sv','push2_score_guide.sv',
            'push2_lights.sv','push2_led_tx.sv','push2_song_screen.sv')],*support]
    for p in usb:
        if p.is_relative_to(ROOT):hashes[str(p.relative_to(ROOT))]=sha(p.read_bytes())
    result=dict(schema=1,passed=False,source_sha256=hashes,reference=REFERENCE,
        reference_playback_sha256=sha(original.encode()),support_baseline=baseline.evidence(),
        support_sha256={str(p.name):sha(p.read_bytes()) for p in support},cases={},
        profile_activated=False,synthesis=False,pnr=False,hardware_tested=False,sram_programmed=False,flash_written=False)

    def execute(name,top,sources,expected=None):
        binary=output/(name+'.vvp');argv=['iverilog','-g2012','-s',top,'-o',str(binary),*map(str,sources)]
        compiled=subprocess.run(argv,text=True,capture_output=True,timeout=60)
        (output/(name+'_compile.log')).write_text(compiled.stdout+compiled.stderr)
        if compiled.returncode:raise RuntimeError(name+' compile failed: '+compiled.stdout+compiled.stderr)
        executed=subprocess.run(['vvp',str(binary)],text=True,capture_output=True,timeout=90)
        log=executed.stdout+executed.stderr;(output/(name+'_run.log')).write_text(log)
        case=dict(argv=argv,returncode=executed.returncode,log=log,compiled_source_sha256={str(p):sha(p.read_bytes()) for p in sources})
        if expected:
            case.update(expected_failure=expected,rejected=executed.returncode!=0 and expected in log)
            if not case['rejected']:raise ValueError(name+' mutant escaped: '+log)
        elif executed.returncode or 'PASS ' not in log:raise RuntimeError(name+' failed: '+log)
        else:print(log.strip(),flush=True)
        result['cases'][name]=case
        return binary

    try:
        playback_tb=ROOT/'sim/architecture/tb_workstation_recognition_playback.sv'
        execute('playback','tb_workstation_recognition_playback',[ROOT/PLAYBACK,golden,playback_tb])
        binary=execute('usb_disabled','tb_workstation_no_cnn_owner',usb+[ROOT/'sim/usb2/tb_workstation_no_cnn_owner.sv'])
        structure=binary.read_text()
        if '"u_guide"' in structure or '"u_song_menu"' in structure:raise ValueError('disabled CNN consumer still elaborated')
        execute('usb_enabled','tb_pl_guide',usb+[ROOT/'sim/tb_pl_guide.sv'])
        source=(ROOT/PLAYBACK).read_text()
        for name,anchor,replacement in (
            ('disabled_track_lost','assign reader_track_o=tf_track_i;',"assign reader_track_o=4'd0;"),
            ('disabled_model_restart','assign reader_restart_o=tf_restart_i;',"assign reader_restart_o=tf_restart_i || model_status_i==4'd14;"),
            ('disabled_fake_score_accept',"assign score_accept_o=1'b0;","assign score_accept_o=1'b1;")):
            if source.count(anchor)!=1:raise ValueError('playback mutant anchor drift')
            mutant=output/(name+'.sv');mutant.write_text(source.replace(anchor,replacement))
            execute(name,'tb_workstation_recognition_playback',[mutant,golden,playback_tb],
                    'disabled playback waited/restarted/accepted analysis')
        owner=(ROOT/OWNER).read_text();anchor='.guide_enabled_i(CNN_FOLLOW_ENABLE)'
        if owner.count(anchor)!=1:raise ValueError('USB mutant anchor drift')
        mutant=output/'disabled_button_swallowed.sv';mutant.write_text(owner.replace(anchor,".guide_enabled_i(1'b1)"))
        execute('disabled_button_swallowed','tb_workstation_no_cnn_owner',
            [mutant,*usb[1:],ROOT/'sim/usb2/tb_workstation_no_cnn_owner.sv'],'no CNN audio mapping changed')
        # A real guard instance must release every shared Flash output while CS
        # is inactive; off composition uses exactly these three inactive inputs.
        guard=ROOT/'rtl/music/basic_pitch_flash_io_guard.sv';tb=output/'flash_tb.sv'
        tb.write_text('''module tb_flash;
            wire cs,ck,mo,wp,hold,owned;
            basic_pitch_flash_io_guard dut(.spi_cs_n_i(1'b1),.spi_clk_i(1'b0),.spi_mosi_i(1'b0),
                .flash_cs_n_o(cs),.flash_clk_o(ck),.flash_mosi_o(mo),.flash_wp_n_o(wp),.flash_hold_n_o(hold),.owned_o(owned));
            initial begin #1;if({cs,ck,mo,wp,hold}!==5'bzzzzz || owned!==0)$fatal(1,"disabled Flash guard drove shared pads");
                $display("PASS disabled Flash guard all five pads Z");$finish;end
        endmodule
        ''')
        execute('flash_guard','tb_flash',[guard,tb])
        result['source_inputs_unchanged_during_run']=all(sha((ROOT/n).read_bytes())==h for n,h in hashes.items())
        if not result['source_inputs_unchanged_during_run']:raise ValueError('source changed during recognition verification')
        result['passed']=True
    finally:(output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
