"""Exact W-only streaming Pitch integration lineage; never generates RTL.

The M24 source parents and reviewed four maintained source identities are
whole-file bound. Every reverse edit round-trips to the same actual source.
M engine composition remains outside the D_ONLY_ENABLE generate branch.
"""
from pathlib import Path
import hashlib

POLICY = 'worker_continuous_pcm_pitch_integration_v1'
IMPLEMENTATION = 'rtl/audio/workstation_stream_pitch.sv'
IMPLEMENTATION_SHA256 = '973ebd9787837972f220ea4078eaf8462afe4bc8e758b382913accff3b5033ac'
PARENT_SHA256 = {'rtl/audio/gw138k_event_workstation.sv': '3082f2411b658903a869a77a78f19987f07577a11f42271c9155599c643d1d87',
 'rtl/control/workstation_parameters.sv': '47437fb03ad79e55cb3836df73ec0b66772bab8f2d315be366cb02964a0468a2',
 'firmware.c': 'b84d9e0c0191963d851f964ef6e674671ed68e00cd1b373d6efba4cd62ea54cf',
 'gw25k_panel.h': 'eebe5eb88aaaac2ed705effe7938d8161adc42205c1ff61c33feeefd91f8000e'}

CURRENT_SHA256 = {'rtl/audio/gw138k_event_workstation.sv': 'c94ef35bdd97e69bf0aabcd3dc0b773949771c42e2ab30178d94b592e3529747',
 'rtl/control/workstation_parameters.sv': '2dcba388e52d78adbc6817ba011a1b24a4b86c56048acaa8e4bdecf9236d2069',
 'firmware.c': 'd0bdf89eff7be0f0a23354f393315e13d531bb7eafbfc9afe3aaeee056cbc108',
 'gw25k_panel.h': '2598ccd24930d967d57e9a18900400fdfe92103078edb0ee3861079b535803f5'}

