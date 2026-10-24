// PSN=DIF[2:0]=ACKS=1 on this daughterboard: pin control, 32-bit I2S.
// 12.288 MHz -> 256fs MCLK, 64fs BICK, 48 kHz LRCK. No SPI writes.
module ak4493_pin_test #(
    parameter integer RESET_CYCLES=245760,
    parameter integer WARMUP_FRAMES=4096,
    parameter integer PHASE_FRAMES=96000,
    parameter integer ISOLATE_CHANNELS=0,
    parameter integer CONTINUOUS_TONES=0
)(
    input wire audio_clk, restart_n,
    output reg pdn=0, output wire mclk, bick,
    output reg lrck=1, sdata=0, smute=1,
    output wire sslow, sd, slow,
    output reg [31:0] clock_gray=0, frame_gray=0,
    output reg [1:0] phase=0
);
    (* ASYNC_REG="TRUE" *) reg [1:0] restart_sync=0;
    always @(posedge audio_clk) restart_sync <= {restart_sync[0],restart_n};
    reg [31:0] clock_count=0;
    always @(posedge audio_clk) begin
        clock_count <= clock_count+1'b1;
        clock_gray <= ((clock_count+32'd1)>>1)^(clock_count+32'd1);
    end
    reg [31:0] frames=0;
    reg [31:0] reset_count=0, warmup=0, phase_frames=0;
    reg clocks_on=0;
    reg [7:0] divider=0;
    reg [5:0] bit_position=63, sine48=0, sine32=0;
    reg signed [31:0] left_sample=0, right_sample=0;
    // Enable changes only on the low-going source edge: complete MCLK pulses.
    assign mclk=audio_clk & clocks_on;
    assign bick=clocks_on & divider[1];
    assign sslow=0;
    assign sd=0;
    assign slow=0;
    function signed [31:0] tone48;
        input [5:0] index;
        begin
            case(index)
                6'd0: tone48=32'h00000000;
                6'd1: tone48=32'h0021f95d;
                6'd2: tone48=32'h00435de9;
                6'd3: tone48=32'h00639b60;
                6'd4: tone48=32'h0082248a;
                6'd5: tone48=32'h009e73a6;
                6'd6: tone48=32'h00b80cb4;
                6'd7: tone48=32'h00ce7f94;
                6'd8: tone48=32'h00e169f1;
                6'd9: tone48=32'h00f078f1;
                6'd10: tone48=32'h00fb6a9d;
                6'd11: tone48=32'h01020f07;
                6'd12: tone48=32'h01044915;
                6'd13: tone48=32'h01020f07;
                6'd14: tone48=32'h00fb6a9d;
                6'd15: tone48=32'h00f078f1;
                6'd16: tone48=32'h00e169f1;
                6'd17: tone48=32'h00ce7f94;
                6'd18: tone48=32'h00b80cb4;
                6'd19: tone48=32'h009e73a6;
                6'd20: tone48=32'h0082248a;
                6'd21: tone48=32'h00639b60;
                6'd22: tone48=32'h00435de9;
                6'd23: tone48=32'h0021f95d;
                6'd24: tone48=32'h00000000;
                6'd25: tone48=32'hffde06a3;
                6'd26: tone48=32'hffbca217;
                6'd27: tone48=32'hff9c64a0;
                6'd28: tone48=32'hff7ddb76;
                6'd29: tone48=32'hff618c5a;
                6'd30: tone48=32'hff47f34c;
                6'd31: tone48=32'hff31806c;
                6'd32: tone48=32'hff1e960f;
                6'd33: tone48=32'hff0f870f;
                6'd34: tone48=32'hff049563;
                6'd35: tone48=32'hfefdf0f9;
                6'd36: tone48=32'hfefbb6eb;
                6'd37: tone48=32'hfefdf0f9;
                6'd38: tone48=32'hff049563;
                6'd39: tone48=32'hff0f870f;
                6'd40: tone48=32'hff1e960f;
                6'd41: tone48=32'hff31806c;
                6'd42: tone48=32'hff47f34c;
                6'd43: tone48=32'hff618c5a;
                6'd44: tone48=32'hff7ddb76;
                6'd45: tone48=32'hff9c64a0;
                6'd46: tone48=32'hffbca217;
                6'd47: tone48=32'hffde06a3;
                default: tone48=0;
            endcase
        end
    endfunction
    function signed [31:0] tone32;
        input [5:0] index;
        begin
            case(index)
                6'd0: tone32=32'h00000000;
                6'd1: tone32=32'h0032c778;
                6'd2: tone32=32'h00639b60;
                6'd3: tone32=32'h00909b5b;
                6'd4: tone32=32'h00b80cb4;
                6'd5: tone32=32'h00d86b62;
                6'd6: tone32=32'h00f078f1;
                6'd7: tone32=32'h00ff48bf;
                6'd8: tone32=32'h01044915;
                6'd9: tone32=32'h00ff48bf;
                6'd10: tone32=32'h00f078f1;
                6'd11: tone32=32'h00d86b62;
                6'd12: tone32=32'h00b80cb4;
                6'd13: tone32=32'h00909b5b;
                6'd14: tone32=32'h00639b60;
                6'd15: tone32=32'h0032c778;
                6'd16: tone32=32'h00000000;
                6'd17: tone32=32'hffcd3888;
                6'd18: tone32=32'hff9c64a0;
                6'd19: tone32=32'hff6f64a5;
                6'd20: tone32=32'hff47f34c;
                6'd21: tone32=32'hff27949e;
                6'd22: tone32=32'hff0f870f;
                6'd23: tone32=32'hff00b741;
                6'd24: tone32=32'hfefbb6eb;
                6'd25: tone32=32'hff00b741;
                6'd26: tone32=32'hff0f870f;
                6'd27: tone32=32'hff27949e;
                6'd28: tone32=32'hff47f34c;
                6'd29: tone32=32'hff6f64a5;
                6'd30: tone32=32'hff9c64a0;
                6'd31: tone32=32'hffcd3888;
                default: tone32=0;
            endcase
        end
    endfunction
    // Update serial data and LRCK only on falling BICK edges.
    // Position 0/32 contains the previous channel LSB; MSB follows one bit later.
    always @(negedge audio_clk) begin
        if (!restart_sync[1]) begin
            pdn<=0; clocks_on<=0; smute<=1; reset_count<=0;
            divider<=0; bit_position<=63; lrck<=1; sdata<=0;
            frames<=0; frame_gray<=0; warmup<=0; phase_frames<=0; phase<=0;
            sine48<=0; sine32<=0; left_sample<=0; right_sample<=0;
        end else if (!pdn) begin
            if (reset_count==RESET_CYCLES-1) begin pdn<=1; reset_count<=0; end
            else reset_count<=reset_count+1'b1;
        end else if (!clocks_on) clocks_on<=1;
        else begin
            divider<=divider+1'b1;
            if (divider[1:0]==2'b11) begin
                bit_position<=bit_position+1'b1;
                if (bit_position==63) begin
                    lrck<=0; sdata<=right_sample[0]; frames<=frames+1'b1;
                    frame_gray<=((frames+32'd1)>>1)^(frames+32'd1);
                    if (warmup<WARMUP_FRAMES) begin
                        warmup<=warmup+1'b1;
                        left_sample<=0; right_sample<=0;
                    end else begin
                        smute<=0;
                        // Isolation mode: silence / left / silence / right.
                        left_sample<=(CONTINUOUS_TONES || phase==1 || (!ISOLATE_CHANNELS && phase==3)) ? tone48(sine48) : 32'd0;
                        right_sample<=(CONTINUOUS_TONES || (ISOLATE_CHANNELS && phase==3) ||
                            (!ISOLATE_CHANNELS && (phase==2 || phase==3))) ? tone32(sine32) : 32'd0;
                        sine48<=sine48==47 ? 6'd0 : sine48+1'b1;
                        sine32<=sine32==31 ? 6'd0 : sine32+1'b1;
                        if (CONTINUOUS_TONES) begin
                            phase_frames<=0; phase<=3;
                        end else if (phase_frames==PHASE_FRAMES-1) begin
                            phase_frames<=0; phase<=phase+1'b1;
                        end else phase_frames<=phase_frames+1'b1;
                    end
                end else if (bit_position==31) begin lrck<=1; sdata<=left_sample[0]; end
                else if (bit_position<31) sdata<=left_sample[31-bit_position];
                else sdata<=right_sample[63-bit_position];
            end
        end
    end
endmodule
