// Time-division voice bank: one sine ROM and one signed 32 x 33 gain
// multiplier serve every voice. The per-voice state is a synchronous RAM;
// only the selected voice occupies arithmetic/pipeline registers.
//
// sample_valid follows an accepted sample_tick by 7*VOICE_COUNT+1 clocks.
// Commands and the pre-update audio/reference state share that boundary.
// The committed active mask is published atomically with sample_valid.
module synth_voice_bank #(parameter integer VOICE_COUNT = 32) (
    input wire clk, input wire rst_n, input wire sample_tick,
    input wire [31:0] command_header, input wire [31:0] command_value,
    input wire command_apply,
    output reg signed [31:0] sample_data, output reg sample_valid,
    output reg signed [39:0] mix_sum,
    output wire voice_sample_event,
    output wire signed [31:0] voice_sample_data,
    output wire [4:0] voice_sample_index,
    output reg [31:0] active_voices, output reg [31:0] nonzero_voices,
    output reg reference_valid, output reg [5:0] reference_voice,
    output reg [31:0] reference_phase,
    output wire busy, output wire ready
);
    localparam integer INDEX_BITS = VOICE_COUNT > 1 ? $clog2(VOICE_COUNT) : 1;
    localparam integer STATE_BITS = 262;
    localparam [2:0] ENV_IDLE=0, ATTACK=1, DECAY=2, SUSTAIN=3, RELEASE=4;
    localparam [31:0] UNITY = 32'h80000000;
    localparam [31:0] RETRIGGER_MAX_STEP = 32'h01000000;
    localparam [1:0] WAVE_PULSE=1, WAVE_SINE=2;
    localparam [3:0] INITIALIZE=0, WAIT_FRAME=1, READ_STATE=2, PREPARE=3,
                     MULTIPLY_ENVELOPE=4, QUANTIZE_ENVELOPE=5,
                     MULTIPLY_VELOCITY=6, QUANTIZE_VELOCITY=7,
                     WRITE_STATE=8, FINISH_FRAME=9;
    localparam [STATE_BITS-1:0] RESET_STATE = {
        32'd0, 32'd0, 32'd0, 32'h60000000,
        32'd8800000, 32'd128000, 32'h50000000, 32'd440000,
        2'd0, ENV_IDLE, 1'b0
    };

    reg [3:0] state;
    reg [INDEX_BITS-1:0] voice_index;
    // No array reset: initialization writes one entry per clock. The RAM
    // remains a memory when VOICE_COUNT grows instead of a resettable mux.
    (* syn_ramstyle = "block_ram" *) reg [STATE_BITS-1:0] state_memory [0:VOICE_COUNT-1];
    reg [STATE_BITS-1:0] current_state, next_state;
    always @(posedge clk) begin
        if (state == INITIALIZE) state_memory[voice_index] <= RESET_STATE;
        else if (state == WRITE_STATE) state_memory[voice_index] <= next_state;
        if (state == READ_STATE) current_state <= state_memory[voice_index];
    end
    assign busy = state != WAIT_FRAME;
    assign ready = state == WAIT_FRAME;

    wire [31:0] phase, phase_step, envelope, velocity;
    wire [31:0] attack_step, decay_step, sustain_level, release_step;
    wire [1:0] waveform;
    wire [2:0] envelope_stage;
    wire retrigger_smooth;
    assign {phase,phase_step,envelope,velocity,attack_step,decay_step,
            sustain_level,release_step,waveform,envelope_stage,retrigger_smooth} = current_state;
    wire active = envelope_stage != ENV_IDLE;
    wire [31:0] attack_increment = retrigger_smooth &&
        (attack_step == 0 || attack_step > RETRIGGER_MAX_STEP) ? RETRIGGER_MAX_STEP : attack_step;
    wire [31:0] decay_increment = retrigger_smooth &&
        (decay_step == 0 || decay_step > RETRIGGER_MAX_STEP) ? RETRIGGER_MAX_STEP : decay_step;

    reg [31:0] frame_header, frame_value;
    reg frame_apply;
    wire selected = frame_header[15:8] == voice_index;
    wire panic = frame_header[23:16] == 8'h0a;
    reg [31:0] next_phase, next_step, next_envelope, next_velocity;
    reg [31:0] next_attack, next_decay, next_sustain, next_release;
    reg [1:0] next_waveform;
    reg [2:0] next_stage;
    reg next_retrigger;
    always @* begin
        next_phase = active ? phase + phase_step : phase;
        next_step = phase_step; next_envelope = envelope; next_velocity = velocity;
        next_attack = attack_step; next_decay = decay_step;
        next_sustain = sustain_level; next_release = release_step;
        next_waveform = waveform; next_stage = envelope_stage; next_retrigger = retrigger_smooth;
        case (envelope_stage)
            ENV_IDLE: begin next_envelope = 0; next_retrigger = 0; end
            ATTACK: if (attack_increment == 0 || UNITY-envelope <= attack_increment) begin
                        next_envelope = UNITY; next_stage = DECAY;
                    end else next_envelope = envelope + attack_increment;
            DECAY: if (decay_increment == 0 || envelope <= sustain_level ||
                       envelope-sustain_level <= decay_increment) begin
                       next_envelope = sustain_level; next_stage = SUSTAIN; next_retrigger = 0;
                   end else next_envelope = envelope - decay_increment;
            SUSTAIN: next_envelope = sustain_level;
            RELEASE: if (release_step == 0 || envelope <= release_step) begin
                         next_envelope = 0; next_stage = ENV_IDLE;
                     end else next_envelope = envelope - release_step;
            default: begin next_envelope = 0; next_stage = ENV_IDLE; end
        endcase
        // Identical priority to synth_voice: samples use old state, while
        // commands override this frame's normal phase/envelope advancement.
        if (frame_apply) begin
            if (panic) begin
                next_envelope = 0; next_stage = ENV_IDLE; next_phase = 0; next_retrigger = 0;
            end else if (selected) case (frame_header[23:16])
                8'h01: begin
                    next_step = frame_value; next_stage = ATTACK;
                    if (active && envelope != 0) begin
                        next_envelope = envelope; next_retrigger = 1;
                    end else begin next_phase = 0; next_envelope = 0; next_retrigger = 0; end
                end
                8'h02: if (active) begin next_stage = RELEASE; next_retrigger = 0; end
                8'h03: next_step = frame_value;
                8'h04: next_velocity = frame_value;
                8'h05: next_waveform = frame_value[1:0];
                8'h06: next_attack = frame_value;
                8'h07: next_decay = frame_value;
                8'h08: next_sustain = frame_value;
                8'h09: next_release = frame_value;
                default: begin end
            endcase
        end
    end

    wire signed [31:0] sine_sample;
    synth_sine_rom sine_rom(.phase_index(phase[31:22]),.sample_data(sine_sample));
    function signed [31:0] geometric_oscillator;
        input [31:0] p; input [1:0] kind;
        reg signed [31:0] ramp;
        begin
            ramp = $signed({1'b0,p[29:0],1'b0});
            if (kind == WAVE_PULSE) geometric_oscillator = p[31] ? -32'sh7fffffff : 32'sh7fffffff;
            else case (p[31:30])
                2'b00: geometric_oscillator = ramp;
                2'b01: geometric_oscillator = 32'sh7fffffff-ramp;
                2'b10: geometric_oscillator = -ramp;
                2'b11: geometric_oscillator = -32'sh7fffffff+ramp;
            endcase
        end
    endfunction

    reg signed [31:0] multiply_sample, completed_sample;
    reg [31:0] multiply_gain, saved_velocity;
    reg signed [64:0] multiply_product;
    // Exactly one multiplier expression, used on two different FSM cycles.
    // Registers inside this datapath are overwritten before use after reset.
    always @(posedge clk) begin
        if (state == MULTIPLY_ENVELOPE || state == MULTIPLY_VELOCITY)
            multiply_product <= multiply_sample * $signed({1'b0,multiply_gain});
    end

    reg signed [39:0] accumulated_sample;
    reg [31:0] frame_active, frame_nonzero;
    // Preserve every voice's Q1.31 level. The output stage applies master
    // gain to the wide sum before its final saturation, never per-slot 1/N.
    // This diagnostic mask describes each voice before master/balance gain.
    wire voice_pcm_nonzero = completed_sample >= 32'sd32768 || completed_sample <= -32'sd32768;
    assign voice_sample_event = state == WRITE_STATE;
    assign voice_sample_data = completed_sample;
    assign voice_sample_index = voice_index;
    reg frame_reference_valid;
    reg [5:0] frame_reference_voice;
    reg [31:0] frame_reference_phase, frame_reference_step;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= INITIALIZE; voice_index <= 0;
            frame_header <= 0; frame_value <= 0; frame_apply <= 0;
            sample_data <= 0; mix_sum <= 0; sample_valid <= 0; active_voices <= 0; nonzero_voices <= 0;
            reference_valid <= 0; reference_voice <= 0; reference_phase <= 0;
            frame_active <= 0; frame_nonzero <= 0; accumulated_sample <= 0;
            frame_reference_valid <= 0; frame_reference_voice <= 0;
            frame_reference_phase <= 0; frame_reference_step <= 32'hffffffff;
        end else begin
            sample_valid <= 0;
            case (state)
                INITIALIZE: if (voice_index == VOICE_COUNT-1) begin
                    voice_index <= 0; state <= WAIT_FRAME;
                end else voice_index <= voice_index + 1'b1;
                WAIT_FRAME: if (sample_tick) begin
                    frame_header <= command_header; frame_value <= command_value;
                    frame_apply <= command_apply; voice_index <= 0;
                    accumulated_sample <= 0; frame_active <= 0; frame_nonzero <= 0;
                    frame_reference_valid <= 0; frame_reference_voice <= 0;
                    frame_reference_phase <= 0; frame_reference_step <= 32'hffffffff;
                    state <= READ_STATE;
                end
                READ_STATE: state <= PREPARE;
                PREPARE: begin
                    next_state <= {next_phase,next_step,next_envelope,next_velocity,
                                   next_attack,next_decay,next_sustain,next_release,
                                   next_waveform,next_stage,next_retrigger};
                    multiply_sample <= waveform == WAVE_SINE ? sine_sample : geometric_oscillator(phase,waveform);
                    multiply_gain <= envelope; saved_velocity <= velocity;
                    frame_active[voice_index] <= next_stage != ENV_IDLE;
                    // Traverse low to high and use strict < to resolve ties.
                    if (active && envelope != 0 && velocity != 0 && phase_step != 0 &&
                        phase_step < frame_reference_step) begin
                        frame_reference_valid <= 1; frame_reference_voice <= voice_index;
                        frame_reference_phase <= phase; frame_reference_step <= phase_step;
                    end
                    state <= MULTIPLY_ENVELOPE;
                end
                MULTIPLY_ENVELOPE: state <= QUANTIZE_ENVELOPE;
                QUANTIZE_ENVELOPE: begin
                    // Q1.31 floor quantization matches the parallel baseline.
                    multiply_sample <= multiply_product[62:31]; multiply_gain <= saved_velocity;
                    state <= MULTIPLY_VELOCITY;
                end
                MULTIPLY_VELOCITY: state <= QUANTIZE_VELOCITY;
                QUANTIZE_VELOCITY: begin
                    completed_sample <= multiply_product[62:31]; state <= WRITE_STATE;
                end
                WRITE_STATE: begin
                    frame_nonzero[voice_index] <= voice_pcm_nonzero;
                    accumulated_sample <= accumulated_sample + {{8{completed_sample[31]}},completed_sample};
                    if (voice_index == VOICE_COUNT-1) state <= FINISH_FRAME;
                    else begin voice_index <= voice_index + 1'b1; state <= READ_STATE; end
                end
                FINISH_FRAME: begin
                    mix_sum <= accumulated_sample;
                    if (accumulated_sample > 40'sd2147483647) sample_data <= 32'sh7fffffff;
                    else if (accumulated_sample < -40'sd2147483648) sample_data <= 32'sh80000000;
                    else sample_data <= accumulated_sample[31:0];
                    sample_valid <= 1; active_voices <= frame_active; nonzero_voices <= frame_nonzero;
                    reference_valid <= frame_reference_valid;
                    reference_voice <= frame_reference_voice; reference_phase <= frame_reference_phase;
                    state <= WAIT_FRAME;
                end
                default: begin state <= INITIALIZE; voice_index <= 0; end
            endcase
        end
    end
endmodule
