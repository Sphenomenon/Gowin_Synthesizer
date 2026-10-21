"""Add an independent old-workstation instance to the real USB attach fixture."""
from pathlib import Path
import re


def add_reference(staged, reference):
    old=reference.read_text()
    if old.count('module gw138k_event_workstation #')!=1:
        raise ValueError('unexpected old workstation module')
    module=staged/'workstation_reference.sv'
    module.write_text(old.replace('module gw138k_event_workstation #','module gw138k_event_workstation_reference #',1))
    tb=staged/'sim/tb_workstation_attach.sv';text=tb.read_text()
    start=text.index('    gw138k_event_workstation audio(');end=text.index(');',start)+2
    duplicate=text[start:end].replace('gw138k_event_workstation audio(', 'gw138k_event_workstation_reference reference_audio(')
    duplicate=re.sub(r'(\.[A-Za-z0-9_]+_o)\([^)]*\)',r'\1()',duplicate)
    observed=['cpu_event_ready_o','core_event_valid','core_note_on','core_note','core_velocity',
        'core_expression_valid','core_expression_note','core_expression_value','event_ready',
        'held','deferred','releasing','release_index','panic_epoch_o','applied_events_o',
        'sample_valid_o','left_o','right_o','active_mask_o','active_voice_count_o','note_drop_o',
        'control_options_o','effect_mask_o','effect_order_o','effect_count','effect_master',
        'requested_mode','mode_pending','volume','expression_gain','pcm_gain_o','route_o',
        'profile_o','target_ratio','glide_step','vibrato_depth','glide_cc','bend_index',
        'sustain','scope_status_o','tf_scope_control_o','panel_event_valid_o','panel_command_o']
    before='{'+','.join('audio.'+name for name in observed)+'}'
    after='{'+','.join('reference_audio.'+name for name in observed)+'}'
    checker='''
    reg ab_stress=0;
    integer ab_cycles=0,ab_release_cycles=0,ab_panic_during_release=0;
    always @(posedge aclk)if(rn && audio.usb_lifecycle && audio.releasing)ab_panic_during_release++;
    always @(negedge aclk)begin
        #1;if(rn)begin
            ab_cycles++;
            if('''+before+' !== '+after+''')$fatal(1,"old/new workstation event or PCM mismatch");
            if(audio.releasing)begin
                ab_release_cycles++;
                if(audio.deferred_current !== audio.deferred[audio.release_index])$fatal(1,"deferred cursor invariant");
            end
        end
    end
'''
    text=text[:end]+'\n'+duplicate+checker+text[end:]
    if text.count('if(deadline || overflow || drops)')!=1:raise ValueError('missing normal no-fault guard')
    text=text.replace('if(deadline || overflow || drops)','if(deadline || overflow || (drops && !ab_stress))')
    anchor='        $display("PASS attach:'
    if text.count(anchor)!=1:raise ValueError('missing attach conclusion anchor')
    stimulus='''        ab_stress=1;
        put(0,7);wait(dut.input_settled);samples(2);
        midi(2,120,0);samples(1);
        for(integer value=0;value<128;value++)begin
            midi(2,7,value);midi(2,11,value);midi(2,16,value);
            midi(2,1,value);midi(2,5,value);midi(2,64,value);
            midi(2,80,value);midi(2,81,value);midi(2,82,value);midi(2,83,value);
            midi(2,84,value);midi(2,85,value);midi(2,86,value);midi(2,87,value);
            midi(2,88,value);midi(2,89,value);midi(2,90,value);midi(2,91,value);
            midi(2,92,value);midi(2,93,value);midi(2,94,value);midi(2,95,value);
            midi(2,96,value);midi(2,97,value);midi(2,98,value);midi(2,99,value);
            midi(2,100,value);midi(2,101,value);midi(2,103,value);midi(2,104,value);
            midi(3,value,0);midi(4,value,127-value);midi(6,value,0);
            samples(1);midi(2,120,0);samples(1);
        end
        // MIDI0/127 exercise original rejection behavior too; the old/new
        // drop counters must agree while deadline and overflow remain zero.
        // All cursor boundaries, including MIDI0/127, both engines and CC123.
        put(0,7);wait(dut.input_settled);samples(2);midi(2,80,0);samples(2);
        for(integer round=0;round<6;round++)begin
            midi(2,120,0);samples(1);midi(2,90,round%2 ? 127 : 0);samples(1);
            midi(2,64,127);
            for(integer key=0;key<7;key++)midi(1,key==0?0:key==1?1:key==2?31:key==3?63:key==4?64:key==5?(round%2?94:126):(round%2?95:127),100);
            samples(1);
            for(integer key=0;key<7;key++)midi(0,key==0?0:key==1?1:key==2?31:key==3?63:key==4?64:key==5?(round%2?94:126):(round%2?95:127),0);
            midi(2,64,0);samples(2);wait(!audio.releasing);
            if(audio.deferred)$fatal(1,"release did not clear deferred map");
            for(integer key=0;key<7;key++)midi(1,30+key,100);
            midi(2,123,0);samples(2);wait(!audio.releasing);
        end
        midi(2,120,0);samples(1);midi(2,90,0);midi(2,64,127);
        midi(1,0,100);midi(1,127,100);samples(1);midi(0,0,0);midi(0,127,0);
        midi(2,64,0);wait(audio.releasing);repeat(8)@(negedge aclk);midi(2,120,0);samples(2);
        if(ab_release_cycles<1000 || ab_panic_during_release<1)$fatal(1,"insufficient cursor cancellation coverage %0d/%0d",ab_release_cycles,ab_panic_during_release);
        $display("PASS release_cursor_ab: cycles=%0d release_cycles=%0d emergency_boundaries=%0d, MIDI0/127, both engines, sustain/CC123, exact per-cycle events/PCM",ab_cycles,ab_release_cycles,ab_panic_during_release);
'''
    text=text.replace(anchor,stimulus+anchor);tb.write_text(text)
    return module,[reference,module,tb,Path(__file__).resolve()]
