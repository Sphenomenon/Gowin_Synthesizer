`timescale 1ns/1ps
`default_nettype none
// Isolated cache probe AHB owner. 8KiB storage; 0x4000..4fff is an explicit
// uncached backing alias of 0x1000..1fff. No workstation/DDR address allocation.
module workstation_ae350_cache_probe_memory(
    input wire clk,reset_n,
    input wire [31:0] address,
    input wire [1:0] transfer,
    input wire [2:0] size,burst,
    input wire [3:0] protection,
    input wire write,
    input wire [63:0] write_data,
    output reg [63:0] read_data,
    output wire ready,response,
    output reg unmapped_seen=0
);
    reg [63:0] ram[0:1023];
    reg fault=0,error_second=0,pending_write=0;
    reg [9:0] pending_index=0;
    reg [7:0] pending_mask=0;
    reg active=0;
    reg [31:0] expected_address=0,burst_origin=0;
    reg [2:0] accepted_size=0,accepted_burst=0;
    reg [4:0] left=0;
    // HPROT is carried by the real hard-IP port; it does not create PMA/cache
    // semantics in this RAM. The probe's cache behavior must be measured at CPU.
    wire unused_protection=^protection;
    wire mapped=(address[31:13]==0)||(address[31:12]==20'h00004);
    wire aligned=size<=3 && ((address&((32'd1<<size)-1))==0);
    wire sequence_error=transfer==3 && (!active || address!=expected_address ||
        size!=accepted_size || burst!=accepted_burst || address[31:10]!=burst_origin[31:10]);
    wire invalid=!mapped || !aligned || sequence_error;
    wire [9:0] index=address[31:12]==20'h00004 ? {1'b1,address[11:3]}:address[12:3];
    wire [7:0] mask=size==0 ? 8'h01<<address[2:0]:size==1 ? 8'h03<<address[2:0]:
        size==2 ? 8'h0f<<address[2:0]:8'hff;
    assign ready=!fault || error_second;
    assign response=fault;
    function automatic [4:0] beats(input [2:0] kind);
        case(kind)
            2,3:beats=4;4,5:beats=8;6,7:beats=16;default:beats=1;
        endcase
    endfunction
    function automatic [31:0] following(input [31:0] current,input [2:0] width,kind);
        reg [31:0] span,low;begin
            span=({27'd0,beats(kind)}<<width)-1;
            low=(current+(32'd1<<width));
            following=(kind==2 || kind==4 || kind==6) ? (current&~span)|(low&span):low;
        end
    endfunction
    integer lane;
    always @(posedge clk)begin
        if(reset_n && pending_write)for(lane=0;lane<8;lane=lane+1)
            if(pending_mask[lane])ram[pending_index][lane*8+:8]<=write_data[lane*8+:8];
        if(reset_n && ready && transfer[1] && !invalid)for(lane=0;lane<8;lane=lane+1)
            read_data[lane*8+:8]<=pending_write && pending_index==index && pending_mask[lane]
                ? write_data[lane*8+:8]:ram[index][lane*8+:8];
    end
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin
            fault<=0;error_second<=0;pending_write<=0;pending_index<=0;pending_mask<=0;
            active<=0;expected_address<=0;burst_origin<=0;accepted_size<=0;accepted_burst<=0;left<=0;
            unmapped_seen<=0;
        end else begin
            pending_write<=0;
            if(!ready)error_second<=1;
            else begin
                fault<=transfer[1] && invalid;error_second<=0;
                if(transfer[1] && invalid)begin active<=0;unmapped_seen<=1;end
                else if(transfer[1])begin
                    pending_write<=write;pending_index<=index;pending_mask<=mask;
                    expected_address<=following(address,size,burst);
                    if(transfer==2)begin
                        accepted_size<=size;accepted_burst<=burst;burst_origin<=address;
                        left<=beats(burst)-1'b1;active<=burst!=0;
                    end else if(burst!=1)begin
                        left<=left-1'b1;if(left==1)active<=0;
                    end
                end else if(transfer==0)active<=0; // BUSY retains the burst.
            end
        end
    end
endmodule
`default_nettype wire
