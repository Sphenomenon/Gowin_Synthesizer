"""Exact maintained dispatch-slot source lineage; never generates production RTL.

The reviewed three-owner change is normalized before the immutable oscillator
release/expression lineage. Every accepted byte belongs to one of two locked
whole-source identities; partial adaptations and mixed owner stages fail.
"""
from pathlib import Path
import hashlib

POLICY = 'native_dispatch_stored_slots_v1'
ORIGINAL_SHA256 = {'rtl/audio/gw138k_event_workstation.sv': '19222032cf9d0e2ebf33b1ad100ad4dc3b2efa4207b7f491beb9d5c5ee823738',
 'rtl/audio/workstation_runtime_render_engines.sv': 'cd4ed71690c7780c047f350ee0c51818643a2768774793a68a0019810ffa2ae3',
 'rtl/audio/workstation_runtime_oscillator_engine.sv': 'ab0fe039cde6f5274c9edcaf79425cd78b31b652ca2d2d580af18f4aa17b5ab4'}

CURRENT_SHA256 = {'rtl/audio/gw138k_event_workstation.sv': '3082f2411b658903a869a77a78f19987f07577a11f42271c9155599c643d1d87',
 'rtl/audio/workstation_runtime_render_engines.sv': '56a9d0719f0896fd61c16e274168d1b54ad6b5710d4cd9f781762ee6f47a9d57',
 'rtl/audio/workstation_runtime_oscillator_engine.sv': '757e734ca7225f168b84ec161f2bb080d849ebed76b0878e337392e7efb493d3'}

