`timescale 1ns/1ps
// Independent native runtime Reverb. Versioned dual-rate room bank preserves
// physical early/FDN delays and matched damping pole. Storage keeps original
//48k capacities; config/history clear logical state while preserving wet gain.
// This component is not selected by any profile, build or top.
module workstation_runtime_spatial_reverb (
    input logic clk_i,rst_ni,clear_i,valid_i,enabled_i,
    input logic signed [31:0] left_i,right_i,
    output wire ready_o,active_o,
    output logic valid_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o,
    input logic config_valid_i,rate_44100_i,history_clear_i,
    output logic config_ready_o,config_applied_o,history_ready_o,history_done_o,
    output logic quiescent_o,applied_rate_44100_o
);
    import audio_math_pkg::*;
    `include "rtl/audio/runtime_spatial_room_preset.svh"
    function automatic integer capacity_length(input integer lane);
        case(lane) 0:capacity_length=1429;1:capacity_length=1789;
                   2:capacity_length=1999;default:capacity_length=2131;endcase
    endfunction
    function automatic integer delay_length(input integer lane);
        delay_length=32'(runtime_room_fdn_length(applied_rate_44100_o,2'(lane)));
    endfunction
    function automatic logic signed [31:0] rate_damping(
        input logic signed [31:0] previous_value,tail_value,input logic rate44);
        logic signed [63:0] previous_product,tail_product,weighted;
        begin
            if(rate44)begin
                previous_product=previous_value*RUNTIME_ROOM_ALPHA_44;
                tail_product=tail_value*RUNTIME_ROOM_INPUT_44;
                weighted=previous_product+tail_product;
                rate_damping=sat31(weighted>>>31);
            end else rate_damping=sat31(($signed({{32{previous_value[31]}},previous_value})+
                $signed({{32{tail_value[31]}},tail_value}))>>>1);
        end
    endfunction
    function automatic [15:0] wet_slew(input [15:0] value,target,delta);
        logic [15:0] upper,lower;
        begin
            upper=value>16'hffff-delta ? 16'hffff : value+delta;
            lower=value<delta ? 16'd0 : value-delta;
            if(target>upper)wet_slew=upper;
            else if(target<lower)wet_slew=lower;
            else wet_slew=target;
        end
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
    wire config_accept=config_valid_i && config_ready_o;
    wire history_accept=history_clear_i && history_ready_o;
    wire local_history_clear=clear_i || config_accept || history_accept;
    for(genvar lane=0;lane<4;lane=lane+1) begin : g_fdn
        workstation_sdp_banked #(.WORDS(capacity_length(lane)),.ADDR_WIDTH(12)) ram(
            .rst_ni(rst_ni),.clear_i(local_history_clear),
            .write_clk_i(clk_i),.write_enable_i(rst_ni && !local_history_clear && state==10),
            .write_addr_i(pointer[lane]),.write_data_i(line_write[lane]),
            .read_clk_i(clk_i),.read_request_i(state==0 && valid_i && ready_o),
            .read_addr_i(pointer[lane]),.read_valid_o(line_valid[lane]),.read_data_o(line_data[lane]));
    end
    workstation_sdp_banked #(.WORDS(2048),.ADDR_WIDTH(11)) early_ram(
        .rst_ni(rst_ni),.clear_i(local_history_clear),
            .write_clk_i(clk_i),.write_enable_i(rst_ni && !local_history_clear && state==10),
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
    logic [7:0] gain_remainder;
    logic ram_write_tail;
    wire [7:0] gain_fraction_sum=gain_remainder+8'd47;
    wire [15:0] gain_delta=applied_rate_44100_o ?
        16'd139+{15'd0,gain_fraction_sum>=8'd147} : 16'd128;
    assign quiescent_o=state==0 && !valid_o && !ram_write_tail && !clear_i;
    assign config_ready_o=quiescent_o && !valid_i;
    assign history_ready_o=config_ready_o && !config_valid_i;
    assign ready_o=state==0 && !local_history_clear;
    always_ff @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            applied_rate_44100_o<=0;config_applied_o<=0;history_done_o<=0;
            gain_remainder<=0;ram_write_tail<=0;
        end else begin
            config_applied_o<=config_accept;history_done_o<=config_accept || history_accept;
            ram_write_tail<=!local_history_clear && state==10;
            if(config_accept)applied_rate_44100_o<=rate_44100_i;
            if(clear_i)gain_remainder<=0;
            else if(state==0 && valid_i && ready_o && applied_rate_44100_o)
                gain_remainder<=gain_fraction_sum>=8'd147 ? gain_fraction_sum-8'd147 : gain_fraction_sum;
        end
    end
    assign active_o=enabled_i || gain!=0;
    // These registers are private to one frame. Configuration/history are
    // accepted only in state 0; PANIC may finish a speculative scratch write
    // on its cancellation edge, while the control block immediately returns
    // to state 0, suppresses output and clears the delay history. Every next
    // frame overwrites sums (3), h/tail mix (4), products/loop gain (5),
    // feedback (6), line write (7), wet products (8) and mix (9) before use.
    // Keep this wide datapath's enables local to its registered state.
    always_ff @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            early_product<=0;wet_product_l<=0;wet_product_r<=0;mixed_l<=0;mixed_r<=0;
            sum01<=0;diff01<=0;sum23<=0;diff23<=0;
            tail_sum01<=0;tail_diff01<=0;tail_sum23<=0;tail_diff23<=0;tail_mix_l<=0;tail_mix_r<=0;
            for(integer lane=0;lane<4;lane=lane+1)begin
                line_write[lane]<=0;h[lane]<=0;loop_gain[lane]<=0;feedback[lane]<=0;
            end
        end else case(state)
            3:if(tap==0)begin
                tail_sum01<=$signed({tail[0][31],tail[0]})+$signed({tail[1][31],tail[1]});
                tail_diff01<=$signed({tail[0][31],tail[0]})-$signed({tail[1][31],tail[1]});
                tail_sum23<=$signed({tail[2][31],tail[2]})+$signed({tail[3][31],tail[3]});
                tail_diff23<=$signed({tail[2][31],tail[2]})-$signed({tail[3][31],tail[3]});
                sum01<=$signed({damping[0][31],damping[0]})+$signed({damping[1][31],damping[1]});
                diff01<=$signed({damping[0][31],damping[0]})-$signed({damping[1][31],damping[1]});
                sum23<=$signed({damping[2][31],damping[2]})+$signed({damping[3][31],damping[3]});
                diff23<=$signed({damping[2][31],damping[2]})-$signed({damping[3][31],damping[3]});
            end
            4:if(tap==0)begin
                tail_mix_l<=32'((ts0-ts2)>>>2);tail_mix_r<=32'((ts1+ts3)>>>2);
                h[0]<=(p0+p2)>>>1;h[1]<=(p1+p3)>>>1;
                h[2]<=(p0-p2)>>>1;h[3]<=(p1-p3)>>>1;
            end
            5:if(early_valid)begin
                if(tap==0)for(integer lane=0;lane<4;lane=lane+1)loop_gain[lane]<=h[lane]-(h[lane]>>>3);
                early_product<=(frames>=runtime_room_early_delay(applied_rate_44100_o,tap) ? $signed(early_data) : 32'sd0)*$signed({1'b0,runtime_room_early_gain(applied_rate_44100_o,tap)});
            end
            6:if(tap==0)for(integer lane=0;lane<4;lane=lane+1)feedback[lane]<=(mono>>>3)+loop_gain[lane];
            7:for(integer lane=0;lane<4;lane=lane+1)line_write[lane]<=sat31(feedback[lane]);
            8:begin
                wet_product_l<=$signed(wet_l)*$signed({1'b0,gain});
                wet_product_r<=$signed(wet_r)*$signed({1'b0,gain});
            end
            9:begin
                mixed_l<=$signed({{32{dry_l[31]}},dry_l})+($signed(wet_product_l)>>>15);
                mixed_r<=$signed({{32{dry_r[31]}},dry_r})+($signed(wet_product_r)>>>15);
            end
            default:begin end
        endcase
    end
    integer i;
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            state<=0;tap<=0;frames<=0;gain<=0;early_pointer<=0;early_address<=0;
            dry_l<=0;dry_r<=0;early_l<=0;early_r<=0;
            left_o<=0;right_o<=0;valid_o<=0;clip_o<=0;internal_clip<=0;
            for(i=0;i<4;i=i+1) begin
                pointer[i]<=0;tail[i]<=0;damping[i]<=0;
            end
        end else begin
            valid_o<=0;clip_o<=0;
            if(local_history_clear) begin
                state<=0;tap<=0;frames<=0;if(clear_i)gain<=0;early_pointer<=0;early_address<=0;
                early_l<=0;early_r<=0;internal_clip<=0;
                for(i=0;i<4;i=i+1) begin pointer[i]<=0;tail[i]<=0;damping[i]<=0;end
            end else case(state)
                0: if(valid_i && ready_o) begin
                    dry_l<=left_i;dry_r<=right_i;early_l<=0;early_r<=0;tap<=0;
                    gain<=wet_slew(gain,enabled_i ? 16'd8192 : 16'd0,gain_delta);
                    internal_clip<=0;state<=1;
                end
                1:state<=2;
                2:if(&line_valid)begin
                    for(i=0;i<4;i=i+1) begin
                        tail[i]<=frames>=delay_length(i) ? $signed(line_data[i]) : 32'sd0;
                        damping[i]<=rate_damping(damping[i],
                            frames>=delay_length(i) ? $signed(line_data[i]) : 32'sd0,applied_rate_44100_o);
                    end
                    state<=3;
                end
                // Hide the feedback pipeline behind the early-reflection RAM
                // reads. Every operation keeps the original signed precision.
                3:begin
                    early_address<=early_pointer-11'(runtime_room_early_delay(applied_rate_44100_o,tap));state<=4;
                end
                4:begin
                    state<=5;
                end
                5:if(early_valid)begin
                    state<=6;
                end
                6:begin
                    if(tap[0]) early_r<=early_r+($signed(early_product)>>>15);
                    else early_l<=early_l+($signed(early_product)>>>15);
                    if(tap==11) state<=7;else begin tap<=tap+1'b1;state<=3;end
                end
                7:begin
                    for(i=0;i<4;i=i+1) begin
                        if(feedback[i]>64'sd2147483647 || feedback[i]< -64'sd2147483648) internal_clip<=1;
                    end
                    state<=8;
                end
                8:begin
                    state<=9;
                end
                9:begin
                    state<=10;
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