HUNKS = {'rtl/audio/gw138k_event_workstation.sv': [('  logic [31:0] vec_previous_rejected;\n'
                                            '  logic vec_previous_frequency_error;\n'
                                            '  logic signed [31:0] held_synth,held_vec_l,held_vec_r;\n'
                                            '  wire effects_valid=synth_joined && vec_joined;\n'
                                            "  wire [15:0] scope_morph_q15=scope_morph==127 ? 16'd32768 "
                                            ": {1'b0,scope_morph,8'd0};\n"
                                            "  wire [15:0] scope_scale_q15=scope_muted ? 16'd0 : "
                                            "scope_scale==127 ? 16'd32768 : {1'b0,scope_scale,8'd0};\n"
                                            '  assign '
                                            'scope_status_o={vec_rejected[15:0],cue_running,cue_done,cue_error,|cue_late,(scope_control_error '
                                            '|| '
                                            'tf_scope_control_o[15]),vec_frequency_error,vec_config_error,scope_enable,vec_active};\n',
                                            '  logic [31:0] vec_previous_rejected;\n'
                                            '  logic vec_previous_frequency_error;\n'
                                            '  logic signed [31:0] held_synth,held_vec_l,held_vec_r;\n'
                                            '  wire '
                                            'pcm_pitch_joined,pcm_pitch_quiet,pcm_pitch_fault,pcm_pitch_valid;\n'
                                            '  wire signed [31:0] pcm_pitch_left,pcm_pitch_right;\n'
                                            '  wire [6:0] pcm_crush,pcm_drive;\n'
                                            '  wire effects_valid=synth_joined && vec_joined && '
                                            'pcm_pitch_joined;\n'
                                            "  wire [15:0] scope_morph_q15=scope_morph==127 ? 16'd32768 "
                                            ": {1'b0,scope_morph,8'd0};\n"
                                            "  wire [15:0] scope_scale_q15=scope_muted ? 16'd0 : "
                                            "scope_scale==127 ? 16'd32768 : {1'b0,scope_scale,8'd0};\n"
                                            '  assign '
                                            'scope_status_o={vec_rejected[15:0],cue_running,cue_done,cue_error,|cue_late,(scope_control_error '
                                            '|| '
                                            'tf_scope_control_o[15]),vec_frequency_error,vec_config_error,scope_enable,vec_active};\n'),
                                           ('    end\n'
                                            '    wire history_accept=history_clear_i && '
                                            'history_ready_o;\n'
                                            '    assign runtime_config_busy=busy;\n'
                                            '    assign runtime_fault=failed || fx_fault;\n'
                                            '    // Block event admission on the broadcast edge so '
                                            'engine rate_ready is\n'
                                            '    // independent of a queued NoteOn. During the fenced '
                                            'wait, ordinary event\n'
                                            '    // dispatch resumes, including NoteOff/PANIC and '
                                            'existing loader pressure.\n',
                                            '    end\n'
                                            '    wire history_accept=history_clear_i && '
                                            'history_ready_o;\n'
                                            '    assign runtime_config_busy=busy;\n'
                                            '    assign runtime_fault=failed || fx_fault || '
                                            'pcm_pitch_fault;\n'
                                            '    // Block event admission on the broadcast edge so '
                                            'engine rate_ready is\n'
                                            '    // independent of a queued NoteOn. During the fenced '
                                            'wait, ordinary event\n'
                                            '    // dispatch resumes, including NoteOff/PANIC and '
                                            'existing loader pressure.\n'),
                                           ('      else begin\n'
                                            '        applied<=0;history_done<=0;\n'
                                            '        if(!busy && fx_history_done && !config_accept && '
                                            '!history_accept && !runtime_fault)history_done<=1;\n'
                                            '        if(fx_fault)failed<=1;\n'
                                            '        if(config_accept || history_accept)begin\n'
                                            '          busy<=1;is_config<=config_accept;\n'
                                            '          pending_rate<=config_accept ? rate_44100_i : '
                                            'committed_rate;\n',
                                            '      else begin\n'
                                            '        applied<=0;history_done<=0;\n'
                                            '        if(!busy && fx_history_done && !config_accept && '
                                            '!history_accept && !runtime_fault)history_done<=1;\n'
                                            '        if(fx_fault || pcm_pitch_fault)failed<=1;\n'
                                            '        if(config_accept || history_accept)begin\n'
                                            '          busy<=1;is_config<=config_accept;\n'
                                            '          pending_rate<=config_accept ? rate_44100_i : '
                                            'committed_rate;\n'),
                                           ('        if(engine_rate_commit)applied_rate<=rate_44100_i;\n'
                                            '      end\n'
                                            '    end\n'
                                            '    assign runtime_quiescent=!rendered;assign '
                                            'runtime_rate_ready=!rendered;assign '
                                            'engine_rate=applied_rate;\n'
                                            '    assign core_sample_ready=1;assign '
                                            'core_event_ready=1;assign core_expression_ready=1;\n'
                                            '    assign core_event_slot_ready=1;assign '
                                            'core_expression_slot_ready=1;\n'
                                            '    assign vec_event_ready=1;assign vec_ready=1;assign '
                                            'vec_busy=0;\n'
                                            '    assign synth_valid_o=rendered;assign synth_o=0;assign '
                                            'vec_valid=rendered;\n'
                                            '    assign vec_left=0;assign vec_right=0;assign '
                                            'vec_active=0;assign vec_count=0;assign vec_rejected=0;\n'
                                            '    assign vec_config_error=0;assign '
                                            'vec_frequency_error=0;assign vec_clip=0;\n'
                                            '    assign allocated=0;assign legacy_active_mask=0;assign '
                                            'legacy_active_count=0;\n'
                                            '    assign load_busy=0;assign mix_busy=0;assign '
                                            "issued=0;assign pitch_q20_o=22'd1048576;\n"
                                            "    assign mode_ready=1;assign mode_o=D_ONLY_ENABLE ? 2'd3 "
                                            ": 2'd2;\n"
                                            '  end else if(RUNTIME_RATE_ENABLE) begin: runtime_engines\n'
                                            '    workstation_runtime_render_engines '
                                            '#(.RUNTIME_RATE_ENABLE(1)) engines(\n',
                                            '        if(engine_rate_commit)applied_rate<=rate_44100_i;\n'
                                            '      end\n'
                                            '    end\n'
                                            '    assign runtime_quiescent=!rendered && '
                                            'pcm_pitch_quiet;assign runtime_rate_ready=!rendered && '
                                            'pcm_pitch_quiet;assign engine_rate=applied_rate;\n'
                                            '    assign core_sample_ready=pcm_pitch_quiet;assign '
                                            'core_event_ready=1;assign core_expression_ready=1;\n'
                                            '    assign core_event_slot_ready=1;assign '
                                            'core_expression_slot_ready=1;\n'
                                            '    assign vec_event_ready=1;assign vec_ready=1;assign '
                                            'vec_busy=0;\n'
                                            '    assign synth_valid_o=rendered;assign synth_o=0;assign '
                                            'vec_valid=rendered;\n'
                                            '    assign vec_left=0;assign vec_right=0;assign '
                                            'vec_active=0;assign vec_count=0;assign vec_rejected=0;\n'
                                            '    assign vec_config_error=0;assign '
                                            'vec_frequency_error=0;assign vec_clip=0;\n'
                                            '    assign allocated=0;assign legacy_active_mask=0;assign '
                                            'legacy_active_count=0;\n'
                                            '    assign load_busy=0;assign mix_busy=0;assign '
                                            'issued=0;assign pitch_q20_o=D_ONLY_ENABLE ? target_ratio : '
                                            "22'd1048576;\n"
                                            "    assign mode_ready=1;assign mode_o=D_ONLY_ENABLE ? 2'd3 "
                                            ": 2'd2;\n"
                                            '  end else if(RUNTIME_RATE_ENABLE) begin: runtime_engines\n'
                                            '    workstation_runtime_render_engines '
                                            '#(.RUNTIME_RATE_ENABLE(1)) engines(\n'),
                                           ('  end endgenerate\n'
                                            "  assign active_mask_o=scope_enable ? {24'd0,vec_active} : "
                                            'legacy_active_mask;\n'
                                            '  assign active_voice_count_o=scope_enable ? '
                                            "{2'd0,vec_count} : legacy_active_count;\n"
                                            '  // Join independently scheduled engines before the '
                                            'existing P10 input mixer.\n'
                                            '  always_ff @(posedge clk_i or negedge rst_ni) begin\n'
                                            '    if(!rst_ni) begin '
                                            'synth_joined<=0;vec_joined<=0;held_synth<=0;held_vec_l<=0;held_vec_r<=0;held_vec_clip<=0;end\n',
                                            '  end endgenerate\n'
                                            "  assign active_mask_o=scope_enable ? {24'd0,vec_active} : "
                                            'legacy_active_mask;\n'
                                            '  assign active_voice_count_o=scope_enable ? '
                                            "{2'd0,vec_count} : legacy_active_count;\n"
                                            '  generate if(D_ONLY_ENABLE)begin: streaming_pcm_pitch\n'
                                            '    logic joined;\n'
                                            '    logic [6:0] held_crush,held_drive;\n'
                                            '    wire quiet,ready;\n'
                                            '    wire clear=engine_clear || engine_rate_commit || '
                                            '(history_clear_i && history_ready_o);\n'
                                            '    // The existing source-session history transaction and '
                                            'native cancellation\n'
                                            '    // own this history too. A new epoch cannot replay an '
                                            'old read-head tail.\n'
                                            '    workstation_stream_pitch pitch(\n'
                                            '        '
                                            '.clk_i,.rst_ni,.clear_i(clear),.valid_i(core_ce),.enable_i(effect_master),\n'
                                            '        '
                                            '.ratio_q20_i(target_ratio),.left_i(pcm_left_i),.right_i(pcm_right_i),\n'
                                            '        '
                                            '.ready_o(ready),.quiescent_o(quiet),.valid_o(pcm_pitch_valid),\n'
                                            '        '
                                            '.fault_o(pcm_pitch_fault),.left_o(pcm_pitch_left),.right_o(pcm_pitch_right));\n'
                                            '    // Observe stored work rather than ready (which '
                                            'contains the same-edge\n'
                                            '    // clear request). This prevents configuration '
                                            'admission feeding itself.\n'
                                            '    assign pcm_pitch_quiet=quiet && !pcm_pitch_valid && '
                                            '!joined;\n'
                                            '    assign pcm_pitch_joined=joined;\n'
                                            '    assign pcm_crush=held_crush;assign '
                                            'pcm_drive=held_drive;\n'
                                            '    always_ff @(posedge clk_i or negedge rst_ni)begin\n'
                                            '      if(!rst_ni)begin '
                                            'joined<=0;held_crush<=0;held_drive<=0;end\n'
                                            '      else if(clear || panic_accept)begin '
                                            'joined<=0;held_crush<=0;held_drive<=0;end\n'
                                            '      else begin\n'
                                            '        if(core_ce)begin '
                                            'held_crush<=d_crush;held_drive<=d_drive;end\n'
                                            '        if(pcm_pitch_valid && frame_inflight)joined<=1;\n'
                                            '        if(effects_valid && fx_ready)joined<=0;\n'
                                            '      end\n'
                                            '    end\n'
                                            '  end else begin: no_streaming_pcm_pitch\n'
                                            '    assign pcm_pitch_quiet=1;assign pcm_pitch_joined=1;\n'
                                            '    assign pcm_pitch_fault=0;assign pcm_pitch_valid=0;\n'
                                            '    assign pcm_pitch_left=0;assign pcm_pitch_right=0;\n'
                                            '    assign pcm_crush=0;assign pcm_drive=0;\n'
                                            '  end endgenerate\n'
                                            '  // Join independently scheduled engines before the '
                                            'existing P10 input mixer.\n'
                                            '  always_ff @(posedge clk_i or negedge rst_ni) begin\n'
                                            '    if(!rst_ni) begin '
                                            'synth_joined<=0;vec_joined<=0;held_synth<=0;held_vec_l<=0;held_vec_r<=0;held_vec_clip<=0;end\n'),
                                           ('          frame_inflight<=1;\n'
                                            '        end\n'
                                            '        if(core_ce) begin pending<=0;\n'
                                            '          held_pcm_l<=D_ONLY_ENABLE ? '
                                            'd_process(pcm_left_i,d_crush,d_drive) : pcm_left_i;\n'
                                            '          held_pcm_r<=D_ONLY_ENABLE ? '
                                            'd_process(pcm_right_i,d_crush,d_drive) : pcm_right_i;\n'
                                            '        end\n'
                                            '        if(effects_valid && !fx_ready) '
                                            'deadline_miss_o<=deadline_miss_o+1;\n'
                                            '      end\n',
                                            '          frame_inflight<=1;\n'
                                            '        end\n'
                                            '        if(core_ce) begin pending<=0;\n'
                                            '          if(!D_ONLY_ENABLE)begin '
                                            'held_pcm_l<=pcm_left_i;held_pcm_r<=pcm_right_i;end\n'
                                            '        end\n'
                                            '        if(D_ONLY_ENABLE && pcm_pitch_valid && '
                                            'frame_inflight)begin\n'
                                            '          '
                                            'held_pcm_l<=d_process(pcm_pitch_left,pcm_crush,pcm_drive);\n'
                                            '          '
                                            'held_pcm_r<=d_process(pcm_pitch_right,pcm_crush,pcm_drive);\n'
                                            '        end\n'
                                            '        if(effects_valid && !fx_ready) '
                                            'deadline_miss_o<=deadline_miss_o+1;\n'
                                            '      end\n')],
 'rtl/control/workstation_parameters.sv': [('    assign effect_state_o = '
                                            "{23'd0,effect_master_o,effect_count_o,effect_order_o};\n"
                                            '    assign effect_mask_o = effect_master_o ? '
                                            '(effect_selected_o |\n'
                                            "        (D_ONLY_ENABLE && d_delay_send_o!=0 ? 3'b001 : "
                                            "3'b000)) : 3'b000;\n"
                                            '    assign options_o = D_ONLY_ENABLE ? '
                                            "{11'd0,d_delay_send_o,d_drive_o,d_crush_o} :\n"
                                            '        {snapshot_request, bend_index_o, glide_cc_o, '
                                            'vibrato_depth_o,\n'
                                            "        sustain_o, target_ratio_o != 22'd1048576, "
                                            'glide_step_o != 0, vibrato_depth_o != 0};\n'
                                            '\n',
                                            '    assign effect_state_o = '
                                            "{23'd0,effect_master_o,effect_count_o,effect_order_o};\n"
                                            '    assign effect_mask_o = effect_master_o ? '
                                            '(effect_selected_o |\n'
                                            "        (D_ONLY_ENABLE && d_delay_send_o!=0 ? 3'b001 : "
                                            "3'b000)) : 3'b000;\n"
                                            '    assign options_o = D_ONLY_ENABLE ? '
                                            "{3'd0,bend_index_o,d_delay_send_o,d_drive_o,d_crush_o} :\n"
                                            '        {snapshot_request, bend_index_o, glide_cc_o, '
                                            'vibrato_depth_o,\n'
                                            "        sustain_o, target_ratio_o != 22'd1048576, "
                                            'glide_step_o != 0, vibrato_depth_o != 0};\n'
                                            '\n'),
                                           ('                sustain_o <= 0;\n'
                                            '                if(D_ONLY_ENABLE)begin\n'
                                            '                    '
                                            'd_crush_o<=0;d_drive_o<=0;d_delay_send_o<=0;\n'
                                            '                    '
                                            'effect_selected_o<=0;effect_count_o<=0;\n'
                                            '                    '
                                            "effect_order_o<=6'b10_01_00;effect_master_o<=1;\n"
                                            '                end\n',
                                            '                sustain_o <= 0;\n'
                                            '                if(D_ONLY_ENABLE)begin\n'
                                            '                    '
                                            'd_crush_o<=0;d_drive_o<=0;d_delay_send_o<=0;\n'
                                            '                    '
                                            "target_ratio_o<=22'd1048576;bend_index_o<=8'd128;\n"
                                            '                    '
                                            'effect_selected_o<=0;effect_count_o<=0;\n'
                                            '                    '
                                            "effect_order_o<=6'b10_01_00;effect_master_o<=1;\n"
                                            '                end\n'),
                                           ('                        120, 123: begin sustain_o <= 0;\n'
                                            '                            if(D_ONLY_ENABLE)begin\n'
                                            '                                '
                                            'd_crush_o<=0;d_drive_o<=0;d_delay_send_o<=0;\n'
                                            '                                '
                                            'effect_selected_o<=0;effect_count_o<=0;\n'
                                            '                                '
                                            "effect_order_o<=6'b10_01_00;effect_master_o<=1;\n"
                                            '                            end\n',
                                            '                        120, 123: begin sustain_o <= 0;\n'
                                            '                            if(D_ONLY_ENABLE)begin\n'
                                            '                                '
                                            'd_crush_o<=0;d_drive_o<=0;d_delay_send_o<=0;\n'
                                            '                                '
                                            "target_ratio_o<=22'd1048576;bend_index_o<=8'd128;\n"
                                            '                                '
                                            'effect_selected_o<=0;effect_count_o<=0;\n'
                                            '                                '
                                            "effect_order_o<=6'b10_01_00;effect_master_o<=1;\n"
                                            '                            end\n')],
 'firmware.c': [('#else\n'
                 '/* W-DEMO retains the same Host and PL transport, with no Push surface code. */\n'
                 'static uint16_t worker_keys,worker_blocked_keys;\n'
                 '#endif\n'
                 '// P138 has one 32-bit USB IN diagnostic word.  Keep four independent,\n'
                 '// saturating byte counters so a long idle NAK stream cannot wrap into a\n',
                 '#else\n'
                 '/* W-DEMO retains the same Host and PL transport, with no Push surface code. */\n'
                 'static uint16_t worker_keys,worker_blocked_keys;\n'
                 "/* Last physical slider request, only for H's temporary dry composition.\n"
                 ' * Applied pitch remains owned and reported by the audio parameter RTL. */\n'
                 'static uint16_t worker_bend=8192;\n'
                 '#endif\n'
                 '// P138 has one 32-bit USB IN diagnostic word.  Keep four independent,\n'
                 '// saturating byte counters so a long idle NAK stream cannot wrap into a\n'),
                ('#ifndef WORKSTATION_WORKER_DEMO\n'
                 '    displayed_state_valid=0;\n'
                 '#else\n'
                 '    worker_keys=0;worker_blocked_keys=0;\n'
                 '#endif\n'
                 '    // Existing RTL releases held notes and resets LED/display initialization.\n'
                 '    // Audio, HDMI, DDR and AE350 continue running throughout reconnection.\n',
                 '#ifndef WORKSTATION_WORKER_DEMO\n'
                 '    displayed_state_valid=0;\n'
                 '#else\n'
                 '    worker_keys=0;worker_blocked_keys=0;worker_bend=8192;\n'
                 '#endif\n'
                 '    // Existing RTL releases held notes and resets LED/display initialization.\n'
                 '    // Audio, HDMI, DDR and AE350 continue running throughout reconnection.\n'),
                ('     * temporarily requests dry; releasing it restores only still-held keys. */\n'
                 '    unsigned keys=(worker_keys&(1u<<7))?0:worker_keys,mask=0;\n'
                 '    for(unsigned key=3;key<6;key++)if(keys&(1u<<key))mask|=1u<<(key-3);\n'
                 '    if(keys&(1u<<6))mask=7;\n'
                 '    for(unsigned key=8;key<15;key++)if(keys&(1u<<key))mask|=key-7;\n'
                 '    for(unsigned key=0;key<3;key++)\n'
                 '        MMIO(0x54)=(2u<<14)|((20u+key)<<7)|((keys&(1u<<key))?100u:0u);\n',
                 '     * temporarily requests dry; releasing it restores only still-held keys. */\n'
                 '    unsigned keys=(worker_keys&(1u<<7))?0:worker_keys,mask=0;\n'
                 '    for(unsigned key=3;key<6;key++)if(keys&(1u<<key))mask|=1u<<(key-3);\n'
                 '    for(unsigned key=8;key<15;key++)if(keys&(1u<<key))mask|=key-7;\n'
                 '    for(unsigned key=0;key<3;key++)\n'
                 '        MMIO(0x54)=(2u<<14)|((20u+key)<<7)|((keys&(1u<<key))?100u:0u);\n'),
                ('        }\n'
                 '        if(down==!!(worker_keys&bit))return;\n'
                 '        if(down)worker_keys|=(uint16_t)bit;else worker_keys&=(uint16_t)~bit;\n'
                 '        if(key!=15){worker_commit_touch();return;}\n'
                 '        if(!down)return;\n'
                 '        kind=2;a=7;b=127; // P is the existing main-volume action.\n'
                 '    } else if(kind!=2 || (a!=7 && a!=11 && a!=20 && a!=21 && a!=22 &&\n'
                 '                         a!=81 && a!=82 && a!=84 && a!=85 && a!=86 &&\n'
                 '                         a!=87 && a!=88 && a!=120 && a!=123))return;\n'
                 '    if(kind==2 && (a==120 || a==123)) {\n'
                 '        worker_blocked_keys|=worker_keys;worker_keys=0;\n'
                 '        // W has no note engine. Both panel clear commands use its existing\n'
                 '        // urgent lifecycle path, which resumes D without requiring NoteOn.\n'
                 '        a=120;\n',
                 '        }\n'
                 '        if(down==!!(worker_keys&bit))return;\n'
                 '        if(down)worker_keys|=(uint16_t)bit;else worker_keys&=(uint16_t)~bit;\n'
                 '        if(key!=15){\n'
                 '            worker_commit_touch();\n'
                 '            if(key==6 || key==7){\n'
                 '                unsigned bend=(worker_keys&(1u<<6)) && '
                 '!(worker_keys&(1u<<7))?worker_bend:8192u;\n'
                 '                MMIO(0x54)=(4u<<14)|((bend&127u)<<7)|(bend>>7);\n'
                 '            }\n'
                 '            return;\n'
                 '        }\n'
                 '        if(!down)return;\n'
                 '        kind=2;a=7;b=127; // P is the existing main-volume action.\n'
                 '    } else if(kind==4) {\n'
                 '        worker_bend=(uint16_t)((b<<7)|a);\n'
                 '        /* G is momentary Pitch; the physical slider remains centered on\n'
                 '         * release. H temporarily requests dry, preserving only live input. */\n'
                 '        if(!(worker_keys&(1u<<6)) || (worker_keys&(1u<<7)))return;\n'
                 '    } else if(kind!=2 || (a!=7 && a!=11 && a!=20 && a!=21 && a!=22 &&\n'
                 '                         a!=81 && a!=82 && a!=84 && a!=85 && a!=86 &&\n'
                 '                         a!=87 && a!=88 && a!=120 && a!=123))return;\n'
                 '    if(kind==2 && (a==120 || a==123)) {\n'
                 '        worker_blocked_keys|=worker_keys;worker_keys=0;worker_bend=8192;\n'
                 '        // W has no note engine. Both panel clear commands use its existing\n'
                 '        // urgent lifecycle path, which resumes D without requiring NoteOn.\n'
                 '        a=120;\n')],
 'gw25k_panel.h': [('    const uint32_t *s=gw.scene;\n'
                    '#ifdef WORKSTATION_WORKER_DEMO\n'
                    '    /* Values are committed audio-owner feedback, never a Host shadow of the\n'
                    '     * touch requests. W reuses options[20:0] for its three D depths. */\n'
                    '    gw_copy(gw.line1,"D STREAM  GAIN 000  OUT ",sizeof "D STREAM  GAIN 000  OUT '
                    '");\n'
                    '    gw_decimal(gw.line1+15,(s[0]>>16)>=32768u?127u:(s[0]>>24),3);\n'
                    '    gw_copy(gw.line1+24,routes[(s[0]>>5)&3u],7);\n',
                    '    const uint32_t *s=gw.scene;\n'
                    '#ifdef WORKSTATION_WORKER_DEMO\n'
                    '    /* Values are committed audio-owner feedback, never a Host shadow of the\n'
                    '     * touch requests. W reports D depths in options[20:0], pitch index[28:21]. '
                    '*/\n'
                    '    gw_copy(gw.line1,"D STREAM  GAIN 000  OUT ",sizeof "D STREAM  GAIN 000  OUT '
                    '");\n'
                    '    gw_decimal(gw.line1+15,(s[0]>>16)>=32768u?127u:(s[0]>>24),3);\n'
                    '    gw_copy(gw.line1+24,routes[(s[0]>>5)&3u],7);\n'),
                   ('    gw_decimal(gw.line2+6,s[1]&127u,3);\n'
                    '    gw_decimal(gw.line2+16,(s[1]>>7)&127u,3);\n'
                    '    gw_decimal(gw.line2+25,(s[1]>>14)&127u,3);\n'
                    '    gw_copy(gw.line3,"FX DCR 000  TOUCH A-C HOLD",sizeof "FX DCR 000  TOUCH A-C '
                    'HOLD");\n'
                    '    '
                    "gw.line3[7]=(s[0]&1u)?'1':'0';gw.line3[8]=(s[0]&2u)?'1':'0';gw.line3[9]=(s[0]&4u)?'1':'0';\n"
                    '    gw_copy(gw.line4,"D-F CHAIN G MASTER H CLEAR",sizeof "D-F CHAIN G MASTER H '
                    'CLEAR");\n'
                    '#else\n'
                    '    unsigned profile=(s[0]>>7)&7u,mode=(s[0]>>3)&3u;\n'
                    '    gw_copy(gw.line1,"NOTE 000  VEL 000  GAIN 000  TONE ",sizeof "NOTE 000  VEL '
                    '000  GAIN 000  TONE ");\n',
                    '    gw_decimal(gw.line2+6,s[1]&127u,3);\n'
                    '    gw_decimal(gw.line2+16,(s[1]>>7)&127u,3);\n'
                    '    gw_decimal(gw.line2+25,(s[1]>>14)&127u,3);\n'
                    '    gw_copy(gw.line3,"FX DCR 000  PITCH IDX 000",sizeof "FX DCR 000  PITCH IDX '
                    '000");\n'
                    '    '
                    "gw.line3[7]=(s[0]&1u)?'1':'0';gw.line3[8]=(s[0]&2u)?'1':'0';gw.line3[9]=(s[0]&4u)?'1':'0';\n"
                    '    gw_decimal(gw.line3+22,(s[1]>>21)&255u,3);\n'
                    '    gw_copy(gw.line4,"G PITCH + SLIDER  H DRY",sizeof "G PITCH + SLIDER  H DRY");\n'
                    '#else\n'
                    '    unsigned profile=(s[0]>>7)&7u,mode=(s[0]>>3)&3u;\n'
                    '    gw_copy(gw.line1,"NOTE 000  VEL 000  GAIN 000  TONE ",sizeof "NOTE 000  VEL '
                    '000  GAIN 000  TONE ");\n')]}


