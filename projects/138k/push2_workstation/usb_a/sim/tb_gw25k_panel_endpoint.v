`timescale 1ns/1ps
// Interactive actual GW25K endpoint for the production-C host regression.
// Only the physical LCD sink is modeled; every accepted tile completes.
module tb_gw25k_panel_endpoint;
    reg clk=0;always #5 clk=~clk;
    reg reset=1,link_reset=0,rx_valid=0,tx_ready=1,settings_toggle=0;
    reg [7:0]rx_data=0;wire rx_ready,tx_valid;wire[7:0]tx_data;
    wire remote_enable,manual_settings,redraw_required;wire[15:0]protocol_errors;
    wire tile_valid;reg tile_ready=1,tile_done=0;
    wire[8:0]tile_x,tile_width;wire[7:0]tile_y,tile_height;
    reg[7:0]tile_read_addr=0;wire[15:0]tile_read_data;
    panel_display_endpoint #(.CLK_HZ(1000000)) dut(.*);
    reg[7:0]response[0:63];integer response_count=0,tile_cycles=0;
    always @(posedge clk)begin
        if(tx_valid&&tx_ready)begin
            if(response_count>=64)$fatal(1,"response overflow");
            response[response_count]=tx_data;response_count=response_count+1;
        end
        tile_done<=tile_cycles==1;
        if(tile_cycles>0)tile_cycles<=tile_cycles-1;
        if(tile_valid&&tile_ready)tile_cycles<=5;
    end
    task clocks;input integer n;integer k;
        begin for(k=0;k<n;k=k+1)@(negedge clk);end
    endtask
    task byte_in;input[7:0]value;integer guard;
        begin
            @(negedge clk);rx_data=value;rx_valid=1;guard=0;
            while(!rx_ready)begin @(negedge clk);guard=guard+1;if(guard>10000)$fatal(1,"RX stalled");end
            @(posedge clk);@(negedge clk);rx_valid=0;
        end
    endtask
    integer result,n,i,value,guard,length,manual=0;reg[7:0]command;
    initial begin
        clocks(4);reset=0;clocks(4);
        forever begin
            result=$fscanf(32'h80000000,"%s",command);
            if(result!=1)$finish;
            if(command=="Q")$finish;
            else if(command=="M")begin
                result=$fscanf(32'h80000000,"%d",value);
                if(result!=1)$fatal(1,"manual input");
                if(value!=manual)begin
                    @(negedge clk);settings_toggle=1;@(negedge clk);settings_toggle=0;clocks(2);manual=value;
                end
                $display("OK");$fflush();
            end else if(command=="X")begin
                response_count=0;result=$fscanf(32'h80000000,"%d",n);
                if(result!=1||n<16||n>528)$fatal(1,"request length");
                for(i=0;i<n;i=i+1)begin
                    result=$fscanf(32'h80000000,"%h",value);
                    if(result!=1)$fatal(1,"request byte");byte_in(value[7:0]);
                end
                guard=0;length=0;
                while(length==0||response_count<length)begin
                    clocks(1);guard=guard+1;if(guard>10000)$fatal(1,"no complete RTL response");
                    if(response_count>=16)length=16+response[12]+256*response[13];
                end
                clocks(2);if(response_count!=length)$fatal(1,"response boundary");
                for(i=0;i<length;i=i+1)$write("%02x",response[i]);
                $write("\n");$fflush();
            end else $fatal(1,"unknown driver command");
        end
    end
endmodule
