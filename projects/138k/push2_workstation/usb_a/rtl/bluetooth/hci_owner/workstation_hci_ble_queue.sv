// Two complete private BLE packet copies. CPU readers never own these slots.
module workstation_hci_ble_queue (
    input wire clk_i, reset_ni,
    input wire offer_i,
    output wire ready_o,
    input wire [3:0] type_i,
    input wire [8:0] length_i,
    output wire [8:0] source_address_o,
    input wire [7:0] source_data_i,
    output reg copy_done_o,
    output wire valid_o,
    output wire [3:0] type_o,
    output wire [8:0] length_o,
    input wire [8:0] address_i,
    output reg [7:0] data_o,
    input wire consume_i
);
    (* ram_style="block" *) reg [7:0] packet_ram [0:1023];
    reg [3:0] types [0:1];
    reg [8:0] lengths [0:1];
    reg head,tail,copying,wait_read;
    reg [1:0] count;
    reg [8:0] index;
    wire publish=copying && !wait_read && index+1'b1==lengths[tail];
    wire retire=valid_o && consume_i;
    assign ready_o=count<2 && !copying;
    assign valid_o=count!=0;
    assign type_o=types[head],length_o=lengths[head],source_address_o=index;
    always @(posedge clk_i)begin
        if(reset_ni && copying && !wait_read)packet_ram[{tail,index}]<=source_data_i;
        data_o<=packet_ram[{head,address_i}];
        copy_done_o<=0;
        if(!reset_ni)begin
            head<=0;tail<=0;copying<=0;wait_read<=1;count<=0;index<=0;
            types[0]<=0;types[1]<=0;lengths[0]<=0;lengths[1]<=0;
        end else begin
            if(offer_i && ready_o)begin
                types[tail]<=type_i;lengths[tail]<=length_i;copying<=1;index<=0;wait_read<=1;
            end
            if(copying)begin
                if(wait_read)wait_read<=0;
                else begin
                    wait_read<=1;
                    if(index+1'b1==lengths[tail])begin copying<=0;copy_done_o<=1;tail<=~tail;end
                    else index<=index+1'b1;
                end
            end
            if(retire)head<=~head;
            case({publish,retire})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:begin end
            endcase
        end
    end
endmodule
