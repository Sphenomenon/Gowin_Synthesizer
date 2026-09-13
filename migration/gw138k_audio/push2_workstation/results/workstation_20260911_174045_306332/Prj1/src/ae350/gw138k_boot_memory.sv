// Fixed-latency AHB ROM and byte-enabled 64bit AHB RAM.
// Address/control are accepted in the address phase; writes consume HWDATA
// in the following data phase. All transfers are completed without wait states.
module gw138k_boot_memory (
    input wire rom_clk,rom_reset_n,
    input wire [31:0] rom_address,
    input wire [1:0] rom_transfer,
    output reg [31:0] rom_data,
    output reg [31:0] fetch_count,last_fetch,
    input wire ram_clk,ram_reset_n,
    input wire [31:0] ram_address,
    input wire [1:0] ram_transfer,
    input wire [2:0] ram_size,
    input wire ram_write,
    input wire [63:0] ram_write_data,
    output reg [63:0] ram_read_data
);
    reg [31:0] rom [0:4095];
    reg [63:0] ram [0:1023];
    initial $readmemh("firmware/boot.mem",rom);
    always @(posedge rom_clk) begin
        if(rom_transfer[1]) rom_data<=rom_address[31:14]==18'h20000 ? rom[rom_address[13:2]] : 32'h00100073;
    end
    always @(posedge rom_clk or negedge rom_reset_n)
        if(!rom_reset_n) begin fetch_count<=0;last_fetch<=0;end
        else if(rom_transfer[1]) begin fetch_count<=fetch_count+1'b1;last_fetch<=rom_address;end
    reg write_pending;
    reg [9:0] write_index;
    reg [7:0] write_mask;
    integer lane;
    always @(posedge ram_clk) begin
        // A read address can overlap the preceding write's data phase.
        // Bypass only the lanes being written, retaining all untouched bytes.
        if(ram_transfer[1]) for(lane=0;lane<8;lane=lane+1)
            ram_read_data[lane*8+:8]<=write_pending && write_index==ram_address[12:3] && write_mask[lane]
                ? ram_write_data[lane*8+:8] : ram[ram_address[12:3]][lane*8+:8];
        if(write_pending) for(lane=0;lane<8;lane=lane+1)
            if(write_mask[lane]) ram[write_index][lane*8+:8]<=ram_write_data[lane*8+:8];
    end
    always @(posedge ram_clk or negedge ram_reset_n) begin
        if(!ram_reset_n) begin write_pending<=0;write_index<=0;write_mask<=0;end
        else begin
            write_pending<=ram_transfer[1] && ram_write && ram_address[31:13]==0 && ram_size<=3;
            write_index<=ram_address[12:3];
            case(ram_size)
                0:write_mask<=8'h01<<ram_address[2:0];
                1:write_mask<=8'h03<<ram_address[2:0];
                2:write_mask<=8'h0f<<ram_address[2:0];
                3:write_mask<=8'hff;
                default:write_mask<=0;
            endcase
        end
    end
endmodule
