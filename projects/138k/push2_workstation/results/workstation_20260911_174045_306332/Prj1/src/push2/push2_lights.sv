module push2_lights(input wire clk,rst,input wire [63:0] held,input wire [31:0] control,
    output reg valid,input wire ready,output reg [1:0] kind,
    output reg [6:0] index,output reg [7:0] value);
    reg [2:0] startup;
    reg [6:0] scan,selected;
    reg [6:0] cached[0:79];reg [79:0] known;
    reg [6:0] color;
    always @* begin
        color=0;
        if(scan<64)begin
            case(scan[2:0])
                0:color=126;1:color=15;2:color=125;3:color=22;
                4:color=25;5:color=3;6:color=8;default:color=127;
            endcase
            if(held[scan])color=122;
        end else if(scan<67)color=control[4:3]==scan-64?126:1;
        else if(scan<72)color=control[9:7]==scan-67?15:1;
        else if(scan<75)color=control[scan-72]?126:1;
        else if(scan<79)color=control[6:5]==scan-75?15:1;
        else color=3;
    end
    always @(posedge clk or posedge rst)begin
        if(rst)begin startup<=0;scan<=0;selected<=0;known<=0;valid<=0;kind<=0;index<=0;value<=0;end
        else if(valid)begin
            if(ready)begin
                valid<=0;
                if(startup<4)startup<=startup+1'b1;
                else begin cached[selected]<=value[6:0];known[selected]<=1;end
            end
        end else if(startup<4)begin
            valid<=1;index<=startup==0?127:startup==3?126:0;
            kind<=startup==0 || startup==3?3:startup==1?1:2;
            value<=startup==0?0:startup==1?64:startup==2?160:104;
        end else begin
            if(!known[scan] || cached[scan]!=color)begin
                selected<=scan;valid<=1;value<={1'b0,color};kind<=scan<64?0:3;
                index<=scan<64?scan+7'd36:scan<72?scan+7'd38:scan-7'd52;
            end
            scan<=scan==79?0:scan+1'b1;
        end
    end
endmodule
