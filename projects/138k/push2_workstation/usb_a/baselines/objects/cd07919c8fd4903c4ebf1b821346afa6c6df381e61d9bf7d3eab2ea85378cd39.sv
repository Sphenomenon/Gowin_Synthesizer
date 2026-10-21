`timescale 1ns/1ps
// Six first-order image sources (stereo excess paths) followed by a shared
// four-line, orthogonal Hadamard FDN. 48 kHz, Q1.31 signal, 7/8 loop loss,
// low-pass damping and slewed wet mix. Fixed room preset, no HRTF or wave grid.
module serial_spatial_reverb (
    input logic clk_i,rst_ni,clear_i,valid_i,enabled_i,
    input logic signed [31:0] left_i,right_i,
    output wire ready_o,active_o,
    output logic valid_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o
);
    import audio_math_pkg::*;
    `include "rtl/audio/spatial_room_preset.svh"
    function automatic integer delay_length(input integer lane);
        case(lane) 0:delay_length=1429;1:delay_length=1789;
                   2:delay_length=1999;default:delay_length=2131;endcase
    endfunction
    logic [3:0] state,tap;
    logic [11:0] pointer[0:3];
    wire [31:0] line_data[0:3];
    wire [3:0] line_valid;
    wire early_valid;
    logic signed [31:0] line_write[0:3],tail[0:3],damping[0:3];
    logic [10:0] early_pointer,early_address;
    wire [31:0] early_data;
    logic [11:0] frames; // saturates once every delay line is initialized
    logic [15:0] gain;
    logic signed [31:0] dry_l,dry_r;
    logic signed [63:0] early_l,early_r,mixed_l,mixed_r;
    logic signed [48:0] early_product,wet_product_l,wet_product_r;
    logic internal_clip;
    wire signed [63:0] mono=($signed({{32{dry_l[31]}},dry_l})+$signed({{32{dry_r[31]}},dry_r}))>>>1;
    logic signed [32:0] sum01,diff01,sum23,diff23;
    wire signed [63:0] p0={{31{sum01[32]}},sum01};
    wire signed [63:0] p1={{31{diff01[32]}},diff01};
    wire signed [63:0] p2={{31{sum23[32]}},sum23};
    wire signed [63:0] p3={{31{diff23[32]}},diff23};
    logic signed [63:0] h[0:3],loop_gain[0:3],feedback[0:3];
    for(genvar lane=0;lane<4;lane=lane+1) begin : g_fdn
        workstation_sdp_banked #(.WORDS(delay_length(lane)),.ADDR_WIDTH(12)) ram(
            .rst_ni(rst_ni),.clear_i(clear_i),
            .write_clk_i(clk_i),.write_enable_i(rst_ni && !clear_i && state==10),
            .write_addr_i(pointer[lane]),.write_data_i(line_write[lane]),
            .read_clk_i(clk_i),.read_request_i(state==0 && valid_i && !clear_i),
            .read_addr_i(pointer[lane]),.read_valid_o(line_valid[lane]),.read_data_o(line_data[lane]));
    end
    workstation_sdp_banked #(.WORDS(2048),.ADDR_WIDTH(11)) early_ram(
        .rst_ni(rst_ni),.clear_i(clear_i),
            .write_clk_i(clk_i),.write_enable_i(rst_ni && !clear_i && state==10),
        .write_addr_i(early_pointer),.write_data_i(mono[31:0]),
        .read_clk_i(clk_i),.read_request_i(state==4),.read_valid_o(early_valid),
        .read_addr_i(early_address),.read_data_o(early_data));
    logic signed [32:0] tail_sum01,tail_diff01,tail_sum23,tail_diff23;
    logic signed [31:0] tail_mix_l,tail_mix_r;
    wire signed [63:0] ts0={{31{tail_sum01[32]}},tail_sum01};
    wire signed [63:0] ts1={{31{tail_diff01[32]}},tail_diff01};
    wire signed [63:0] ts2={{31{tail_sum23[32]}},tail_sum23};
    wire signed [63:0] ts3={{31{tail_diff23[32]}},tail_diff23};
    wire signed [31:0] wet_l=sat31(early_l+{{32{tail_mix_l[31]}},tail_mix_l});
    wire signed [31:0] wet_r=sat31(early_r+{{32{tail_mix_r[31]}},tail_mix_r});
    assign ready_o=state==0;
    assign active_o=enabled_i || gain!=0;
    integer i;
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            state<=0;tap<=0;frames<=0;gain<=0;early_pointer<=0;early_address<=0;
            dry_l<=0;dry_r<=0;early_l<=0;early_r<=0;early_product<=0;
            wet_product_l<=0;wet_product_r<=0;mixed_l<=0;mixed_r<=0;
            left_o<=0;right_o<=0;valid_o<=0;clip_o<=0;internal_clip<=0;
            sum01<=0;diff01<=0;sum23<=0;diff23<=0;
            tail_sum01<=0;tail_diff01<=0;tail_sum23<=0;tail_diff23<=0;tail_mix_l<=0;tail_mix_r<=0;
            for(i=0;i<4;i=i+1) begin
                pointer[i]<=0;tail[i]<=0;damping[i]<=0;line_write[i]<=0;
                h[i]<=0;loop_gain[i]<=0;feedback[i]<=0;
            end
        end else begin
            valid_o<=0;clip_o<=0;
            if(clear_i) begin
                state<=0;tap<=0;frames<=0;gain<=0;early_pointer<=0;early_address<=0;
                early_l<=0;early_r<=0;internal_clip<=0;
                for(i=0;i<4;i=i+1) begin pointer[i]<=0;tail[i]<=0;damping[i]<=0;end
            end else case(state)
                0: if(valid_i) begin
                    dry_l<=left_i;dry_r<=right_i;early_l<=0;early_r<=0;tap<=0;
                    gain<=slew15(gain,enabled_i ? 16'd8192 : 16'd0);
                    internal_clip<=0;state<=1;
                end
                1:state<=2;
                2:if(&line_valid)begin
                    for(i=0;i<4;i=i+1) begin
                        tail[i]<=frames>=delay_length(i) ? $signed(line_data[i]) : 32'sd0;
                        damping[i]<=sat31(($signed({{32{damping[i][31]}},damping[i]})+
                            (frames>=delay_length(i) ? $signed({{32{line_data[i][31]}},line_data[i]}) : 64'sd0))>>>1);
                    end
                    state<=3;
                end
                // Hide the feedback pipeline behind the early-reflection RAM
                // reads. Every operation keeps the original signed precision.
                3:begin
                    early_address<=early_pointer-11'(early_delay(tap));state<=4;
                    if(tap==0)begin
                        tail_sum01<=$signed({tail[0][31],tail[0]})+$signed({tail[1][31],tail[1]});
                        tail_diff01<=$signed({tail[0][31],tail[0]})-$signed({tail[1][31],tail[1]});
                        tail_sum23<=$signed({tail[2][31],tail[2]})+$signed({tail[3][31],tail[3]});
                        tail_diff23<=$signed({tail[2][31],tail[2]})-$signed({tail[3][31],tail[3]});
                        sum01<=$signed({damping[0][31],damping[0]})+$signed({damping[1][31],damping[1]});
                        diff01<=$signed({damping[0][31],damping[0]})-$signed({damping[1][31],damping[1]});
                        sum23<=$signed({damping[2][31],damping[2]})+$signed({damping[3][31],damping[3]});
                        diff23<=$signed({damping[2][31],damping[2]})-$signed({damping[3][31],damping[3]});
                    end
                end
                4:begin
                    if(tap==0)begin
                        tail_mix_l<=32'((ts0-ts2)>>>2);tail_mix_r<=32'((ts1+ts3)>>>2);
                        h[0]<=(p0+p2)>>>1;h[1]<=(p1+p3)>>>1;
                        h[2]<=(p0-p2)>>>1;h[3]<=(p1-p3)>>>1;
                    end
                    state<=5;
                end
                5:if(early_valid)begin
                    if(tap==0)for(i=0;i<4;i=i+1)loop_gain[i]<=h[i]-(h[i]>>>3);
                    early_product<=(frames>=early_delay(tap) ? $signed(early_data) : 32'sd0)*$signed({1'b0,early_gain(tap)});
                    state<=6;
                end
                6:begin
                    if(tap==0)for(i=0;i<4;i=i+1)feedback[i]<=(mono>>>3)+loop_gain[i];
                    if(tap[0]) early_r<=early_r+($signed(early_product)>>>15);
                    else early_l<=early_l+($signed(early_product)>>>15);
                    if(tap==11) state<=7;else begin tap<=tap+1'b1;state<=3;end
                end
                7:begin
                    for(i=0;i<4;i=i+1) begin
                        line_write[i]<=sat31(feedback[i]);
                        if(feedback[i]>64'sd2147483647 || feedback[i]< -64'sd2147483648) internal_clip<=1;
                    end
                    state<=8;
                end
                8:begin
                    wet_product_l<=$signed(wet_l)*$signed({1'b0,gain});
                    wet_product_r<=$signed(wet_r)*$signed({1'b0,gain});state<=9;
                end
                9:begin
                    mixed_l<=$signed({{32{dry_l[31]}},dry_l})+($signed(wet_product_l)>>>15);
                    mixed_r<=$signed({{32{dry_r[31]}},dry_r})+($signed(wet_product_r)>>>15);state<=10;
                end
                10:begin
                    left_o<=sat31(mixed_l);right_o<=sat31(mixed_r);valid_o<=1;
                    clip_o<=internal_clip || mixed_l>64'sd2147483647 || mixed_l< -64'sd2147483648 ||
                                            mixed_r>64'sd2147483647 || mixed_r< -64'sd2147483648;
                    for(i=0;i<4;i=i+1) pointer[i]<=pointer[i]==delay_length(i)-1 ? 12'd0 : pointer[i]+1'b1;
                    early_pointer<=early_pointer+1'b1;
                    if(frames<12'd2131)frames<=frames+1'b1;
                    state<=0;
                end
                default:state<=0;
            endcase
        end
    end
endmodule