HUNKS = {'rtl/audio/gw138k_event_workstation.sv': [['  logic core_event_valid, core_event_ready, core_note_on;\n'
                                            '  logic core_expression_valid, core_expression_ready;\n'
                                            '  logic [6:0] core_note, core_velocity;\n'
                                            '  logic [6:0] core_expression_note, core_expression_value;\n',
                                            '  logic core_event_valid, core_event_ready, core_note_on;\n'
                                            '  logic core_expression_valid, core_expression_ready;\n'
                                            '  wire core_event_slot_ready,core_expression_slot_ready;\n'
                                            '  logic '
                                            'core_event_dispatch_ready,core_expression_dispatch_ready;\n'
                                            '  logic [6:0] core_note, core_velocity;\n'
                                            '  logic [6:0] core_expression_note, core_expression_value;\n'],
                                           ['  assign full = scope_enable ? &vec_active : &allocated;\n'
                                            '  assign dispatch=!usb_lifecycle && (!pending || '
                                            'runtime_config_busy) && !sample_ce_i && !event_config_block && '
                                            '!native_clear && !load_busy && !mix_busy && !vec_busy && '
                                            '!(TIMING_OPTIMIZED ? (mode_pending && allocated==0) : '
                                            'mode_valid);\n'
                                            '  // CC120 uses the control-event dispatch condition directly. '
                                            'It never needs\n'
                                            '  // engine event_ready; keeping that dependency out of '
                                            'cancellation also\n',
                                            '  assign full = scope_enable ? &vec_active : &allocated;\n'
                                            '  assign dispatch=!usb_lifecycle && (!pending || '
                                            'runtime_config_busy) && !sample_ce_i && !event_config_block && '
                                            '!native_clear && !load_busy && !mix_busy && !vec_busy && '
                                            '!(TIMING_OPTIMIZED ? (mode_pending && allocated==0) : '
                                            'mode_valid);\n'
                                            '  // Dispatch excludes a pending mode with no allocated voices. '
                                            'Otherwise\n'
                                            "  // mode_pending is zero or the oscillator's mode_ready is "
                                            'zero, so no mode\n'
                                            '  // can commit on this edge. Expression dispatch also has no '
                                            'NoteOn/Off.\n'
                                            '  // Use the stored engine slot here instead of feeding '
                                            'mode_valid (and the\n'
                                            '  // sample/fault admission cone behind it) back through the '
                                            'full ready path.\n'
                                            '  // Keep the public engine handshakes and unknown-state '
                                            'behavior intact.\n'
                                            '  generate if(TIMING_OPTIMIZED && RUNTIME_RATE_ENABLE)begin: '
                                            'engine_dispatch_slots\n'
                                            '    always_comb begin\n'
                                            "      case({mode_pending,allocated==32'd0})\n"
                                            "        2'b00,2'b01,2'b10,2'b11: begin\n"
                                            '          core_event_dispatch_ready=core_event_slot_ready;\n'
                                            '          '
                                            'core_expression_dispatch_ready=core_expression_slot_ready;\n'
                                            '        end\n'
                                            '        default: begin\n'
                                            '          core_event_dispatch_ready=core_event_ready;\n'
                                            '          '
                                            'core_expression_dispatch_ready=core_expression_ready;\n'
                                            '        end\n'
                                            '      endcase\n'
                                            '    end\n'
                                            '  end else begin: original_engine_dispatch_slots\n'
                                            '    assign core_event_dispatch_ready=core_event_ready;\n'
                                            '    assign '
                                            'core_expression_dispatch_ready=core_expression_ready;\n'
                                            '  end endgenerate\n'
                                            '  // CC120 uses the control-event dispatch condition directly. '
                                            'It never needs\n'
                                            '  // engine event_ready; keeping that dependency out of '
                                            'cancellation also\n'],
                                           ['        // handshake, so held state cannot advance while its '
                                            'event is rejected.\n'
                                            '        event_ready=dispatch && ((TIMING_OPTIMIZED && '
                                            '!RUNTIME_RATE_ENABLE) ||\n'
                                            '            (kind==1 && full) || (scope_enable ? '
                                            'vec_dispatch_ready : core_event_ready));\n'
                                            '      end else if(kind==5) begin\n'
                                            '        core_expression_valid=dispatch && '
                                            'core_expression_ready;\n'
                                            '        event_ready=dispatch && core_expression_ready;\n'
                                            '      end else event_ready=dispatch;\n'
                                            '    end\n',
                                            '        // handshake, so held state cannot advance while its '
                                            'event is rejected.\n'
                                            '        event_ready=dispatch && ((TIMING_OPTIMIZED && '
                                            '!RUNTIME_RATE_ENABLE) ||\n'
                                            '            (kind==1 && full) || (scope_enable ? '
                                            'vec_dispatch_ready : core_event_dispatch_ready));\n'
                                            '      end else if(kind==5) begin\n'
                                            '        core_expression_valid=dispatch && '
                                            'core_expression_dispatch_ready;\n'
                                            '        event_ready=dispatch && '
                                            'core_expression_dispatch_ready;\n'
                                            '      end else event_ready=dispatch;\n'
                                            '    end\n'],
                                           ['    assign runtime_quiescent=!rendered;assign '
                                            'runtime_rate_ready=!rendered;assign engine_rate=applied_rate;\n'
                                            '    assign core_sample_ready=1;assign core_event_ready=1;assign '
                                            'core_expression_ready=1;\n'
                                            '    assign vec_event_ready=1;assign vec_ready=1;assign '
                                            'vec_busy=0;\n'
                                            '    assign synth_valid_o=rendered;assign synth_o=0;assign '
                                            'vec_valid=rendered;\n',
                                            '    assign runtime_quiescent=!rendered;assign '
                                            'runtime_rate_ready=!rendered;assign engine_rate=applied_rate;\n'
                                            '    assign core_sample_ready=1;assign core_event_ready=1;assign '
                                            'core_expression_ready=1;\n'
                                            '    assign core_event_slot_ready=1;assign '
                                            'core_expression_slot_ready=1;\n'
                                            '    assign vec_event_ready=1;assign vec_ready=1;assign '
                                            'vec_busy=0;\n'
                                            '    assign synth_valid_o=rendered;assign synth_o=0;assign '
                                            'vec_valid=rendered;\n'],
                                           ['      '
                                            '.event_note_i(a),.event_off_note_i(core_note),.event_velocity_i(core_velocity),\n'
                                            '      '
                                            '.synth_event_ready_o(core_event_ready),.vector_event_ready_o(vec_event_ready),\n'
                                            '      '
                                            '.expression_valid_i(core_expression_valid),.expression_ready_o(core_expression_ready),\n'
                                            '      '
                                            '.expression_note_i(core_expression_note),.expression_value_i(core_expression_value),\n',
                                            '      '
                                            '.event_note_i(a),.event_off_note_i(core_note),.event_velocity_i(core_velocity),\n'
                                            '      '
                                            '.synth_event_ready_o(core_event_ready),.vector_event_ready_o(vec_event_ready),\n'
                                            '      '
                                            '.synth_event_slot_ready_o(core_event_slot_ready),.expression_slot_ready_o(core_expression_slot_ready),\n'
                                            '      '
                                            '.expression_valid_i(core_expression_valid),.expression_ready_o(core_expression_ready),\n'
                                            '      '
                                            '.expression_note_i(core_expression_note),.expression_value_i(core_expression_value),\n'],
                                           ['      '
                                            '.vector_frequency_error_o(vec_frequency_error),.vector_clip_o(vec_clip));\n'
                                            '  end else begin: legacy_engines\n'
                                            "    assign runtime_quiescent=1'b0;\n"
                                            "    assign runtime_rate_ready=1'b0;\n",
                                            '      '
                                            '.vector_frequency_error_o(vec_frequency_error),.vector_clip_o(vec_clip));\n'
                                            '  end else begin: legacy_engines\n'
                                            '    assign core_event_slot_ready=core_event_ready;\n'
                                            '    assign core_expression_slot_ready=core_expression_ready;\n'
                                            "    assign runtime_quiescent=1'b0;\n"
                                            "    assign runtime_rate_ready=1'b0;\n"],
                                           ['        if(effects_valid && !fx_ready) '
                                            'deadline_miss_o<=deadline_miss_o+1;\n'
                                            '      end\n'
                                            '      if(releasing && dispatch && (!deferred_current || '
                                            '(scope_enable ? vec_dispatch_ready : core_event_ready))) begin\n'
                                            '        deferred[release_index]<=0;\n'
                                            '        if(release_index==127) begin '
                                            'releasing<=0;deferred_current<=0;end\n',
                                            '        if(effects_valid && !fx_ready) '
                                            'deadline_miss_o<=deadline_miss_o+1;\n'
                                            '      end\n'
                                            '      if(releasing && dispatch && (!deferred_current || '
                                            '(scope_enable ? vec_dispatch_ready : '
                                            'core_event_dispatch_ready))) begin\n'
                                            '        deferred[release_index]<=0;\n'
                                            '        if(release_index==127) begin '
                                            'releasing<=0;deferred_current<=0;end\n']],
 'rtl/audio/workstation_runtime_render_engines.sv': [['    input logic [6:0] event_note_i, event_off_note_i, '
                                                      'event_velocity_i,\n'
                                                      '    output wire synth_event_ready_o, '
                                                      'vector_event_ready_o,\n'
                                                      '    input logic expression_valid_i,\n'
                                                      '    input logic [6:0] expression_note_i, '
                                                      'expression_value_i,\n',
                                                      '    input logic [6:0] event_note_i, event_off_note_i, '
                                                      'event_velocity_i,\n'
                                                      '    output wire synth_event_ready_o, '
                                                      'vector_event_ready_o,\n'
                                                      '    output wire synth_event_slot_ready_o, '
                                                      'expression_slot_ready_o,\n'
                                                      '    input logic expression_valid_i,\n'
                                                      '    input logic [6:0] expression_note_i, '
                                                      'expression_value_i,\n'],
                                                     ['        .event_valid_i(event_valid_i && '
                                                      '!scope_enable_i),\n'
                                                      '        .event_ready_o(synth_event_ready_o), '
                                                      '.event_note_on_i,\n'
                                                      '        .event_profile_i, '
                                                      '.event_midi_note_i(event_note_i),\n'
                                                      '        .event_off_note_i, .event_velocity_i,\n',
                                                      '        .event_valid_i(event_valid_i && '
                                                      '!scope_enable_i),\n'
                                                      '        .event_ready_o(synth_event_ready_o), '
                                                      '.event_note_on_i,\n'
                                                      '        '
                                                      '.event_slot_ready_o(synth_event_slot_ready_o), '
                                                      '.expression_slot_ready_o,\n'
                                                      '        .event_profile_i, '
                                                      '.event_midi_note_i(event_note_i),\n'
                                                      '        .event_off_note_i, .event_velocity_i,\n']],
 'rtl/audio/workstation_runtime_oscillator_engine.sv': [['    input  logic               event_valid_i,\n'
                                                         '    output logic               event_ready_o,\n'
                                                         '    input  logic               event_note_on_i,\n'
                                                         '    input  logic               '
                                                         'expression_valid_i,\n',
                                                         '    input  logic               event_valid_i,\n'
                                                         '    output logic               event_ready_o,\n'
                                                         "    // Stored readiness before the caller's "
                                                         'same-edge mode/event arbitration.\n'
                                                         '    // Only a caller that proves those requests '
                                                         'mutually exclusive may use it.\n'
                                                         '    output wire                '
                                                         'event_slot_ready_o,\n'
                                                         '    output wire                '
                                                         'expression_slot_ready_o,\n'
                                                         '    input  logic               event_note_on_i,\n'
                                                         '    input  logic               '
                                                         'expression_valid_i,\n'],
                                                        ['      load_state == LOAD_IDLE && !mix_busy_o &&\n'
                                                         '      (!PIPELINED_ENVELOPE || !envelope_lane_busy) '
                                                         '&& (!PIPELINED_RATE || quiescent_o);\n'
                                                         '  assign event_ready_o = load_state == LOAD_IDLE '
                                                         '&& !mix_busy_o &&\n'
                                                         '      !mode_set_valid_i && (event_note_on_i ? '
                                                         "allocation_found : 1'b1) &&\n"
                                                         '      (!PIPELINED_ENVELOPE || !envelope_lane_busy) '
                                                         '&& (!PIPELINED_RATE || quiescent_o);\n'
                                                         '  assign sample_ready_o = load_state == LOAD_IDLE '
                                                         '&& !mix_busy_o &&\n'
                                                         '      !envelope_lane_busy &&\n'
                                                         '      !(event_valid_i && event_ready_o) && '
                                                         '!mode_set_valid_i && (!PIPELINED_RATE || '
                                                         'quiescent_o);\n'
                                                         '  assign expression_ready_o = load_state == '
                                                         'LOAD_IDLE && !mix_busy_o &&\n'
                                                         '      !envelope_lane_busy &&\n'
                                                         '      !event_valid_i && !mode_set_valid_i && '
                                                         '(!PIPELINED_RATE || quiescent_o);\n'
                                                         '\n'
                                                         '  midi_step_rom #(\n',
                                                         '      load_state == LOAD_IDLE && !mix_busy_o &&\n'
                                                         '      (!PIPELINED_ENVELOPE || !envelope_lane_busy) '
                                                         '&& (!PIPELINED_RATE || quiescent_o);\n'
                                                         '  assign event_slot_ready_o = load_state == '
                                                         'LOAD_IDLE && !mix_busy_o &&\n'
                                                         "      (event_note_on_i ? allocation_found : 1'b1) "
                                                         '&&\n'
                                                         '      (!PIPELINED_ENVELOPE || !envelope_lane_busy) '
                                                         '&& (!PIPELINED_RATE || quiescent_o);\n'
                                                         '  assign event_ready_o = event_slot_ready_o && '
                                                         '!mode_set_valid_i;\n'
                                                         '  assign sample_ready_o = load_state == LOAD_IDLE '
                                                         '&& !mix_busy_o &&\n'
                                                         '      !envelope_lane_busy &&\n'
                                                         '      !(event_valid_i && event_ready_o) && '
                                                         '!mode_set_valid_i && (!PIPELINED_RATE || '
                                                         'quiescent_o);\n'
                                                         '  assign expression_slot_ready_o = load_state == '
                                                         'LOAD_IDLE && !mix_busy_o &&\n'
                                                         '      !envelope_lane_busy &&\n'
                                                         '      (!PIPELINED_RATE || quiescent_o);\n'
                                                         '  assign expression_ready_o = '
                                                         'expression_slot_ready_o && !event_valid_i && '
                                                         '!mode_set_valid_i;\n'
                                                         '\n'
                                                         '  midi_step_rom #(\n']]}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def restore_parent(relative, source):
    """Reverse the complete reviewed owner change and verify forward roundtrip."""
    relative = str(relative)
    if relative not in HUNKS or sha(source) != CURRENT_SHA256[relative]:
        raise ValueError('Dispatch slot source identity changed: ' + relative)
    current = source.decode()
    for before, after in reversed(HUNKS[relative]):
        if not after or current.count(after) != 1:
            raise ValueError('Dispatch slot reverse anchor drift: ' + relative)
        current = current.replace(after, before)
    parent = current.encode()
    if sha(parent) != ORIGINAL_SHA256[relative]:
        raise ValueError('Dispatch slot parent identity changed: ' + relative)
    for before, after in HUNKS[relative]:
        if not before or current.count(before) != 1:
            raise ValueError('Dispatch slot forward anchor drift: ' + relative)
        current = current.replace(before, after)
    if current.encode() != source:
        raise ValueError('Dispatch slot round trip changed bytes: ' + relative)
    return parent