def sha(source):
    return hashlib.sha256(source).hexdigest()


def restore_parent(relative, source):
    relative = str(relative)
    from tools.workstation_pr2_storage_reference import RECORDS, restore_parent as restore_merged
    if relative in RECORDS and sha(source) == RECORDS[relative]['current_sha256']:
        source, _ = restore_merged(source, relative)
    if relative not in HUNKS or sha(source) != CURRENT_SHA256[relative]:
        raise ValueError('Streaming Pitch integration source identity changed: ' + relative)
    current = source.decode()
    for before, after in reversed(HUNKS[relative]):
        if not after or current.count(after) != 1:
            raise ValueError('Streaming Pitch reverse anchor drift: ' + relative)
        current = current.replace(after, before)
    parent = current.encode()
    if sha(parent) != PARENT_SHA256[relative]:
        raise ValueError('Streaming Pitch parent identity changed: ' + relative)
    for before, after in HUNKS[relative]:
        if not before or current.count(before) != 1:
            raise ValueError('Streaming Pitch forward anchor drift: ' + relative)
        current = current.replace(before, after)
    if current.encode() != source:
        raise ValueError('Streaming Pitch roundtrip changed bytes: ' + relative)
    return parent


def normalize_source(relative, source):
    relative = str(relative)
    if relative in PARENT_SHA256 and sha(source) == PARENT_SHA256[relative]:
        return source
    return restore_parent(relative, source)


def source_bundle(root):
    root = Path(root)
    if sha((root / IMPLEMENTATION).read_bytes()) != IMPLEMENTATION_SHA256:
        raise ValueError('Streaming Pitch DSP implementation identity changed')
    owners = {}
    for name in HUNKS:
        source = (root / name).read_bytes()
        parent = normalize_source(name, source)
        owners[name] = dict(current_source_sha256=sha(source), parent_source_sha256=sha(parent),
                           stage='parent' if source == parent else 'stream_pitch',
                           exact_inverse_and_roundtrip=True)
    stages = {v['stage'] for v in owners.values()}
    if len(stages) != 1:
        raise ValueError('Streaming Pitch integration uses mixed source stages')
    return dict(policy=POLICY, stage=next(iter(stages)), owners=owners,
                implementation=IMPLEMENTATION, implementation_sha256=IMPLEMENTATION_SHA256,
                enable_condition='D_ONLY_ENABLE (worker image); M remains disabled',
                sole_ratio_owner='rtl/control/workstation_parameters.sv',
                lifecycle='native clear, actual accepted rate/history broadcast',
                momentary='25K G + standard Pitch Bend; H temporary dry; O DCR',
                physical_timing_verified=False, hardware_tested=False)
