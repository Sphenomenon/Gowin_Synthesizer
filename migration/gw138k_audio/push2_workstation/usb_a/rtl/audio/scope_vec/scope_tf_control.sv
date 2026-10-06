// Accepted audio-domain control events. No PCM storage or playback timer here.
// Word: [31:16] restart epoch, [15] sticky invalid control, [14] manual ownership latched,
//       [13] run, [12] TF scope mode, [11:8] zero-based root track, [7:6] track action (0 absolute, 1 next, 2 previous, 3 restart), [5:0] reserved.
module scope_tf_control (
    input wire clk_i,rst_ni,event_valid_i,
    input wire [6:0] cc_i,value_i,
    input wire live_enable_i,voices_idle_i,
    output wire [31:0] control_o
);
    reg [15:0] epoch;
    reg mode,run,error,manual;
    reg [3:0] track;
    reg [1:0] track_action;
    wire mode_target=value_i==64 ? !mode : value_i==127;
    assign control_o={epoch,error,manual,run,mode,track,track_action,6'd0};
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin epoch<=0;mode<=0;run<=0;error<=0;manual<=0;track<=0;track_action<=0;end
        else if(event_valid_i) begin
            case(cc_i)
                104: if((value_i==0 || value_i==64 || value_i==127) &&
                        (!mode_target || mode || voices_idle_i)) begin
                    mode<=mode_target;track_action<=0;
                    if(mode_target) manual<=1;
                    if(mode_target && !mode) begin run<=1;epoch<=epoch+1'b1;end
                    else if(!mode_target) run<=0;
                end else error<=1;
                105: if(mode && (value_i==0 || value_i==64 || value_i==127)) begin
                    if(value_i==127) begin run<=1;epoch<=epoch+1'b1;track_action<=3;end
                    else run<=value_i==64 ? !run : 1'b0;
                end else error<=1;
                106: if(value_i<16) begin
                    track<=value_i[3:0];track_action<=0;
                    if(mode) begin epoch<=epoch+1'b1;run<=1;end
                end else error<=1;
                108: if(mode && (value_i==0 || value_i==127)) begin
                    // Directory-aware transport owns relative bounds; this
                    // index may differ after a song-menu selection.
                    track_action<=value_i==127 ? 2'd1 : 2'd2;
                    epoch<=epoch+1'b1;run<=1;
                end else error<=1;
                // Live geometry and TF playback have distinct mode ownership.
                90: if(voices_idle_i && (value_i==127 || (value_i==64 && !live_enable_i))) begin mode<=0;run<=0;end
                120,123: run<=0;
                default: begin end
            endcase
        end
    end
endmodule