def normalize_source(relative, source):
    relative = str(relative)
    # Historical complete dispatch parents predate the later glide layer.
    # Admit only their unchanged original whole-file identities.
    if relative in ORIGINAL_SHA256 and sha(source) == ORIGINAL_SHA256[relative]:
        return source
    try:
        from tools.workstation_oscillator_availability import restore as restore_available
    except ModuleNotFoundError:
        from workstation_oscillator_availability import restore as restore_available
    source=restore_available(relative,source)
    try:
        from tools.workstation_committed_glide import normalize as normalize_glide
    except ModuleNotFoundError:
        from workstation_committed_glide import normalize as normalize_glide
    source = normalize_glide(relative, source)
    if relative in ORIGINAL_SHA256 and sha(source) == ORIGINAL_SHA256[relative]:
        return source
    return restore_parent(relative, source)


def source_evidence(relative, source):
    relative = str(relative)
    parent = normalize_source(relative, source)
    return dict(source=relative, current_source_sha256=sha(source),
                parent_source_sha256=sha(parent),
                stage='parent' if source == parent else 'stored_slots',
                exact_whole_source_inverse_and_roundtrip=True,
                added_clock_latency=0,
                physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    root = Path(root)
    owners = {n: source_evidence(n, (root / n).read_bytes()) for n in HUNKS}
    stages = {entry['stage'] for entry in owners.values()}
    if len(stages) != 1:
        raise ValueError('Dispatch slot owners use mixed source stages')
    return dict(policy=POLICY, stage=next(iter(stages)), owners=owners,
                all_owner_sources_identity_bound=True, added_clock_latency=0,
                physical_timing_verified=False, hardware_acceptance_inherited=False)
