`timescale 1ns/1ps
module tb_feedback_dashboard;
    reg clk=0, reset_n=0, enable=1;
    always #5 clk=~clk;
    reg [10:0] x=0,y=0;
    reg [31:0] sample_data=0,previous=0,peak=0,voices=0,status=0;
    reg waveform_held=0;
    wire [31:0] pixel;
    feedback_dashboard dut(.clk(clk),.reset_n(reset_n),.enable(enable),.pixel_x(x),.pixel_y(y),.wave_sample(sample_data),.wave_previous(previous),
        .waveform_held(waveform_held),
        .peak_data(peak),.active_voices(voices),.status_data(32'h0),.sequence_data(32'h0),
        .skipped_data(32'h0),.memory_status(status),.underruns(32'h0),.framecount(32'h0),.pixel_data(pixel));
    reg [7:0] reference_character=8'hff;
    reg [2:0] reference_column=0,reference_row=0;
    wire reference_ink;
    video_font_5x7 reference_font(.character(reference_character),.column(reference_column),.row(reference_row),.ink(reference_ink),.glyph());
    integer character_index,row_index,column_index,voice_index,tile_index,digit_index;
    integer tile_x,tile_y;
    reg [3:0] mask_digit;
    task at(input integer px,input integer py,input [31:0] expected);
        begin @(negedge clk); x=px;y=py; repeat(4) @(posedge clk); #1; if(pixel!==expected) $fatal(1,"pixel (%d,%d)=%h expected %h",px,py,pixel,expected); end
    endtask
    initial begin
        #12; reset_n=1;
        // Independent punctuation shapes: negative dB and decimal-time labels
        // must not silently render as unsigned integers / blank separators.
        for(character_index=0;character_index<2;character_index=character_index+1) begin
            reference_character=character_index==0 ? "-" : ".";
            for(row_index=0;row_index<8;row_index=row_index+1)
                for(column_index=0;column_index<8;column_index=column_index+1) begin
                    reference_row=row_index; reference_column=column_index; #1;
                    if(reference_ink !== (character_index==0 ?
                        (row_index==3 && column_index<5) :
                        ((row_index==5 || row_index==6) && column_index==2)))
                        $fatal(1,"missing/incorrect punctuation glyph");
                end
        end
        // Font constants must retain their first characters at native layout.
        at(64,48,32'h00e5f0fa);       // F in FPGA.
        at(1220,64,32'h00e5f0fa);    // 1 in 1920.
        at(1218,168,32'h00e5f0fa);   // O in OUTPUT PEAK.
        at(64,768,32'h00e5f0fa);     // 5 in 512 SAMPLES.
        at(644,768,32'h00e5f0fa);    // Top middle of T in TRIGGERED.
        waveform_held=1;
        at(644,768,32'h00101b2a);    // Top middle of H is empty in HOLD.
        at(640,768,32'h00e5f0fa);    // Left stem of H is visible.
        at(64,840,32'h00e5f0fa);     // Left edge of 3 in the full "32 VOICES" title.
        waveform_held=0;
        at(80,480,32'h003cdbab);     // Silence at center.
        sample_data=32'h7fffffff;previous=sample_data;
        at(80,225,32'h003cdbab);     // Positive full scale.
        sample_data=32'h80000000;previous=sample_data;
        at(80,735,32'h003cdbab);     // Negative full scale remains on plot.
        sample_data=32'h40000000;previous=32'hc0000000;
        at(80,480,32'h003cdbab);     // Connected adjacent samples.
        peak=0;at(1840,240,32'h00273b50);
        peak=32'h80000000;at(1840,240,32'h00ef6572);
        status=0;at(1800,440,32'h00f1c05a);
        status=1;at(1800,440,32'h00f1c05a);
        status=3;at(1800,440,32'h003cdbab);
        status=7;at(1800,440,32'h00ef6572);
        // Every voice must light exactly its own tile, including high bits.
        for(voice_index=0;voice_index<32;voice_index=voice_index+1) begin
            voices=32'h1 << voice_index;
            for(tile_index=0;tile_index<32;tile_index=tile_index+1) begin
                tile_x=64+64*(tile_index%16); tile_y=880+48*(tile_index/16);
                at(tile_x+4,tile_y+30,voice_index==tile_index ? 32'h00157d70 : 32'h00263a4f);
                at(tile_x+4,tile_y+1,voice_index==tile_index ? 32'h003cdbab : 32'h0049627a);
            end
        end
        voices=0;
        for(voice_index=0;voice_index<32;voice_index=voice_index+1) begin
            tile_x=64+64*(voice_index%16); tile_y=880+48*(voice_index/16);
            at(tile_x+60,tile_y+30,32'h00101b2a); // Horizontal separation.
            at(tile_x+4,tile_y+44,32'h00101b2a);  // Vertical separation.
            for(digit_index=0;digit_index<2;digit_index=digit_index+1) begin
                reference_character=8'h30+(digit_index==0 ? (voice_index+1)/10 : (voice_index+1)%10);
                for(row_index=0;row_index<8;row_index=row_index+1)
                    for(column_index=0;column_index<8;column_index=column_index+1) begin
                        reference_row=row_index; reference_column=column_index; #1;
                        at(tile_x+16+16*digit_index+2*column_index,tile_y+12+2*row_index,
                           reference_ink ? 32'h00e5f0fa : 32'h00263a4f);
                    end
            end
        end
        // The status word must retain all eight nibbles, not only voices 0..7.
        voices=32'h89abcdef;
        for(digit_index=0;digit_index<8;digit_index=digit_index+1) begin
            mask_digit=voices[31-digit_index*4 -: 4];
            reference_character=mask_digit<10 ? 8'h30+mask_digit : 8'h37+mask_digit;
            for(row_index=0;row_index<8;row_index=row_index+1)
                for(column_index=0;column_index<8;column_index=column_index+1) begin
                    reference_row=row_index; reference_column=column_index; #1;
                    at(1536+16*digit_index+2*column_index,896+2*row_index,
                       reference_ink ? 32'h00e5f0fa : 32'h00101b2a);
                end
        end
        voices=1;at(70,910,32'h00157d70);at(134,910,32'h00263a4f);
        @(negedge clk); enable=0; x=64; y=48;
        repeat(5) @(posedge clk);
        #1; if(pixel!==32'h00263a4f) $fatal(1,"dashboard pipeline changed while stopped");
        // Isolate the added C/D font stages. Compare every ASCII byte and
        // all 8x8 legal/padding positions with the legacy scalar-font decoder,
        // which uses arithmetic indexing instead of the new fixed-slice cases.
        @(negedge clk); enable=1;
        force dut.b_character=reference_character;
        force dut.b_font_row=reference_row;
        force dut.b_font_column=reference_column;
        force dut.b_text_enable=1'b1;
        force dut.b_background=32'h00101b2a;
        for(character_index=0;character_index<256;character_index=character_index+1)
            for(row_index=0;row_index<8;row_index=row_index+1)
                for(column_index=0;column_index<8;column_index=column_index+1) begin
                    @(negedge clk);
                    reference_character=character_index;
                    reference_row=row_index;
                    reference_column=column_index;
                    repeat(2) @(posedge clk);
                    #1;
                    if(pixel!==(reference_ink ? 32'h00e5f0fa : 32'h00101b2a))
                        $fatal(1,"font pipeline mismatch character=%d row=%d column=%d pixel=%h refink=%b glyph=%h bg=%h char=%h",character_index,row_index,column_index,pixel,reference_ink,dut.c_glyph,dut.c_background,dut.b_character);
                end
        release dut.b_character; release dut.b_font_row; release dut.b_font_column;
        release dut.b_text_enable; release dut.b_background;
        $display("PASS feedback dashboard: all 32 one-hot activity masks, decimal labels 01..32, full 32-bit mask, all 256 glyphs x 8x8 coordinates, stopped four-stage pipeline, text boundaries, Q1.31 endpoints, trace connection, peak and calibration/BIST state");
        $finish;
    end
endmodule
