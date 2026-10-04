module push2_lights(input wire clk,rst,input wire [63:0] held,input wire [31:0] control,
    input wire [31:0] score_mask,input wire score_running,record_enabled,
    input wire guide_mode,input wire [63:0] guide_mask,
    output reg valid,input wire ready,output reg [1:0] kind,
    output reg [6:0] index,output reg [7:0] value);
    reg [2:0] startup;
    reg [6:0] scan,selected;
    reg [6:0] cached[0:84];reg [84:0] known;
    reg [6:0] color;
    reg guide_mode_q,clear_guide;
    reg [63:0] guide_mask_q;
    wire guide_changed=guide_mode && (!guide_mode_q || guide_mask!=guide_mask_q);
    always @* begin
        color=0;
        if(guide_mode) begin
            if(!clear_guide && !guide_changed && scan<64 && guide_mask[scan]) color=126;
        end else if(scan<64)begin
            case(scan[2:0])
                0:color=126;1:color=15;2:color=125;3:color=22;
                4:color=25;5:color=3;6:color=8;default:color=127;
            endcase
            if(score_running && scan<32 && score_mask[scan])color=126;
            if(held[scan])color=122;
        end else if(scan<67)color=control[4:3]==scan-64?126:1;
        else if(scan<72)color=control[9:7]==scan-67?15:1;
        else if(scan<75)color=control[scan-72]?126:1;
        else if(scan<79)color=control[6:5]==scan-75?15:1;
        else if(scan==79)color=3;
        else if(scan==80)color=(|control[2:0]) ? 126 : 1;
        else if(scan==81)color=score_running?126:1;
        else if(scan==82)color=record_enabled?5:1;
        else color=3;
    end
    always @(posedge clk or posedge rst)begin
        if(rst)begin
            startup<=0;scan<=0;selected<=0;known<=0;valid<=0;kind<=0;index<=0;value<=0;
            guide_mode_q<=0;guide_mask_q<=0;clear_guide<=0;
        end else begin
        guide_mode_q<=guide_mode;guide_mask_q<=guide_mask;
        if(guide_changed)begin clear_guide<=1;scan<=0;end
        else if(!guide_mode)clear_guide<=0;
        if(valid)begin
            if(ready)begin
                valid<=0;
                if(startup<5)startup<=startup+1'b1;
                else begin cached[selected]<=value[6:0];known[selected]<=1;end
            end
        end else if(startup<5)begin
            // Select Live mode, set both brightness controls, configure the
            // touch strip, then request the documented poly-aftertouch mode.
            valid<=1;index<=startup==0?127:startup==3?126:startup==4?125:0;
            kind<=startup==0 || startup==3 || startup==4?3:startup==1?1:2;
            value<=startup==0?0:startup==1?64:startup==2?160:startup==3?104:1;
        end else begin
            if(!known[scan] || cached[scan]!=color)begin
                selected<=scan;valid<=1;value<={1'b0,color};kind<=scan<64?0:3;
                if(scan<64)index<=scan+7'd36;
                else if(scan<72)index<=scan+7'd38;
                else if(scan<79)index<=scan-7'd52;
                else case(scan)
                    79:index<=27;80:index<=28;81:index<=85;82:index<=86;
                    83:index<=62;default:index<=63;
                endcase
            end
            if(!guide_changed)begin
                scan<=scan==84?0:scan+1'b1;
                if(clear_guide && scan==84)clear_guide<=0;
            end
        end
        end
    end
endmodule
