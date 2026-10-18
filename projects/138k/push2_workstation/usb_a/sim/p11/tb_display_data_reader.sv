`timescale 1ns/1ps
module tb_display_data_reader;
    import display_data_layout_pkg::*;
    reg clk=0,rst_n=0,start=0;
    always #5 clk=~clk;
    wire busy,done,valid,fault,req_valid;
    reg req_ready=0,rsp_valid=0;
    wire [28:0]req_addr;
    reg [255:0]rsp_data=0,pending_data=0;
    reg render_read_enable=0;
    reg [8:0]render_wave_addr=0,render_spectrum_column=0;
    reg [15:0]render_image_addr=0;
    wire [31:0]render_wave_data,render_analysis_sequence,render_analysis_skipped,render_stereo_peaks,render_frame_sequence;
    wire render_image_hit,render_analysis_valid;
    wire [7:0]render_spectrum_left,render_spectrum_right;
    wire [2:0]render_image_gain;
    wire [255:0]render_meta;
    integer cycles=0,delay_count=0,header_reads=0,accepted_reads=0;
    reg pending=0,corrupt_final_once=1,saw_fault=0;

    function automatic [255:0] packet(input [28:0]address);
        control_record_t control;
        block_descriptor_t block;
        reg [255:0]value;
        integer beat,lane,kind;
        begin
            control='0;
            control.magic=DISPLAY_MAGIC;
            control.version_bank_count={8'd4,7'd0,1'b1,VERSION_MAJOR,VERSION_MINOR};
            control.frame_sequence=7;control.commit_sequence=14;
            control.descriptor_base_word={3'd0,DESC_BANK1_WORD};control.flags=32'hf;
            control.waveform_skipped=9;control.analysis_skipped=11;
            value=0;
            if(address==DISPLAY_CONTROL_WORD || address==BANK1_HEADER_WORD)value=control;
            else if(address>=DESC_BANK1_WORD && address<DESC_BANK1_WORD+64)begin
                beat=(address-DESC_BANK1_WORD)/8;kind=beat/2;block='0;
                block.magic=BLOCK_MAGIC;
                block.version_type_format={8'(kind+1),8'(kind+1),VERSION_MAJOR,VERSION_MINOR};
                block.frame_sequence=7;
                block.source_sequence=kind==0 ? 100 : kind==3 ? 7 : 200;
                block.sample_rate_hz=kind==3 ? 0 : SAMPLE_RATE_HZ;
                block.flags=1;block.skipped_samples=kind==0 ? 9 : kind==3 ? 0 : 11;
                block.bank_header_word={3'd0,BANK1_HEADER_WORD};
                case(kind)
                    0:begin block.valid_length=512;block.payload_words=512;block.payload_base_word={3'd0,PAYLOAD_BANK1_WORD};block.window_trigger=32'h0d010200;end
                    1:begin block.valid_length=65536;block.payload_words=2048;block.payload_base_word={3'd0,PAYLOAD_BANK1_WORD+LISSAJOUS_OFFSET_WORD};block.window_trigger=32'h800;block.display_gain=5;block.aux0=32'h01000100;end
                    2:begin block.valid_length=512;block.payload_words=256;block.payload_base_word={3'd0,PAYLOAD_BANK1_WORD+SPECTRUM_OFFSET_WORD};block.window_trigger=32'h20800;block.aux0=32'h03550002;block.aux1=224;end
                    default:begin block.valid_length=16;block.payload_words=16;block.payload_base_word={3'd0,PAYLOAD_BANK1_WORD+EFFECT_META_OFFSET_WORD};end
                endcase
                value=beat[0] ? block[511:256] : block[255:0];
            end else if(address>=PAYLOAD_BANK1_WORD && address<PAYLOAD_BANK1_WORD+512)begin
                beat=(address-PAYLOAD_BANK1_WORD)/8;
                for(lane=0;lane<8;lane=lane+1)value[lane*32+:32]=32'h10000000+beat*8+lane;
            end else if(address>=PAYLOAD_BANK1_WORD+LISSAJOUS_OFFSET_WORD && address<PAYLOAD_BANK1_WORD+SPECTRUM_OFFSET_WORD)begin
                beat=(address-PAYLOAD_BANK1_WORD-LISSAJOUS_OFFSET_WORD)/8;
                for(lane=0;lane<256;lane=lane+1)value[lane]=((beat*256+lane)%17)==3;
            end else if(address>=PAYLOAD_BANK1_WORD+SPECTRUM_OFFSET_WORD && address<PAYLOAD_BANK1_WORD+EFFECT_META_OFFSET_WORD)begin
                beat=(address-PAYLOAD_BANK1_WORD-SPECTRUM_OFFSET_WORD)/8;
                for(lane=0;lane<16;lane=lane+1)begin
                    value[lane*16+:8]=(beat*16+lane)&8'hff;
                    value[lane*16+8+:8]=~((beat*16+lane)&8'hff);
                end
            end else if(address==PAYLOAD_BANK1_WORD+EFFECT_META_OFFSET_WORD)begin
                value[31:0]=32'ha5;value[63:32]=9;value[95:64]=100;value[127:96]=32'h12345678;
                value[159:128]=32'h20;value[191:160]=32'h00009abc;value[200:192]=9'b101010111;value[255:224]=32'h44495350;
            end else if(address==PAYLOAD_BANK1_WORD+EFFECT_META_OFFSET_WORD+8)begin
                value[31:0]=200;value[63:32]=11;value[95:64]=32'h12345678;
                value[127:96]=5;value[159:128]=32'hf;value[191:160]=SAMPLE_RATE_HZ;
            end
            packet=value;
        end
    endfunction

    always @* req_ready=rst_n && !pending && cycles%5!=0;
    always @(posedge clk)begin
        cycles=cycles+1;rsp_valid<=0;
        if(fault)saw_fault<=1;
        if(req_valid && req_ready)begin
            pending<=1;delay_count<=2;pending_data=packet(req_addr);accepted_reads=accepted_reads+1;
            if(req_addr==BANK1_HEADER_WORD)begin
                if(header_reads==1 && corrupt_final_once)begin pending_data[96]=1;corrupt_final_once=0;end
                header_reads=header_reads+1;
            end
        end
        if(pending)begin
            if(delay_count==0)begin rsp_valid<=1;rsp_data<=pending_data;pending<=0;end
            else delay_count<=delay_count-1;
        end
    end

    display_data_reader dut(.clk,.rst_n,.enabled(rst_n),.start,.busy,.done,.valid,.fault,
        .req_valid,.req_ready,.req_addr,.rsp_valid,.rsp_data,
        .render_read_enable,.render_wave_addr,.render_image_addr,.render_spectrum_column,
        .render_wave_data,.render_image_hit,.render_spectrum_left,.render_spectrum_right,
        .render_meta,.render_analysis_sequence,.render_analysis_skipped,.render_stereo_peaks,
        .render_image_gain,.render_analysis_valid,.render_frame_sequence);

    initial begin
        repeat(5)@(negedge clk);rst_n=1;@(negedge clk);start=1;@(negedge clk);start=0;
        wait(done);@(negedge clk);
        if(!saw_fault || fault || !valid)$fatal(1,"reader did not reject then recover from changed final header");
        if(render_frame_sequence!=7 || render_analysis_sequence!=200 || render_analysis_skipped!=11 ||
           render_stereo_peaks!=32'h12345678 || render_image_gain!=5 || !render_analysis_valid)$fatal(1,"published metadata mismatch");
        if(render_meta[255:224]!=32'h44495350 || render_meta[95:64]!=100 || render_meta[63:32]!=9)$fatal(1,"effect metadata mismatch");
        render_wave_addr=37;render_image_addr=1023;render_spectrum_column=37;render_read_enable=1;
        @(posedge clk);#1;
        if(render_wave_data!=32'h10000025 || !render_image_hit)$fatal(1,"waveform/bitmap cache read mismatch");
        @(posedge clk);#1;
        if(render_spectrum_left!=8'd37 || render_spectrum_right!=8'hda)$fatal(1,"spectrum cache read mismatch");
        render_image_addr=1024;@(posedge clk);#1;if(render_image_hit)$fatal(1,"bitmap zero read mismatch");
        if(accepted_reads!=730)$fatal(1,"expected one discarded and one committed 365-read snapshot, got %0d",accepted_reads);
        $display("PASS display reader: descriptors/lengths/version, delayed DDR responses, final-header retry, coherent waveform/image/spectrum/meta cache");
        $finish;
    end
    initial begin #2000000;$fatal(1,"reader timeout");end
endmodule
