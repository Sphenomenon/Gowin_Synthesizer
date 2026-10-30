// Maintained AE350 PL boot storage. Selected explicitly by a new source policy.
// The AHB ABI and 8 KiB scratch RAM retain the locked reference's semantics;
// ROM capacity is a parameter bound to the firmware image by the preparer.
module gw138k_boot_memory #(
    parameter integer ROM_BYTES = 65536,
    parameter ROM_FILE = "firmware/boot.mem"
) (
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
    localparam integer ROM_WORDS = ROM_BYTES / 4;
    localparam integer ROM_INDEX_BITS = $clog2(ROM_WORDS);
    localparam [31:0] ROM_MASK = ~(ROM_BYTES - 1);
    reg [31:0] rom [0:ROM_WORDS-1];
    reg [63:0] ram [0:1023];
    initial begin
        if (ROM_BYTES != 16384 && ROM_BYTES != 65536)
            $error("AE350 ROM capacity must be explicitly 16 or 64 KiB");
        $readmemh(ROM_FILE,rom);
    end
    always @(posedge rom_clk) begin
        if(rom_transfer[1])
            rom_data <= (rom_address & ROM_MASK) == 32'h80000000
                ? rom[rom_address[ROM_INDEX_BITS+1:2]] : 32'h00100073;
    end
    always @(posedge rom_clk or negedge rom_reset_n)
        if(!rom_reset_n) begin fetch_count<=0;last_fetch<=0;end
        else if(rom_transfer[1]) begin fetch_count<=fetch_count+1'b1;last_fetch<=rom_address;end
    reg write_pending;
    reg [9:0] write_index;
    reg [7:0] write_mask;
    integer lane;
    always @(posedge ram_clk) begin
        if(ram_transfer[1]) for(lane=0;lane<8;lane=lane+1)
            ram_read_data[lane*8+:8] <= write_pending && write_index==ram_address[12:3] && write_mask[lane]
                ? ram_write_data[lane*8+:8] : ram[ram_address[12:3]][lane*8+:8];
        if(write_pending) for(lane=0;lane<8;lane=lane+1)
            if(write_mask[lane]) ram[write_index][lane*8+:8] <= ram_write_data[lane*8+:8];
    end
    always @(posedge ram_clk or negedge ram_reset_n) begin
        if(!ram_reset_n) begin write_pending<=0;write_index<=0;write_mask<=0;end
        else begin
            write_pending <= ram_transfer[1] && ram_write && ram_address[31:13]==0 && ram_size<=3;
            write_index <= ram_address[12:3];
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
