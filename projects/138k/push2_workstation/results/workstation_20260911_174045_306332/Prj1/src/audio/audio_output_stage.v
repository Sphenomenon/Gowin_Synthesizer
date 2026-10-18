`default_nettype none
// Full-width voice sum -> smoothed master -> L/R balance -> saturation.
// One multiplier also observes individual post-master contributions while
// the voice bank scans. Center balance is unity in both channels; at least
// one channel always has unity balance gain, so master alone determines
// whether a voice reaches the final PCM16 nonzero threshold in either ear.
module audio_output_stage (
    input wire clk, reset_n, frame_start,
    input wire [31:0] master_target, balance_target,
    input wire signed [39:0] mix_sum,
    input wire mix_valid,
    input wire [31:0] mix_reference,
    input wire voice_sample_event,
    input wire signed [31:0] voice_sample_data,
    input wire [4:0] voice_sample_index,
    output reg signed [31:0] sample_left, sample_right,
    output reg sample_valid,
    output reg [31:0] sample_reference, sample_nonzero_voices,
    output wire trace_sample_event,
    output wire [23:0] trace_sample_revision,
    output wire [31:0] trace_nonzero_voices
);
    localparam [31:0] UNITY=32'h80000000, CENTER=32'h40000000;
    localparam [31:0] SLEW_STEP=32'h00800000; // Full range / 256 = 5.24 ms.
    localparam [3:0] IDLE=0, MIX_MULT=1, MIX_SAVE=2, LEFT_MULT=3,
        LEFT_SAVE=4, RIGHT_MULT=5, RIGHT_SAVE=6, COMMIT=7;
    reg [3:0] state;
    reg [31:0] master_current, balance_current;
    reg [31:0] frame_master, frame_left_gain, frame_right_gain;
    reg signed [39:0] mix_held, mastered_mix;
    reg signed [31:0] left_held, right_held;
    reg [31:0] reference_held, frame_nonzero;
    reg voice_pending;
    reg [4:0] pending_voice;

    function [31:0] slew;
        input [31:0] current_value,target_value;
        begin
            if(target_value>current_value)
                slew=target_value-current_value>SLEW_STEP ? current_value+SLEW_STEP : target_value;
            else slew=current_value-target_value>SLEW_STEP ? current_value-SLEW_STEP : target_value;
        end
    endfunction
    wire [31:0] next_master=slew(master_current,master_target);
    wire [31:0] next_balance=slew(balance_current,balance_target);
    wire [31:0] left_gain=next_balance>CENTER ? (UNITY-next_balance)<<1 : UNITY;
    wire [31:0] right_gain=next_balance<CENTER ? next_balance<<1 : UNITY;

    reg signed [39:0] multiply_sample;
    reg [31:0] multiply_gain;
    reg signed [72:0] product;
    always @* begin
        multiply_sample=mix_held; multiply_gain=frame_master;
        if(voice_sample_event) multiply_sample={{8{voice_sample_data[31]}},voice_sample_data};
        else if(state==LEFT_MULT || state==RIGHT_MULT) begin
            multiply_sample=mastered_mix;
            multiply_gain=state==LEFT_MULT ? frame_left_gain : frame_right_gain;
        end
    end
    always @(posedge clk)
        if(voice_sample_event || state==MIX_MULT || state==LEFT_MULT || state==RIGHT_MULT)
            product<=multiply_sample*$signed({1'b0,multiply_gain});
    // Inputs are at most 32 full-scale voices and all gains are <=unity.
    // The sign bits above bit70 are redundant; keep the complete Q*.31 sum.
    wire signed [39:0] gained_sample=product[70:31];
    wire voice_pcm_nonzero=gained_sample>=40'sd32768 || gained_sample<=-40'sd32768;
    function signed [31:0] saturate;
        input signed [39:0] value;
        begin
            if(value>40'sd2147483647) saturate=32'sh7fffffff;
            else if(value< -40'sd2147483648) saturate=32'sh80000000;
            else saturate=value[31:0];
        end
    endfunction
    assign trace_sample_event=state==COMMIT;
    assign trace_sample_revision=reference_held[31:8];
    assign trace_nonzero_voices=frame_nonzero;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            state<=IDLE; master_current<=UNITY; balance_current<=CENTER;
            frame_master<=UNITY; frame_left_gain<=UNITY; frame_right_gain<=UNITY;
            mix_held<=0; mastered_mix<=0; left_held<=0; right_held<=0;
            reference_held<=0; frame_nonzero<=0; voice_pending<=0; pending_voice<=0;
            sample_left<=0; sample_right<=0; sample_valid<=0;
            sample_reference<=0; sample_nonzero_voices<=0;
        end else begin
            sample_valid<=0; voice_pending<=voice_sample_event;
            if(voice_sample_event) pending_voice<=voice_sample_index;
            if(voice_pending) frame_nonzero[pending_voice]<=voice_pcm_nonzero;
            if(frame_start) begin
                master_current<=next_master; balance_current<=next_balance;
                frame_master<=next_master; frame_left_gain<=left_gain; frame_right_gain<=right_gain;
                frame_nonzero<=0;
            end
            case(state)
                IDLE: if(mix_valid) begin mix_held<=mix_sum; reference_held<=mix_reference; state<=MIX_MULT; end
                MIX_MULT: state<=MIX_SAVE;
                MIX_SAVE: begin mastered_mix<=gained_sample; state<=LEFT_MULT; end
                LEFT_MULT: state<=LEFT_SAVE;
                LEFT_SAVE: begin left_held<=saturate(gained_sample); state<=RIGHT_MULT; end
                RIGHT_MULT: state<=RIGHT_SAVE;
                RIGHT_SAVE: begin right_held<=saturate(gained_sample); state<=COMMIT; end
                COMMIT: begin
                    sample_left<=left_held; sample_right<=right_held; sample_valid<=1;
                    sample_reference<=reference_held; sample_nonzero_voices<=frame_nonzero; state<=IDLE;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
