// One independent oscillator, linear ADSR and velocity gain.
// Public numerical links are 32 bits; wide products remain private.
module synth_voice #(parameter integer VOICE_ID = 0) (
    input wire clk, input wire rst_n, input wire sample_tick,
    input wire [31:0] command_header, input wire [31:0] command_value,
    input wire command_apply,
    output reg signed [31:0] sample_data, output reg sample_valid,
    output wire active,
    // Read-only oscillator state, sampled beside raw_wave for display timing.
    output wire [31:0] display_phase, display_step,
    output wire display_active
);
    localparam [2:0] IDLE=0, ATTACK=1, DECAY=2, SUSTAIN=3, RELEASE=4;
    localparam [31:0] UNITY = 32'h80000000;
    reg [31:0] phase, phase_step, envelope, velocity;
    reg [31:0] attack_step, decay_step, sustain_level, release_step;
    localparam [1:0] WAVE_TRIANGLE=0, WAVE_PULSE=1, WAVE_SINE=2;
    reg [1:0] waveform;
    reg [2:0] envelope_stage;
    // Reusing a releasing/held voice must not cut its current waveform to
    // zero. Keep phase and level, then reattack from that level. Cap only
    // this reattack's fast A/D steps (1/128 full scale per sample, 2.62 ms
    // for a full-scale ramp at 48,828.125 Hz). Normal slower ADSR is intact.
    localparam [31:0] RETRIGGER_MAX_STEP = 32'h01000000;
    reg retrigger_smooth;
    wire [31:0] attack_increment = retrigger_smooth &&
        (attack_step == 0 || attack_step > RETRIGGER_MAX_STEP) ? RETRIGGER_MAX_STEP : attack_step;
    wire [31:0] decay_increment = retrigger_smooth &&
        (decay_step == 0 || decay_step > RETRIGGER_MAX_STEP) ? RETRIGGER_MAX_STEP : decay_step;
    assign active = envelope_stage != IDLE;
    assign display_phase = phase;
    assign display_step = phase_step;
    assign display_active = active && envelope != 0 && velocity != 0;
    wire selected = command_header[15:8] == VOICE_ID;
    wire panic = command_header[23:16] == 8'h0a;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase <= 0; phase_step <= 0; envelope <= 0; velocity <= 32'h60000000;
            attack_step <= 32'd8800000; decay_step <= 32'd128000;
            sustain_level <= 32'h50000000; release_step <= 32'd440000;
            waveform <= WAVE_TRIANGLE; envelope_stage <= IDLE; retrigger_smooth <= 0;
        end else if (sample_tick) begin
            if (active) phase <= phase+phase_step;
            case (envelope_stage)
                IDLE: begin envelope <= 0; retrigger_smooth <= 0; end
                ATTACK: if (attack_increment == 0 || UNITY-envelope <= attack_increment) begin
                            envelope <= UNITY; envelope_stage <= DECAY;
                        end else envelope <= envelope+attack_increment;
                DECAY: if (decay_increment == 0 || envelope <= sustain_level || envelope-sustain_level <= decay_increment) begin
                           envelope <= sustain_level; envelope_stage <= SUSTAIN; retrigger_smooth <= 0;
                       end else envelope <= envelope-decay_increment;
                SUSTAIN: envelope <= sustain_level;
                RELEASE: if (release_step == 0 || envelope <= release_step) begin
                             envelope <= 0; envelope_stage <= IDLE;
                         end else envelope <= envelope-release_step;
                default: begin envelope <= 0; envelope_stage <= IDLE; end
            endcase
            // Commands take priority over normal state updates at this boundary.
            if (command_apply) begin
                if (panic) begin envelope <= 0; envelope_stage <= IDLE; phase <= 0; retrigger_smooth <= 0; end
                else if (selected) case (command_header[23:16])
                    8'h01: begin
                        phase_step <= command_value; envelope_stage <= ATTACK;
                        if (active && envelope != 0) begin
                            // The normal phase advance above still applies.
                            // Override this tick's ADSR update with its current
                            // level so even a release-end boundary is continuous.
                            envelope <= envelope; retrigger_smooth <= 1;
                        end else begin
                            phase <= 0; envelope <= 0; retrigger_smooth <= 0;
                        end
                    end
                    8'h02: if (active) begin envelope_stage <= RELEASE; retrigger_smooth <= 0; end
                    8'h03: phase_step <= command_value; // phase remains continuous
                    8'h04: velocity <= command_value;
                    8'h05: waveform <= command_value[1:0];
                    8'h06: attack_step <= command_value;
                    8'h07: decay_step <= command_value;
                    8'h08: sustain_level <= command_value;
                    8'h09: release_step <= command_value;
                    default: begin end
                endcase
            end
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
    reg [3:0] valid_pipe;
    reg signed [31:0] raw_wave, envelope_sample;
    reg [31:0] envelope_gain, velocity_gain, velocity_delayed;
    reg signed [64:0] envelope_product, velocity_product;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_pipe <= 0; raw_wave <= 0; envelope_sample <= 0; envelope_gain <= 0;
            velocity_gain <= 0; velocity_delayed <= 0; envelope_product <= 0;
            velocity_product <= 0; sample_data <= 0; sample_valid <= 0;
        end else begin
            valid_pipe <= {valid_pipe[2:0],sample_tick};
            sample_valid <= valid_pipe[3];
            if (sample_tick) begin
                raw_wave <= waveform == WAVE_SINE ? sine_sample : geometric_oscillator(phase,waveform);
                envelope_gain <= envelope; velocity_gain <= velocity;
            end
            if (valid_pipe[0]) envelope_product <= raw_wave * $signed({1'b0,envelope_gain});
            if (valid_pipe[1]) begin
                // Q1.31 floor quantization. Gains <= 1 keep the discarded high bits sign extensions.
                envelope_sample <= envelope_product[62:31]; velocity_delayed <= velocity_gain;
            end
            if (valid_pipe[2]) velocity_product <= envelope_sample * $signed({1'b0,velocity_delayed});
            if (valid_pipe[3]) sample_data <= velocity_product[62:31];
        end
    end
endmodule
