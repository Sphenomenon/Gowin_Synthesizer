`timescale 1ns/1ps
`default_nettype none
// Adapted from workstation_tf_sd_sector_wire_tb.sv; sparse constructed FAT disk.
// SPI mode-0 card model. The only DUT connections are its public SPI and
// sector ports: no forced card state, session stub or hierarchical deposits.
module workstation_tf_file_wire_card #(
    parameter integer CARD_KIND=0 // 0=SDHCv2, 1=SDv2 byte addressing, 2=SDv1
) (
    input wire ssn,sck,mosi,
    output reg miso,
    input integer token_delay_bytes,
    input wire hold_init,
    input wire [31:0] fault_lba,
    input integer fault_kind,
    input wire suppress_token,command_error,suppress_r1,
    output integer cmd17_count,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,
    output integer high_clocks,
    output reg [31:0] last_argument
);
    integer bit_count,command_bytes,queue_head,queue_tail,phase,remaining,index;
    reg [7:0] rx_byte,tx_byte,queue[0:31];
    reg [47:0] command_word;
    reg idle_card;
    integer tx_kind,tx_index;
    reg [31:0] lbas[0:511];
    reg [7:0] image[0:262143];
    reg [2047:0] image_path,lba_path;
    integer image_i,current_slot,current_fault;
    function automatic [7:0] pattern(input [31:0] argument,input integer offset);
        pattern=image[current_slot*512+offset];
    endfunction
    task automatic enqueue(input [7:0] value);
        begin queue[queue_tail]=value; queue_tail=queue_tail+1; end
    endtask
    task automatic receive_byte(input [7:0] value);
        reg [5:0] command;
        begin
            if(command_bytes==0) begin
                if(value[7:6]==2'b01) begin command_word={40'd0,value}; command_bytes=1; end
            end else begin
                command_word={command_word[39:0],value};
                if(command_bytes==5) begin
                    command_bytes=0;
                    command=command_word[45:40];
                    // Response queue is empty before each command, including
                    // CMD55 + ACMD41 under the same asserted chip select.
                    if(queue_head!=queue_tail) $fatal(1,"card response overlap");
                    queue_head=0; queue_tail=0;
                    if(!hold_init) case(command)
                        0: begin idle_card=1; enqueue(8'h01); end
                        1: begin idle_card=0; enqueue(8'h00); end
                        8: if(CARD_KIND==2) enqueue(8'h05);
                           else begin enqueue(8'h01); enqueue(0); enqueue(0); enqueue(1); enqueue(8'haa); end
                        55: enqueue(idle_card ? 8'h01 : 8'h00);
                        41: begin idle_card=0; enqueue(8'h00); end
                        58: begin enqueue(0); enqueue(CARD_KIND==0 ? 8'hc0 : 8'h80); enqueue(0); enqueue(0); enqueue(0); end
                        16: begin
                            if(command_word[39:8]!=512) $fatal(1,"CMD16 block size");
                            enqueue(0);
                        end
                        17: begin
                            cmd17_count=cmd17_count+1;
                            last_argument=command_word[39:8];
                            current_slot=-1;
                            for(image_i=0;image_i<512;image_i=image_i+1)
                                if(lbas[image_i]==last_argument) current_slot=image_i;
                            if(current_slot<0) $fatal(1,"read outside constructed disk LBA=%0d",last_argument);
                            current_fault=(last_argument==fault_lba) ? fault_kind : 0;
                            if(!suppress_r1 && current_fault!=3) enqueue((command_error || current_fault==2) ? 8'h04 : 8'h00);
                            remaining=token_delay_bytes; index=0; phase=1;
                        end
                        default: $fatal(1,"unexpected SPI command %0d",command);
                    endcase
                end else command_bytes=command_bytes+1;
            end
        end
    endtask
    task automatic next_byte;
        begin
            tx_byte=8'hff; tx_kind=0; tx_index=0;
            if(queue_head<queue_tail) begin tx_byte=queue[queue_head]; queue_head=queue_head+1; end
            else case(phase)
                1: if(!suppress_token && !command_error && current_fault!=1 && current_fault!=2) begin
                    if(remaining>0) remaining=remaining-1;
                    else begin tx_byte=8'hfe; phase=2; end
                end
                2: begin
                    tx_byte=pattern(last_argument,index); tx_kind=1; tx_index=index;
                    if(index==511) begin phase=3; index=0; end
                    else index=index+1;
                end
                3: begin
                    tx_byte=(index==0) ? 8'ha5 : 8'h5a; tx_kind=2;
                    if(index==1) begin phase=4; index=0; end else index=1;
                end
                4: tx_kind=3;
                default: begin end
            endcase
        end
    endtask
    initial begin
        if(!$value$plusargs("IMAGE=%s",image_path) || !$value$plusargs("LBAS=%s",lba_path)) $fatal(1,"missing sparse disk image");
        $readmemh(image_path,image);$readmemh(lba_path,lbas);
        current_slot=0;current_fault=0;
        miso=1; bit_count=0; command_bytes=0; queue_head=0; queue_tail=0;
        phase=0; remaining=0; index=0; rx_byte=0; tx_byte=8'hff;
        command_word=0; idle_card=1; tx_kind=0; tx_index=0;
        cmd17_count=0; payload_bytes=0; crc_bytes=0; post_crc_bytes=0;
        cs_releases=0; high_clocks=0; last_argument=0;
    end
    always @(posedge ssn) begin
        if(phase!=0) cs_releases=cs_releases+1;
        bit_count=0; command_bytes=0; queue_head=0; queue_tail=0;
        phase=0; tx_kind=0; miso=1;
    end
    always @(negedge sck) if(!ssn) begin
        if(bit_count==0) next_byte();
        miso=tx_byte[7-bit_count];
    end
    always @(posedge sck) begin
        if(ssn) high_clocks=high_clocks+1;
        else begin
            rx_byte={rx_byte[6:0],mosi};
            if(bit_count==7) begin
                bit_count=0;
                if(tx_kind==1) payload_bytes=payload_bytes+1;
                if(tx_kind==2) crc_bytes=crc_bytes+1;
                if(tx_kind==3) post_crc_bytes=post_crc_bytes+1;
                receive_byte(rx_byte);
            end else bit_count=bit_count+1;
        end
    end
endmodule

`default_nettype wire
