// 50-MHz TF scope transport. Receives coherent accepted audio-domain state;
// song-menu launches work without a Basic Pitch model. Reader/DDR stay shared.
module scope_tf_transport (
    input wire clk_i,rst_ni,control_valid_i,
    input wire [31:0] control_i,
    input wire song_valid_i,
    input wire [3:0] song_track_i,
    input wire playlist_ready_i,card_lost_i,
    input wire [4:0] track_count_i,
    output wire mode_o,run_o,
    output reg [3:0] track_o,
    output reg restart_o,cancel_analysis_o,error_o
);
    reg mode_q,run_q,wait_card;
    reg [15:0] epoch;
    wire mode_request=control_i[12];
    wire run_request=control_i[13];
    wire [15:0] epoch_delta=control_i[31:16]-epoch;
    wire new_epoch=epoch_delta!=0;
    wire relative_action=control_i[7:6]==1 || control_i[7:6]==2;
    wire [1:0] action=control_i[7:6];
    reg [4:0] requested_track;
    always @* begin
        case(action)
            1: requested_track={1'b0,track_o}+5'd1;
            2: requested_track=track_o==0 ? 5'd31 : {1'b0,track_o}-5'd1;
            default: requested_track={1'b0,control_i[11:8]};
        endcase
    end
    assign mode_o=mode_q;
    assign run_o=mode_q && run_q && !wait_card && !error_o;
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            mode_q<=0;run_q<=0;epoch<=0;track_o<=0;wait_card<=0;
            restart_o<=0;cancel_analysis_o<=0;error_o<=0;
        end else begin
            restart_o<=0;cancel_analysis_o<=0;
            if(control_valid_i) begin
                epoch<=control_i[31:16];mode_q<=mode_request;run_q<=run_request;
                if(mode_request!=mode_q) cancel_analysis_o<=1;
                if(!mode_request) begin wait_card<=0;error_o<=0;end
                else if(new_epoch && mode_q && relative_action && epoch_delta!=1) begin
                    // Held-state CDC can coalesce rapid CPU commands. Never
                    // silently apply only the last relative step. Absolute
                    // select or restart explicitly rearms after this error.
                    error_o<=1;wait_card<=0;
                end else if(new_epoch) begin
                    if(!mode_q || action==0) track_o<=control_i[11:8];
                    else if((action==1 || action==2) && requested_track<16 && requested_track<track_count_i) track_o<=requested_track[3:0];
                    if(action==3) begin
                        // Restart means the currently selected menu track,
                        // not a stale absolute index from the audio domain.
                        error_o<=0;restart_o<=playlist_ready_i && track_o<track_count_i;
                        wait_card<=!playlist_ready_i;
                        if(playlist_ready_i && track_o>=track_count_i) error_o<=1;
                    end else if(!playlist_ready_i) begin
                        wait_card<=1;error_o<=0;
                    end else if(requested_track>=16 || requested_track>=track_count_i) begin
                        error_o<=1;wait_card<=0;
                    end else begin restart_o<=1;wait_card<=0;error_o<=0;end
                end
            end
            if(mode_q && song_valid_i) begin
                if(song_track_i<track_count_i && playlist_ready_i) begin
                    track_o<=song_track_i;restart_o<=1;error_o<=0;wait_card<=0;
                end else error_o<=1;
            end
            if(mode_q && card_lost_i) begin wait_card<=1;error_o<=0;end
            else if(mode_q && wait_card && playlist_ready_i) begin
                wait_card<=0;
                if(track_o<track_count_i) begin restart_o<=1;error_o<=0;end
                else error_o<=1;
            end
        end
    end
endmodule
