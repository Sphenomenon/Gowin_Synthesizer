reg [7:0] message[0:511],last_reply[0:83];
integer checks=0,cycles=0,compared_bytes=0,token_counter=0;
reg [31:0] hit_mask=0;
reg walk_time=0,abort_seen=0;
reg [63:0] active_nonce=64'h123456789abcdef0;
integer i,j,n,total_count,fragment_count,offset_count,k,status;
reg [31:0] checksum;
function automatic [31:0] crc_byte(input [31:0] before_crc,input [7:0] value);
reg [31:0] c;integer bit_index;
begin c=before_crc^value;for(bit_index=0;bit_index<8;bit_index=bit_index+1)c=(c>>1)^(c[0]?32'hedb88320:0);crc_byte=c;end
endfunction
always #5 clk=~clk;
always @(negedge clk)if(walk_time && dut.state==7)elapsed_ms=elapsed_ms+1;
always @(posedge clk)begin
    cycles=cycles+1;
    if(resetn && enable && dut.state==7 && dut.metadata_hit)hit_mask[dut.lookup_slot]=1;
    if(resetn && dut.metadata_write && dut.g_block_metadata.read_enable)$fatal(1,"metadata read/write collision");
end
always @(posedge clk or negedge clk)begin
    #1;
    if(cycles>2)begin
        // Generated checks compare every output with validity-gated RAM data.
        `include "compare_outputs.svh"
        if(dut.state!==reference.state)$fatal(1,"parser state changed cycle=%0d new=%0d old=%0d",cycles,dut.state,reference.state);
        checks=checks+1;
    end
end
task step;begin @(negedge clk);#2;end endtask
task set_fragment_byte(input [4:0] address,input [7:0] value);
begin fragment_write=1;fragment_addr=address;fragment_data=value;step();fragment_write=0;end
endtask
task request(input [7:0] operation,input [31:0] id,input integer payload_bytes,input integer changed);
integer at,part,sequence_number,waited,reply_bytes;
reg [7:0] flags;
begin: request_body
    for(at=0;at<512;at=at+1)message[at]=0;
    message[0]=operation;message[2]=payload_bytes;message[3]=payload_bytes>>8;
    for(at=0;at<4;at=at+1)message[4+at]=id>>(8*at);
    for(at=0;at<8;at=at+1)message[8+at]=active_nonce>>(8*at);
    if(operation==1)message[16]=1;
    if(changed!=0)message[16]=changed;
    total_count=20+payload_bytes;checksum=32'hffffffff;
    for(at=0;at<total_count-4;at=at+1)checksum=crc_byte(checksum,message[at]);
    checksum=~checksum;
    for(at=0;at<4;at=at+1)message[total_count-4+at]=checksum>>(8*at);
    token_counter=token_counter+1;offset_count=0;sequence_number=0;
    while(offset_count<total_count)begin
        part=total_count-offset_count;if(part>14)part=14;
        flags=(offset_count==0 ? 1:0)|(offset_count+part==total_count ? 2:0);
        set_fragment_byte(0,8'hb1);set_fragment_byte(1,token_counter);set_fragment_byte(2,token_counter>>8);
        set_fragment_byte(3,sequence_number);set_fragment_byte(4,flags);set_fragment_byte(5,part);
        for(at=0;at<part;at=at+1)set_fragment_byte(6+at,message[offset_count+at]);
        fragment_length=6+part;fragment_start=1;step();fragment_start=0;waited=0;
        while(!n_fragment_done && waited<10000 && !abort_seen)begin step();waited=waited+1;end
        if(abort_seen)disable request_body;
        if(waited==10000 || n_fragment_error!=0)$fatal(1,"fragment completion id=%0d error=%h",id,n_fragment_error);
        offset_count=offset_count+part;sequence_number=sequence_number+1;
    end
    waited=0;while(!n_response_valid && waited<10000)begin step();waited=waited+1;end
    if(waited==10000)$fatal(1,"no response id=%0d",id);
    reply_bytes=n_response_length;
    for(at=0;at<reply_bytes;at=at+1)begin
        response_addr=at;#1;last_reply[at]=n_response_data;
        if(n_response_data!==g_response_data)$fatal(1,"response byte id=%0d offset=%0d",id,at);
        compared_bytes=compared_bytes+1;step();
    end
    response_consume=1;step();response_consume=0;step();
end endtask
task expect_status(input integer expected);
begin if(last_reply[1]!==expected[7:0])$fatal(1,"unexpected reply status=%h expected=%h",last_reply[1],expected[7:0]);checks=checks+1;end
endtask
task begin_session;
begin request(1,1,4,0);expect_status(0);end endtask
initial begin
    `include "input_defaults.svh"
    repeat(4)step();resetn=1;step();
    // Every slot is hit, then all32 entries are replaced in ring order.
    begin_session();
    for(i=2;i<=32;i=i+1)begin request(2,i,0,0);expect_status(0);end
    for(i=1;i<=32;i=i+1)begin request(i==1 ? 1:2,i,i==1 ? 4:0,0);expect_status(0);end
    if(hit_mask!==32'hffffffff)$fatal(1,"not every slot hit %h",hit_mask);
    // Expiry can cross during the32-cycle scan without adding a lookup clock.
    elapsed_ms=59969;walk_time=1;request(2,32,0,0);walk_time=0;expect_status(8'h87);elapsed_ms=0;
    for(i=33;i<=64;i=i+1)begin request(2,i,0,0);expect_status(0);end
    request(1,1,4,0);expect_status(8'h87);
    for(i=33;i<=64;i=i+1)begin request(2,i,0,0);expect_status(0);end
    request(2,50,1,1);expect_status(8'h86); // SameID, different total length.
    request(3,50,0,0);expect_status(8'h86); // Same length, different request bytes.
    elapsed_ms=59999;request(2,50,0,0);expect_status(0);
    elapsed_ms=60000;request(2,50,0,0);expect_status(8'h87);
    // Disable clears validity/session, while physical metadata RAM stays old.
    enable=0;repeat(3)step();enable=1;active_nonce=64'hfedcba9876543210;elapsed_ms=0;
    begin_session();request(2,100,0,0);expect_status(0);
    request(2,50,0,0);expect_status(8'h87);
    // CPU observer reset preserves the radio-session cache and its bytes.
    business_owner_reset_ni=0;repeat(3)step();business_owner_reset_ni=1;repeat(3)step();
    request(2,100,0,0);expect_status(0);
    // A true common reset also hides stale entries until newly published.
    resetn=0;repeat(3)step();resetn=1;elapsed_ms=32'hfffffff0;active_nonce=64'h1020304050607080;
    begin_session();request(2,2,0,0);expect_status(0);
    elapsed_ms=32'h20;request(2,2,0,0);expect_status(0);
    elapsed_ms=32'hea4f;request(2,2,0,0);expect_status(0);
    elapsed_ms=32'hea50;request(2,2,0,0);expect_status(8'h87);
    // Reset while a miss is walking old, invalid RAM slots.
    elapsed_ms=0;request(2,200,0,0);expect_status(0);
    fork
        request(2,50,0,0);
        begin
            wait(dut.state==7 && dut.lookup_slot==17);#2;resetn=0;abort_seen=1;
            repeat(3)step();resetn=1;step();
        end
    join
    abort_seen=0;elapsed_ms=0;active_nonce=64'h9988776655443322;
    begin_session();request(2,200,0,0);expect_status(0);
    request(2,50,0,0);expect_status(8'h87);
    if(dut.cache_valid!==32'h3)$fatal(1,"old RAM became valid after reset");
    $display("PASS real parser metadata equivalence checks=%0d cycles=%0d bytes=%0d hit_mask=%h",checks,cycles,compared_bytes,hit_mask);
    $finish;
end
initial begin #10000000;$fatal(1,"test timeout");end
