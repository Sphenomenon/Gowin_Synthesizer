`timescale 1ns/1ps
// Optional control-only cue ROM. Playback begins only with a live start pulse.
// Absolute cue times are 48 kHz sample counts; Q8 speed changes time progression.
module scope_control_player #(
    parameter integer CUE_COUNT=69,
    parameter CUE_FILE="rtl/audio/scope_vec/data/scene_controls.mem"
)(
    input wire clk_i,rst_ni,sample_ce_i,start_i,stop_i,
    input wire [9:0] speed_q8_i,
    output wire event_valid_o,
    input wire event_ready_i,
    output wire [17:0] event_o,
    output reg running_o,done_o,config_error_o,
    output reg [31:0] late_events_o,time_samples_o
);
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [63:0] cues[0:255];
    reg [7:0] address;
    reg [63:0] cue;
    reg [1:0] state;
    reg [7:0] fraction;
    reg [10:0] advanced_fraction;
    reg [31:0] previous_time;
    wire legal=cue[31:18]==0 && (cue[17:14]==0 || cue[17:14]==1 || cue[17:14]==2 || cue[17:14]==4)
        && cue[63:32]>=previous_time && !(cue[17:14]==1 && cue[6:0]==0);
    assign event_valid_o=running_o && state==2 && legal && time_samples_o>=cue[63:32];
    assign event_o=cue[17:0];
    initial begin
        if(CUE_COUNT<1 || CUE_COUNT>256)$fatal(1,"scope cue count exceeds 256x64 control RAM budget");
        $readmemh(CUE_FILE,cues);
    end
    always @(posedge clk_i) if(state==1) cue<=cues[address];
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            running_o<=0;done_o<=0;config_error_o<=0;late_events_o<=0;time_samples_o<=0;
            address<=0;state<=0;fraction<=0;previous_time<=0;advanced_fraction<=0;
        end else if(stop_i) begin running_o<=0;state<=0;end
        else if(start_i) begin
            if(running_o || speed_q8_i==0) config_error_o<=1;
            else begin running_o<=1;done_o<=0;address<=0;state<=1;time_samples_o<=0;fraction<=0;previous_time<=0;end
        end else if(running_o) begin
            if(speed_q8_i==0) begin config_error_o<=1;running_o<=0;state<=0;end
            else begin
                if(sample_ce_i) begin
                    advanced_fraction={3'd0,fraction}+{1'b0,speed_q8_i};
                    fraction<=advanced_fraction[7:0];time_samples_o<=time_samples_o+{29'd0,advanced_fraction[10:8]};
                end
                case(state)
                    1:state<=2;
                    2:if(!legal) begin config_error_o<=1;running_o<=0;state<=0;end
                      else if(event_valid_o && event_ready_i) begin
                        if(time_samples_o>cue[63:32])late_events_o<=late_events_o+1'b1;
                        previous_time<=cue[63:32];
                        if(32'(address)==CUE_COUNT-1) begin running_o<=0;done_o<=1;state<=0;end
                        else begin address<=address+1'b1;state<=1;end
                      end
                    default:begin config_error_o<=1;running_o<=0;state<=0;end
                endcase
            end
        end
    end
endmodule
