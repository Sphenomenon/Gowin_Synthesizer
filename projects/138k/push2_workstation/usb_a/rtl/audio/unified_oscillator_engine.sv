`timescale 1ns/1ps

`ifndef UNIFIED_MIDI_STEP_MEM_FILE
`define UNIFIED_MIDI_STEP_MEM_FILE \
    "sim/matlab/output/stage13_note_voice/stage13_midi_step.mem"
`endif
`ifndef UNIFIED_SINE_MEM_FILE
`define UNIFIED_SINE_MEM_FILE \
    "sim/matlab/output/stage3_sine2048x24.mem"
`endif
`ifndef UNIFIED_RATIO_MEM_FILE
`define UNIFIED_RATIO_MEM_FILE \
    "sim/matlab/output/stage13_note_voice/stage13_ratio_q18.mem"
`endif
`ifndef UNIFIED_GAIN_MEM_FILE
`define UNIFIED_GAIN_MEM_FILE \
    "sim/matlab/output/stage15_unified_modes/stage15_mode_gain_q15.mem"
`endif
`ifndef UNIFIED_ADSR_MEM_FILE
`define UNIFIED_ADSR_MEM_FILE \
    "sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem"
`endif

module unified_oscillator_engine #(
    parameter bit EXPRESSION_ENABLE = 1'b0,
    parameter int SAMPLE_RATE_HZ = 192000,
    parameter bit SEPARATE_OFF_NOTE = 1'b0
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               mode_set_valid_i,
    output logic               mode_set_ready_o,
    input  logic        [1:0]  mode_i,
    output logic        [1:0]  current_mode_o,
    input  logic               panic_i,
    input  logic               event_valid_i,
    output logic               event_ready_o,
    input  logic               event_note_on_i,
    input  logic               expression_valid_i,
    output logic               expression_ready_o,
    input  logic        [6:0]  expression_note_i,
    input  logic        [6:0]  expression_value_i,
    input  logic        [2:0]  event_profile_i,
    input  logic        [6:0]  event_midi_note_i,
    input  logic        [6:0]  event_velocity_i,
    input  logic        [21:0] pitch_ratio_q20_i,
    input  logic               sample_ce_i,
    output logic               sample_ready_o,
    output logic               sample_valid_o,
    output logic signed [31:0] sample_o,
    output logic        [31:0] allocated_mask_o,
    output logic        [31:0] active_mask_o,
    output logic        [5:0]  active_voice_count_o,
    output logic               load_busy_o,
    output logic               mix_busy_o,
    output logic        [7:0]  issued_slot_count_o,
    input  logic        [6:0]  event_off_note_i
);
  localparam logic [2:0] LOAD_IDLE = 3'd0;
  localparam logic [2:0] LOAD_WAIT_MIDI = 3'd1;
  localparam logic [2:0] LOAD_PARTIALS = 3'd2;
  localparam logic [2:0] LOAD_LAUNCH = 3'd3;
  localparam logic [2:0] ENVELOPE_IDLE = 3'd0;
  localparam logic [2:0] ENVELOPE_ATTACK = 3'd1;
  localparam logic [2:0] ENVELOPE_DECAY = 3'd2;
  localparam logic [2:0] ENVELOPE_SUSTAIN = 3'd3;
  localparam logic [2:0] ENVELOPE_RELEASE = 3'd4;
  localparam logic [23:0] MAXIMUM_LEVEL_Q24 = 24'hffffc0;

  logic [2:0] load_state;
  logic [4:0] load_voice_index;
  logic [2:0] load_profile;
  logic [1:0] load_mode;
  logic [15:0] load_velocity_q15;
  logic [5:0] load_partial_count;
  logic [4:0] load_last_partial_index;
  logic [31:0] voice_started_mask;
  logic [6:0] assigned_midi_note [0:31];
  logic [23:0] attack_step_q24 [0:31];
  logic [23:0] decay_step_q24 [0:31];
  logic [23:0] sustain_level_q24 [0:31];
  logic [23:0] release_step_q24 [0:31];
  logic [17:0] envelope_level_q18 [0:31];
  logic [17:0] sample_envelope_q18 [0:31];
  logic [2:0] envelope_state [0:31];
  logic [23:0] envelope_level_q24 [0:31];
  // Per-voice pressure gain.  128 represents unity; 0 is silence.
  logic [7:0] expression_gain_q8 [0:31];
  logic [23:0] expression_scaled_gain;
  logic envelope_update_active;
  logic [4:0] envelope_update_index;
  logic envelope_update_valid;
  logic [4:0] envelope_update_write_index;
  logic [2:0] envelope_update_state;
  logic [23:0] envelope_update_level_q24;
  logic [23:0] envelope_update_attack_q24;
  logic [23:0] envelope_update_decay_q24;
  logic [23:0] envelope_update_sustain_q24;
  logic [23:0] envelope_update_release_q24;
  logic [24:0] envelope_update_attack_sum;
  logic [23:0] envelope_next_level_q24;
  logic [17:0] envelope_next_level_q18;
  logic [2:0] envelope_next_state;

  (* syn_ramstyle = "block_ram", ram_style = "block" *)
  logic [79:0] slot_mem [0:1023];
  logic slot_read_valid;
  logic slot_read_last;
  logic [9:0] slot_read_index;
  logic [79:0] slot_read_data;
  logic slot_write_enable;
  logic [9:0] slot_write_address;
  logic [79:0] slot_write_data;
  logic [31:0] updated_slot_phase;
  logic [21:0] sample_pitch_q20;
  logic [53:0] pitch_product;
  logic [33:0] pitch_step_rounded;
  logic pitch_write_valid;
  logic [9:0] pitch_write_index;
  logic [79:0] pitch_write_data;
  logic [31:0] scaled_midi_phase_step;
  localparam int RATE_SCALE = 192000 / SAMPLE_RATE_HZ;

  function automatic logic [23:0] scale_envelope_step(input logic [23:0] value);
    logic [31:0] scaled;
    begin
      scaled = value * RATE_SCALE;
      scale_envelope_step = scaled > 32'hffffc0 ? 24'hffffc0 : scaled[23:0];
    end
  endfunction

  logic allocation_found;
  logic [4:0] allocation_index;
  logic release_found;
  logic [4:0] release_index;
  logic expression_found;
  logic [4:0] expression_index;
  wire [6:0] off_note=SEPARATE_OFF_NOTE ? event_off_note_i : event_midi_note_i;
  wire [31:0] release_matches,release_select,expression_matches,expression_select;
  for(genvar ev=0;ev<32;ev=ev+1) begin: g_direct_event_select
    assign release_matches[ev]=ev<=maximum_voice_index && allocated_mask_o[ev] &&
        envelope_state[ev]!=ENVELOPE_RELEASE && envelope_state[ev]!=ENVELOPE_IDLE &&
        assigned_midi_note[ev]==off_note;
    assign expression_matches[ev]=allocated_mask_o[ev] &&
        envelope_state[ev]!=ENVELOPE_RELEASE && envelope_state[ev]!=ENVELOPE_IDLE &&
        assigned_midi_note[ev]==expression_note_i;
    if(ev==0) begin
      assign release_select[ev]=release_matches[ev];
      assign expression_select[ev]=expression_matches[ev];
    end else begin
      assign release_select[ev]=release_matches[ev] && !(|release_matches[ev-1:0]);
      assign expression_select[ev]=expression_matches[ev] && !(|expression_matches[ev-1:0]);
    end
  end
  logic [4:0] maximum_voice_index;
  logic [5:0] current_partial_count;
  logic accepted_event;
  logic accepted_expression;
  logic accepted_sample;

  logic midi_read;
  logic midi_valid;
  logic [31:0] midi_phase_step;
  logic partial_start;
  logic partial_ready;
  logic partial_busy;
  logic partial_valid;
  logic partial_done;
  logic [4:0] partial_index;
  logic [31:0] partial_step;
  logic partial_enable;
  logic gain_valid;
  logic [15:0] gain_q15;
  logic [4:0] partial_index_delay;
  logic [31:0] partial_step_delay;
  logic partial_enable_delay;
  logic [9:0] load_slot_address;
  logic [23:0] rom_attack_step_q24;
  logic [23:0] rom_decay_step_q24;
  logic [23:0] rom_sustain_level_q24;
  logic [23:0] rom_release_step_q24;
  logic [31:0] velocity_gain_product;
  logic [31:0] velocity_gain_biased;
  logic [15:0] velocity_gain_rounded;
  logic [15:0] scaled_gain_q15;

  logic issue_active;
  logic [9:0] issue_index;
  logic [9:0] last_slot_index;
  logic [4:0] issued_voice_index;
  logic sine_valid_i;
  logic [31:0] sine_phase_i;
  logic sine_valid_o;
  logic signed [23:0] sine_sample_o;
  logic [15:0] gain_pipe [0:4];
  logic [17:0] envelope_pipe [0:4];
  logic last_pipe [0:4];
  logic signed [16:0] gain_signed;
  logic signed [18:0] envelope_signed;
  logic gain_product_valid;
  logic gain_product_last;
  logic signed [40:0] gain_product;
  logic [17:0] gain_product_envelope;
  logic envelope_product_valid;
  logic envelope_product_last;
  logic signed [59:0] envelope_product;
  logic signed [63:0] product_extended;
  logic signed [63:0] accumulator;
  logic signed [63:0] accumulated_next;
  logic signed [63:0] final_accumulator;
  logic finalize_valid;
  // Keep the exact P30 3/2 gain and rounding, with separate registered
  // magnitude, scaling and quantization stages. No sample-rate change.
  unified_mix_quantizer quantizer(
      .clk_i(clk_i),.rst_ni(rst_ni),.panic_i(panic_i),
      .valid_i(finalize_valid),.mix_i(final_accumulator),.mode_i(current_mode_o),
      .valid_o(sample_valid_o),.sample_o(sample_o));

  integer voice_index;
  integer pipeline_index;

  function automatic logic [15:0] midi_velocity_to_q15(
      input logic [6:0] velocity);
    logic [15:0] scaled;
    begin
      if (velocity == 7'd127) begin
        midi_velocity_to_q15 = 16'h7fff;
      end else begin
        // round(velocity * 32767 / 127), written without a divider.
        scaled = ({9'd0, velocity} << 8) + ({9'd0, velocity} << 1);
        if (velocity >= 7'd64) begin
          scaled = scaled + 16'd1;
        end
        midi_velocity_to_q15 = scaled;
      end
    end
  endfunction

  assign current_partial_count = current_mode_o == 2'd0 ? 6'd1 :
      (current_mode_o == 2'd1 ? 6'd4 : 6'd32);
  assign maximum_voice_index = 5'd31;
  assign last_slot_index = current_mode_o == 2'd0 ? 10'd31 :
      (current_mode_o == 2'd1 ? 10'd127 : 10'd1023);
  assign load_busy_o = load_state != LOAD_IDLE;
  assign accepted_event = event_valid_i && event_ready_o;
  assign accepted_expression = expression_valid_i && expression_ready_o;
  assign accepted_sample = sample_ce_i && sample_ready_o;
  assign midi_read = accepted_event && event_note_on_i;
  assign partial_start = load_state == LOAD_WAIT_MIDI && midi_valid && partial_ready;
  assign sine_valid_i = slot_read_valid;
  // Unallocated slot RAM is intentionally unreset for BRAM inference. Mask
  // inactive slots before lookup: an unknown RAM value times zero is still X.
  assign sine_phase_i = sample_envelope_q18[issued_voice_index] == 0
      ? 32'd0 : slot_read_data[79:48];
  assign gain_signed = $signed({1'b0, gain_pipe[4]});
  assign envelope_signed = $signed({1'b0, gain_product_envelope});
  assign product_extended = {{4{envelope_product[59]}}, envelope_product};
  assign accumulated_next = accumulator + product_extended;
  assign envelope_update_attack_sum =
      {1'b0, envelope_update_level_q24} +
      {1'b0, envelope_update_attack_q24};
  assign updated_slot_phase = slot_read_data[79:48] + slot_read_data[47:16];
  assign scaled_midi_phase_step = midi_phase_step * RATE_SCALE;
  assign pitch_step_rounded = pitch_product[53:20] + {33'd0,pitch_product[19]};
  assign velocity_gain_product = gain_q15 * load_velocity_q15;
  assign velocity_gain_biased = velocity_gain_product + 32'd16384;
  assign velocity_gain_rounded = velocity_gain_biased[30:15];
  assign scaled_gain_q15 = load_velocity_q15 == 16'h7fff
      ? gain_q15 : velocity_gain_rounded;
  assign expression_scaled_gain =
      {8'd0, slot_read_data[15:0]} *
      {16'd0, expression_gain_q8[issued_voice_index]};

  // One ADSR arithmetic lane services all voices.  Array selection is
  // registered before the arithmetic so the vendor mapper does not build a
  // long read-mux/arithmetic/write-demux path through all 32 voices.
  always @* begin
    envelope_next_level_q24 = envelope_update_level_q24;
    envelope_next_state = envelope_update_state;
    case (envelope_update_state)
      ENVELOPE_ATTACK: begin
        if (envelope_update_attack_q24 == 0 ||
            envelope_update_attack_sum >= {1'b0, MAXIMUM_LEVEL_Q24}) begin
          envelope_next_level_q24 = MAXIMUM_LEVEL_Q24;
          envelope_next_state = ENVELOPE_DECAY;
        end else begin
          envelope_next_level_q24 = envelope_update_attack_sum[23:0];
        end
      end
      ENVELOPE_DECAY: begin
        if (envelope_update_decay_q24 == 0 ||
            envelope_update_level_q24 <= envelope_update_sustain_q24 ||
            envelope_update_level_q24 - envelope_update_sustain_q24 <=
                envelope_update_decay_q24) begin
          envelope_next_level_q24 = envelope_update_sustain_q24;
          envelope_next_state = ENVELOPE_SUSTAIN;
        end else begin
          envelope_next_level_q24 = envelope_update_level_q24 -
              envelope_update_decay_q24;
        end
      end
      ENVELOPE_SUSTAIN: begin
        envelope_next_level_q24 = envelope_update_sustain_q24;
      end
      ENVELOPE_RELEASE: begin
        if (envelope_update_release_q24 == 0 ||
            envelope_update_level_q24 <= envelope_update_release_q24) begin
          envelope_next_level_q24 = '0;
          envelope_next_state = ENVELOPE_IDLE;
        end else begin
          envelope_next_level_q24 = envelope_update_level_q24 -
              envelope_update_release_q24;
        end
      end
      default: begin
        envelope_next_level_q24 = '0;
        envelope_next_state = ENVELOPE_IDLE;
      end
    endcase
    envelope_next_level_q18 = envelope_next_level_q24[23:6];
  end

  always @* begin
    slot_write_enable = 1'b0;
    slot_write_address = '0;
    slot_write_data = '0;
    if (!EXPRESSION_ENABLE && slot_read_valid) begin
      slot_write_enable = 1'b1;
      slot_write_address = slot_read_index;
      slot_write_data = {updated_slot_phase, slot_read_data[47:0]};
    end
    if (EXPRESSION_ENABLE && pitch_write_valid) begin
      slot_write_enable = 1'b1;
      slot_write_address = pitch_write_index;
      slot_write_data = {
          pitch_write_data[79:48] + pitch_step_rounded[31:0],
          pitch_write_data[47:0]};
    end
    if (load_state == LOAD_PARTIALS && gain_valid) begin
      slot_write_enable = 1'b1;
      slot_write_address = load_slot_address;
      slot_write_data = {32'd0,
          partial_enable_delay ? partial_step_delay : 32'd0,
          partial_enable_delay ? scaled_gain_q15 : 16'd0};
    end
  end

  always @* begin
    case (current_mode_o)
      2'd0: issued_voice_index = slot_read_index[4:0];
      2'd1: issued_voice_index = slot_read_index[6:2];
      default: issued_voice_index = slot_read_index[9:5];
    endcase
  end

  always @* begin
    case (load_mode)
      2'd0: load_slot_address = {5'b0, load_voice_index};
      2'd1: load_slot_address = {3'b0, load_voice_index, 2'b0} +
          {5'b0, partial_index_delay};
      default: load_slot_address = {load_voice_index, 5'b0} +
          {5'b0, partial_index_delay};
    endcase
  end

  always @* begin
    allocation_found = 1'b0;
    allocation_index = '0;
    release_found = 1'b0;
    release_index = '0;
    expression_found = 1'b0;
    expression_index = '0;

    for (int index = 0; index < 32; index = index + 1) begin
      if (!allocation_found && index <= maximum_voice_index &&
          !allocated_mask_o[index]) begin
        allocation_found = 1'b1;
        allocation_index = index[4:0];
      end
      if (!release_found && index <= maximum_voice_index &&
          allocated_mask_o[index] &&
          // Re-triggered equal pitches can overlap a releasing voice. Each
          // Note Off consumes one still-held voice, not the old release tail.
          envelope_state[index] != ENVELOPE_RELEASE &&
          envelope_state[index] != ENVELOPE_IDLE &&
          assigned_midi_note[index] == off_note) begin
        release_found = 1'b1;
        release_index = index[4:0];
      end
      if (!expression_found && allocated_mask_o[index] &&
          envelope_state[index] != ENVELOPE_RELEASE &&
          envelope_state[index] != ENVELOPE_IDLE &&
          assigned_midi_note[index] == expression_note_i) begin
        expression_found = 1'b1;
        expression_index = index[4:0];
      end
    end

  end

  always @* begin
    active_voice_count_o = '0;
    active_mask_o = '0;
    for (int index = 0; index < 32; index = index + 1) begin
      if (allocated_mask_o[index] &&
          envelope_state[index] != ENVELOPE_IDLE) begin
        active_mask_o[index] = 1'b1;
        active_voice_count_o = active_voice_count_o + 6'd1;
      end
    end
  end

  assign mode_set_ready_o = allocated_mask_o == 32'd0 &&
      load_state == LOAD_IDLE && !mix_busy_o;
  assign event_ready_o = load_state == LOAD_IDLE && !mix_busy_o &&
      !mode_set_valid_i && (event_note_on_i ? allocation_found : 1'b1);
  assign sample_ready_o = load_state == LOAD_IDLE && !mix_busy_o &&
      !envelope_update_active && !envelope_update_valid &&
      !(event_valid_i && event_ready_o) && !mode_set_valid_i;
  assign expression_ready_o = load_state == LOAD_IDLE && !mix_busy_o &&
      !envelope_update_active && !envelope_update_valid &&
      !event_valid_i && !mode_set_valid_i;

  midi_step_rom #(
      .MEM_FILE(`UNIFIED_MIDI_STEP_MEM_FILE)
  ) u_midi_step_rom (
      .clk_i,
      .rst_ni,
      .read_i(midi_read),
      .midi_note_i(event_midi_note_i),
      .valid_o(midi_valid),
      .phase_step_o(midi_phase_step)
  );

  partial_step_generator_variable #(
      .RATIO_MEM_FILE(`UNIFIED_RATIO_MEM_FILE)
  ) u_partial_step_generator_variable (
      .clk_i,
      .rst_ni,
      .start_i(partial_start),
      .profile_i(load_profile),
      .base_step_i(scaled_midi_phase_step),
      .partial_count_i(load_partial_count),
      .ready_o(partial_ready),
      .busy_o(partial_busy),
      .valid_o(partial_valid),
      .done_o(partial_done),
      .partial_index_o(partial_index),
      .partial_step_o(partial_step),
      .partial_enable_o(partial_enable)
  );

  mode_timbre_rom #(
      .GAIN_MEM_FILE(`UNIFIED_GAIN_MEM_FILE),
      .ADSR_MEM_FILE(`UNIFIED_ADSR_MEM_FILE)
  ) u_mode_timbre_rom (
      .clk_i,
      .rst_ni,
      .gain_read_i(partial_valid),
      .mode_i(load_mode),
      .profile_i(load_profile),
      .partial_index_i(partial_index),
      .gain_valid_o(gain_valid),
      .gain_q15_o(gain_q15),
      .attack_step_q24_o(rom_attack_step_q24),
      .decay_step_q24_o(rom_decay_step_q24),
      .sustain_level_q24_o(rom_sustain_level_q24),
      .release_step_q24_o(rom_release_step_q24)
  );

  sine_interp #(
      .MEM_FILE(`UNIFIED_SINE_MEM_FILE)
  ) u_sine_interp (
      .clk_i,
      .rst_ni,
      .valid_i(sine_valid_i),
      .phase_i(sine_phase_i),
      .valid_o(sine_valid_o),
      .sample_o(sine_sample_o)
  );

  // Keep the storage write process free of reset logic.  This coding style is
  // recognized as block RAM by both GowinSynthesis and Vivado.
  always_ff @(posedge clk_i) begin
    if (slot_write_enable) begin
      slot_mem[slot_write_address] <= slot_write_data;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      sample_pitch_q20 <= 22'd1048576;
      pitch_product <= '0;
      pitch_write_valid <= 1'b0;
      pitch_write_index <= '0;
      pitch_write_data <= '0;
    end else if (panic_i) begin
      pitch_write_valid <= 1'b0;
      pitch_write_index <= '0;
      pitch_write_data <= '0;
    end else begin
      if (accepted_sample) sample_pitch_q20 <= pitch_ratio_q20_i;
      pitch_write_valid <= slot_read_valid;
      if (slot_read_valid) begin
        pitch_product <= slot_read_data[47:16] * sample_pitch_q20;
        pitch_write_index <= slot_read_index;
        pitch_write_data <= slot_read_data;
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      slot_read_valid <= 1'b0;
      slot_read_last <= 1'b0;
      slot_read_index <= '0;
      slot_read_data <= '0;
    end else if (panic_i) begin
      slot_read_valid <= 1'b0;
      slot_read_last <= 1'b0;
      slot_read_index <= '0;
      slot_read_data <= '0;
    end else begin
      slot_read_valid <= issue_active;
      if (issue_active) begin
        slot_read_index <= issue_index;
        slot_read_last <= issue_index == last_slot_index;
        slot_read_data <= slot_mem[issue_index];
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      current_mode_o <= 2'd2;
      load_state <= LOAD_IDLE;
      load_voice_index <= '0;
      load_profile <= '0;
      load_mode <= '0;
      load_velocity_q15 <= '0;
      load_partial_count <= 6'd1;
      load_last_partial_index <= '0;
      allocated_mask_o <= '0;
      voice_started_mask <= '0;
      envelope_update_active <= 1'b0;
      envelope_update_index <= '0;
      envelope_update_valid <= 1'b0;
      envelope_update_write_index <= '0;
      envelope_update_state <= ENVELOPE_IDLE;
      envelope_update_level_q24 <= '0;
      envelope_update_attack_q24 <= '0;
      envelope_update_decay_q24 <= '0;
      envelope_update_sustain_q24 <= '0;
      envelope_update_release_q24 <= '0;
      partial_index_delay <= '0;
      partial_step_delay <= '0;
      partial_enable_delay <= 1'b0;
      issue_active <= 1'b0;
      issue_index <= '0;
      issued_slot_count_o <= '0;
      gain_product_valid <= 1'b0;
      gain_product_last <= 1'b0;
      gain_product <= '0;
      gain_product_envelope <= '0;
      envelope_product_valid <= 1'b0;
      envelope_product_last <= 1'b0;
      envelope_product <= '0;
      accumulator <= '0;
      final_accumulator <= '0;
      finalize_valid <= 1'b0;
      mix_busy_o <= 1'b0;
      for (voice_index = 0; voice_index < 32; voice_index = voice_index + 1) begin
        assigned_midi_note[voice_index] <= '0;
        attack_step_q24[voice_index] <= '0;
        decay_step_q24[voice_index] <= '0;
        sustain_level_q24[voice_index] <= '0;
        release_step_q24[voice_index] <= '0;
        envelope_level_q24[voice_index] <= '0;
        envelope_level_q18[voice_index] <= '0;
        envelope_state[voice_index] <= ENVELOPE_IDLE;
        sample_envelope_q18[voice_index] <= '0;
        expression_gain_q8[voice_index] <= 8'd128;
      end
      for (pipeline_index = 0; pipeline_index < 5;
          pipeline_index = pipeline_index + 1) begin
        gain_pipe[pipeline_index] <= '0;
        envelope_pipe[pipeline_index] <= '0;
        last_pipe[pipeline_index] <= 1'b0;
      end
    end else begin
      finalize_valid <= 1'b0;
      envelope_update_valid <= envelope_update_active;

      if (envelope_update_active) begin
        envelope_update_write_index <= envelope_update_index;
        envelope_update_state <= envelope_state[envelope_update_index];
        envelope_update_level_q24 <=
            envelope_level_q24[envelope_update_index];
        envelope_update_attack_q24 <= attack_step_q24[envelope_update_index];
        envelope_update_decay_q24 <= decay_step_q24[envelope_update_index];
        envelope_update_sustain_q24 <=
            sustain_level_q24[envelope_update_index];
        envelope_update_release_q24 <=
            release_step_q24[envelope_update_index];
        if (envelope_update_index == 5'd31) begin
          envelope_update_active <= 1'b0;
        end else begin
          envelope_update_index <= envelope_update_index + 5'd1;
        end
      end

      if (envelope_update_valid) begin
        envelope_level_q24[envelope_update_write_index] <=
            envelope_next_level_q24;
        envelope_level_q18[envelope_update_write_index] <=
            envelope_next_level_q18;
        envelope_state[envelope_update_write_index] <= envelope_next_state;
      end

      if (mode_set_valid_i && mode_set_ready_o) begin
        current_mode_o <= mode_i <= 2'd2 ? mode_i : 2'd2;
      end

      for (voice_index = 0; voice_index < 32; voice_index = voice_index + 1) begin
        if (allocated_mask_o[voice_index] && voice_started_mask[voice_index] &&
            envelope_state[voice_index] == ENVELOPE_IDLE) begin
          allocated_mask_o[voice_index] <= 1'b0;
          voice_started_mask[voice_index] <= 1'b0;
        end
      end

      for(integer ev=0;ev<32;ev=ev+1)
        if(accepted_event && !event_note_on_i && release_select[ev])
          envelope_state[ev]<=ENVELOPE_RELEASE;

      if (accepted_event && event_note_on_i) begin
        allocated_mask_o[allocation_index] <= 1'b1;
        assigned_midi_note[allocation_index] <= event_midi_note_i;
        load_voice_index <= allocation_index;
        load_profile <= event_profile_i;
        load_mode <= current_mode_o;
        load_velocity_q15 <= midi_velocity_to_q15(event_velocity_i);
        load_partial_count <= current_partial_count;
        load_last_partial_index <= current_partial_count[4:0] - 5'd1;
        load_state <= LOAD_WAIT_MIDI;
        expression_gain_q8[allocation_index] <= 8'd128;
      end else if (accepted_expression) begin
        for(integer ev=0;ev<32;ev=ev+1)
          if(expression_select[ev]) expression_gain_q8[ev]<=
              expression_value_i == 7'd127 ? 8'd128 : {1'b0, expression_value_i};
      end else begin
        case (load_state)
          LOAD_WAIT_MIDI: begin
            if (midi_valid && partial_ready) begin
              attack_step_q24[load_voice_index] <= scale_envelope_step(rom_attack_step_q24);
              decay_step_q24[load_voice_index] <= scale_envelope_step(rom_decay_step_q24);
              sustain_level_q24[load_voice_index] <= rom_sustain_level_q24;
              release_step_q24[load_voice_index] <= scale_envelope_step(rom_release_step_q24);
              load_state <= LOAD_PARTIALS;
            end
          end
          LOAD_PARTIALS: begin
            if (gain_valid) begin
              if (partial_index_delay == load_last_partial_index) begin
                load_state <= LOAD_LAUNCH;
              end
            end
          end
          LOAD_LAUNCH: begin
            voice_started_mask[load_voice_index] <= 1'b1;
            envelope_level_q24[load_voice_index] <= '0;
            envelope_level_q18[load_voice_index] <= '0;
            envelope_state[load_voice_index] <= ENVELOPE_ATTACK;
            load_state <= LOAD_IDLE;
          end
          default: load_state <= LOAD_IDLE;
        endcase
      end

      if (partial_valid) begin
        partial_index_delay <= partial_index;
        partial_step_delay <= partial_step;
        partial_enable_delay <= partial_enable;
      end

      gain_pipe[0] <= sample_envelope_q18[issued_voice_index] == 0
          ? 16'd0 : expression_scaled_gain[22:7];
      envelope_pipe[0] <= sample_envelope_q18[issued_voice_index];
      last_pipe[0] <= slot_read_valid && slot_read_last;
      for (pipeline_index = 1; pipeline_index < 5;
          pipeline_index = pipeline_index + 1) begin
        gain_pipe[pipeline_index] <= gain_pipe[pipeline_index-1];
        envelope_pipe[pipeline_index] <= envelope_pipe[pipeline_index-1];
        last_pipe[pipeline_index] <= last_pipe[pipeline_index-1];
      end
      if (EXPRESSION_ENABLE && pitch_step_rounded >= 34'd1932735283)
        gain_pipe[1] <= 16'd0;

      gain_product_valid <= sine_valid_o;
      if (sine_valid_o) begin
        gain_product <= sine_sample_o * gain_signed;
        gain_product_envelope <= envelope_pipe[4];
        gain_product_last <= last_pipe[4];
      end

      envelope_product_valid <= gain_product_valid;
      if (gain_product_valid) begin
        envelope_product <= gain_product * envelope_signed;
        envelope_product_last <= gain_product_last;
      end

      if (envelope_product_valid) begin
        if (envelope_product_last) begin
          final_accumulator <= accumulated_next;
          finalize_valid <= 1'b1;
          accumulator <= '0;
          mix_busy_o <= 1'b0;
        end else begin
          accumulator <= accumulated_next;
        end
      end

      if (accepted_sample) begin
        issue_active <= 1'b1;
        issue_index <= '0;
        issued_slot_count_o <= '0;
        accumulator <= '0;
        mix_busy_o <= 1'b1;
        envelope_update_active <= 1'b1;
        envelope_update_index <= '0;
        for (voice_index = 0; voice_index < 32; voice_index = voice_index + 1) begin
          sample_envelope_q18[voice_index] <= envelope_level_q18[voice_index];
        end
      end

      if (issue_active) begin
        issued_slot_count_o <= issued_slot_count_o + 8'd1;
        if (issue_index == last_slot_index) begin
          issue_active <= 1'b0;
        end else begin
          issue_index <= issue_index + 10'd1;
        end
      end

      // CC120 PANIC is a hard state boundary.  Clearing the allocation mask
      // makes the old per-voice envelope arrays unreachable; a later voice
      // load initializes its selected entry before samples can be accepted.
      // Keep those arrays out of this branch so PANIC does not add a reset
      // mux to every stored bit or disturb the slot-RAM inference.
      if (panic_i) begin
        load_state <= LOAD_IDLE;
        allocated_mask_o <= '0;
        voice_started_mask <= '0;
        envelope_update_active <= 1'b0;
        envelope_update_valid <= 1'b0;
        issue_active <= 1'b0;
        issued_slot_count_o <= '0;
        gain_product_valid <= 1'b0;
        gain_product_last <= 1'b0;
        envelope_product_valid <= 1'b0;
        envelope_product_last <= 1'b0;
        accumulator <= '0;
        final_accumulator <= '0;
        finalize_valid <= 1'b0;
        mix_busy_o <= 1'b0;
      end
    end
  end
endmodule

// Kept beside its sole production consumer so all existing engine file lists
// include the quantizer. The independent testbench also exercises this module
// directly with full-range 64-bit inputs, rounding boundaries and PANIC.
module unified_mix_quantizer(
    input logic clk_i,rst_ni,panic_i,valid_i,
    input logic signed [63:0] mix_i,
    input logic [1:0] mode_i,
    output logic valid_o,
    output logic signed [31:0] sample_o
);
  logic magnitude_low_valid,magnitude_valid,scale_low_valid,scaled_valid,rounded_valid;
  logic low_negative,magnitude_negative,scale_low_negative,scaled_negative,rounded_negative;
  logic low_mode_c,magnitude_mode_c,scale_low_mode_c,scaled_mode_c;
  logic [31:0] magnitude_low,magnitude_high_base;
  logic magnitude_carry;
  logic [63:0] magnitude;
  logic [33:0] scale_low_sum;
  logic [32:0] scale_high_sum;
  logic [65:0] scaled;
  logic [38:0] rounded;
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      magnitude_low_valid<=0;magnitude_valid<=0;scale_low_valid<=0;scaled_valid<=0;rounded_valid<=0;valid_o<=0;
      low_negative<=0;magnitude_negative<=0;scale_low_negative<=0;scaled_negative<=0;rounded_negative<=0;
      low_mode_c<=0;magnitude_mode_c<=0;scale_low_mode_c<=0;scaled_mode_c<=0;
      magnitude_low<=0;magnitude_high_base<=0;magnitude_carry<=0;
      magnitude<=0;scale_low_sum<=0;scale_high_sum<=0;scaled<=0;rounded<=0;sample_o<=0;
    end else if(panic_i) begin
      magnitude_low_valid<=0;magnitude_valid<=0;scale_low_valid<=0;scaled_valid<=0;rounded_valid<=0;valid_o<=0;
      low_negative<=0;magnitude_negative<=0;scale_low_negative<=0;scaled_negative<=0;rounded_negative<=0;
      low_mode_c<=0;magnitude_mode_c<=0;scale_low_mode_c<=0;scaled_mode_c<=0;
      magnitude_low<=0;magnitude_high_base<=0;magnitude_carry<=0;
      magnitude<=0;scale_low_sum<=0;scale_high_sum<=0;scaled<=0;rounded<=0;sample_o<=0;
    end else begin
      magnitude_low_valid<=valid_i;
      magnitude_valid<=magnitude_low_valid;
      scale_low_valid<=magnitude_valid;
      scaled_valid<=scale_low_valid;
      rounded_valid<=scaled_valid;
      valid_o<=rounded_valid;
      if(valid_i) begin
        magnitude_low<=mix_i[63] ? -mix_i[31:0] : mix_i[31:0];
        magnitude_high_base<=mix_i[63] ? ~mix_i[63:32] : mix_i[63:32];
        magnitude_carry<=mix_i[63] && mix_i[31:0]==0;
        low_negative<=mix_i[63];low_mode_c<=mode_i==2'd2;
      end
      if(magnitude_low_valid) begin
        magnitude<={magnitude_high_base+{31'd0,magnitude_carry},magnitude_low};
        magnitude_negative<=low_negative;magnitude_mode_c<=low_mode_c;
      end
      if(magnitude_valid) begin
        // Split the exact 66-bit 3*x adder at bit 33. Both halves are
        // independent here; the registered carry is applied next cycle.
        scale_low_sum<={1'b0,magnitude[32:0]}+{1'b0,magnitude[31:0],1'b0};
        scale_high_sum<={2'b0,magnitude[63:33]}+{1'b0,magnitude[63:32]};
        scale_low_negative<=magnitude_negative;scale_low_mode_c<=magnitude_mode_c;
      end
      if(scale_low_valid) begin
        scaled<={scale_high_sum+{32'd0,scale_low_sum[33]},scale_low_sum[32:0]};
        scaled_negative<=scale_low_negative;scaled_mode_c<=scale_low_mode_c;
      end
      if(scaled_valid) begin
        // Adding half an LSB before shifting is exactly the retained upper
        // bits plus the discarded rounding bit. Avoid a full 66-bit adder.
        rounded<=scaled_mode_c ?
            {1'b0,scaled[65:28]}+{{38{1'b0}},scaled[27]} :
            {4'b0,scaled[65:31]}+{{38{1'b0}},scaled[30]};
        rounded_negative<=scaled_negative;
      end
      if(rounded_valid) begin
        if(rounded_negative)
          sample_o<=rounded>39'd2147483648 ? 32'sh80000000 : -$signed(rounded[31:0]);
        else
          sample_o<=rounded>39'd2147483647 ? 32'sh7fffffff : $signed(rounded[31:0]);
      end
    end
  end
endmodule
