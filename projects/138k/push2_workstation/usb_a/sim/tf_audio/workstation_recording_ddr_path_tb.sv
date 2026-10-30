
`timescale 1ns/1ps
module tb_workstation_recording_ddr_path;
parameter integer BITS=5,SEED=7,RECORDING_ENABLE=1,USE_RECORDING=1,CORE_ONLY=0,REGISTER_GRANTS=0;
reg clk=0,rst=0,bd=0;
always #5 clk=~clk;
reg [8:0] valid=0,write=0;
reg [28:0] address[0:8];reg [255:0] data[0:8];reg [31:0] mask[0:8];
wire [8:0] ready,response;
assign response[3]=0;
wire [8:0] slot_accept,core_accept,native_accept;wire transport_fault;
wire [2:0] cmd;wire en,wren,wend;wire [28:0] native_address;
wire [255:0] native_data,client_rddata;wire [31:0] native_mask;wire fault;
reg native_ready=0,native_wrdy=0,native_rsp=0;reg [255:0] native_rddata=0;
wire command_pending;
wire [7:0] ref_ready,ref_response;assign ref_response[3]=0;
wire [2:0] ref_cmd;wire ref_en,ref_wren,ref_wend,ref_fault;
wire [28:0] ref_native_address;wire [255:0] ref_native_data,ref_client_rddata;wire [31:0] ref_native_mask;
generate if(CORE_ONLY)begin:g_core
    workstation_recording_ddr_arbiter_pipeline #(.TAG_BITS(BITS),.REGISTER_GRANTS(REGISTER_GRANTS),.RECORDING_ENABLE(RECORDING_ENABLE)) dut(
        .clk(clk),
        .reset_n(rst),
        .bist_done(bd),
        .bist_valid(valid[0]),
        .bist_address(address[0]),
        .bist_ready(ready[0]),
        .bist_data(data[0]),
        .bist_write(write[0]),
        .bist_response(response[0]),
        .scan_valid(valid[1]),
        .scan_address(address[1]),
        .scan_ready(ready[1]),
        .scan_response(response[1]),
        .cpu_valid(valid[2]),
        .cpu_address(address[2]),
        .cpu_ready(ready[2]),
        .cpu_data(data[2]),
        .cpu_write(write[2]),
        .cpu_mask(mask[2]),
        .cpu_response(response[2]),
        .writer_valid(valid[3]),
        .writer_address(address[3]),
        .writer_ready(ready[3]),
        .writer_data(data[3]),
        .audio_valid(valid[4]),
        .audio_address(address[4]),
        .audio_ready(ready[4]),
        .audio_data(data[4]),
        .audio_write(write[4]),
        .audio_response(response[4]),
        .music_valid(valid[5]),
        .music_address(address[5]),
        .music_ready(ready[5]),
        .music_data(data[5]),
        .music_write(write[5]),
        .music_mask(mask[5]),
        .music_response(response[5]),
        .delay_valid(valid[6]),
        .delay_address(address[6]),
        .delay_ready(ready[6]),
        .delay_data(data[6]),
        .delay_write(write[6]),
        .delay_response(response[6]),
        .display_valid(valid[7]),
        .display_address(address[7]),
        .display_ready(ready[7]),
        .display_response(response[7]),
        .recording_valid(valid[8]),
        .recording_address(address[8]),
        .recording_ready(ready[8]),
        .recording_data(data[8]),
        .recording_write(write[8]),
        .recording_mask(mask[8]),
        .recording_response(response[8]),
        .app_cmd(cmd),
        .app_en(en),
        .app_wren(wren),
        .app_wend(wend),
        .app_address(native_address),
        .app_data(native_data),
        .app_mask(native_mask),
        .response_data(client_rddata),
        .response_fault(fault),
        .app_ready(native_ready),
        .app_write_ready(native_wrdy),
        .app_response(native_rsp),
        .app_response_data(native_rddata),
        .core_accept_o(core_accept),
        .native_accept_o(native_accept),
        .transport_fault_o(transport_fault));
    assign slot_accept=valid & ready;
    basic_pitch_ddr_arbiter_pipeline #(.TAG_BITS(BITS),.REGISTER_GRANTS(REGISTER_GRANTS)) reference(
        .clk(clk),
        .reset_n(rst),
        .bist_done(bd),
        .bist_valid(valid[0]),
        .bist_address(address[0]),
        .bist_ready(ref_ready[0]),
        .bist_data(data[0]),
        .bist_write(write[0]),
        .bist_response(ref_response[0]),
        .scan_valid(valid[1]),
        .scan_address(address[1]),
        .scan_ready(ref_ready[1]),
        .scan_response(ref_response[1]),
        .cpu_valid(valid[2]),
        .cpu_address(address[2]),
        .cpu_ready(ref_ready[2]),
        .cpu_data(data[2]),
        .cpu_write(write[2]),
        .cpu_mask(mask[2]),
        .cpu_response(ref_response[2]),
        .writer_valid(valid[3]),
        .writer_address(address[3]),
        .writer_ready(ref_ready[3]),
        .writer_data(data[3]),
        .audio_valid(valid[4]),
        .audio_address(address[4]),
        .audio_ready(ref_ready[4]),
        .audio_data(data[4]),
        .audio_write(write[4]),
        .audio_response(ref_response[4]),
        .music_valid(valid[5]),
        .music_address(address[5]),
        .music_ready(ref_ready[5]),
        .music_data(data[5]),
        .music_write(write[5]),
        .music_mask(mask[5]),
        .music_response(ref_response[5]),
        .delay_valid(valid[6]),
        .delay_address(address[6]),
        .delay_ready(ref_ready[6]),
        .delay_data(data[6]),
        .delay_write(write[6]),
        .delay_response(ref_response[6]),
        .display_valid(valid[7]),
        .display_address(address[7]),
        .display_ready(ref_ready[7]),
        .display_response(ref_response[7]),
        .app_cmd(ref_cmd),
        .app_en(ref_en),
        .app_wren(ref_wren),
        .app_wend(ref_wend),
        .app_address(ref_native_address),
        .app_data(ref_native_data),
        .app_mask(ref_native_mask),
        .response_data(ref_client_rddata),
        .response_fault(ref_fault),
        .app_ready(native_ready),
        .app_write_ready(native_wrdy),
        .app_response(native_rsp),
        .app_response_data(native_rddata));
    if(RECORDING_ENABLE)assign command_pending=dut.g_recording.command_full;
    else assign command_pending=reference.command_full;
end else begin:g_queues
    workstation_recording_ddr_client_queues #(.TAG_BITS(BITS),.RECORDING_ENABLE(RECORDING_ENABLE)) dut(
        .clk(clk),
        .reset_n(rst),
        .bist_done(bd),
        .bist_valid(valid[0]),
        .bist_address(address[0]),
        .bist_ready(ready[0]),
        .bist_data(data[0]),
        .bist_write(write[0]),
        .bist_response(response[0]),
        .scan_valid(valid[1]),
        .scan_address(address[1]),
        .scan_ready(ready[1]),
        .scan_response(response[1]),
        .cpu_valid(valid[2]),
        .cpu_address(address[2]),
        .cpu_ready(ready[2]),
        .cpu_data(data[2]),
        .cpu_write(write[2]),
        .cpu_mask(mask[2]),
        .cpu_response(response[2]),
        .writer_valid(valid[3]),
        .writer_address(address[3]),
        .writer_ready(ready[3]),
        .writer_data(data[3]),
        .audio_valid(valid[4]),
        .audio_address(address[4]),
        .audio_ready(ready[4]),
        .audio_data(data[4]),
        .audio_write(write[4]),
        .audio_response(response[4]),
        .music_valid(valid[5]),
        .music_address(address[5]),
        .music_ready(ready[5]),
        .music_data(data[5]),
        .music_write(write[5]),
        .music_mask(mask[5]),
        .music_response(response[5]),
        .delay_valid(valid[6]),
        .delay_address(address[6]),
        .delay_ready(ready[6]),
        .delay_data(data[6]),
        .delay_write(write[6]),
        .delay_response(response[6]),
        .display_valid(valid[7]),
        .display_address(address[7]),
        .display_ready(ready[7]),
        .display_response(response[7]),
        .recording_valid(valid[8]),
        .recording_address(address[8]),
        .recording_ready(ready[8]),
        .recording_data(data[8]),
        .recording_write(write[8]),
        .recording_mask(mask[8]),
        .recording_response(response[8]),
        .app_cmd(cmd),
        .app_en(en),
        .app_wren(wren),
        .app_wend(wend),
        .app_address(native_address),
        .app_data(native_data),
        .app_mask(native_mask),
        .response_data(client_rddata),
        .response_fault(fault),
        .app_ready(native_ready),
        .app_write_ready(native_wrdy),
        .app_response(native_rsp),
        .app_response_data(native_rddata),
        .core_accept_o(core_accept),
        .native_accept_o(native_accept),
        .transport_fault_o(transport_fault),
        .slot_accept_o(slot_accept));
    basic_pitch_ddr_client_queues #(.TAG_BITS(BITS)) reference(
        .clk(clk),
        .reset_n(rst),
        .bist_done(bd),
        .bist_valid(valid[0]),
        .bist_address(address[0]),
        .bist_ready(ref_ready[0]),
        .bist_data(data[0]),
        .bist_write(write[0]),
        .bist_response(ref_response[0]),
        .scan_valid(valid[1]),
        .scan_address(address[1]),
        .scan_ready(ref_ready[1]),
        .scan_response(ref_response[1]),
        .cpu_valid(valid[2]),
        .cpu_address(address[2]),
        .cpu_ready(ref_ready[2]),
        .cpu_data(data[2]),
        .cpu_write(write[2]),
        .cpu_mask(mask[2]),
        .cpu_response(ref_response[2]),
        .writer_valid(valid[3]),
        .writer_address(address[3]),
        .writer_ready(ref_ready[3]),
        .writer_data(data[3]),
        .audio_valid(valid[4]),
        .audio_address(address[4]),
        .audio_ready(ref_ready[4]),
        .audio_data(data[4]),
        .audio_write(write[4]),
        .audio_response(ref_response[4]),
        .music_valid(valid[5]),
        .music_address(address[5]),
        .music_ready(ref_ready[5]),
        .music_data(data[5]),
        .music_write(write[5]),
        .music_mask(mask[5]),
        .music_response(ref_response[5]),
        .delay_valid(valid[6]),
        .delay_address(address[6]),
        .delay_ready(ref_ready[6]),
        .delay_data(data[6]),
        .delay_write(write[6]),
        .delay_response(ref_response[6]),
        .display_valid(valid[7]),
        .display_address(address[7]),
        .display_ready(ref_ready[7]),
        .display_response(ref_response[7]),
        .app_cmd(ref_cmd),
        .app_en(ref_en),
        .app_wren(ref_wren),
        .app_wend(ref_wend),
        .app_address(ref_native_address),
        .app_data(ref_native_data),
        .app_mask(ref_native_mask),
        .response_data(ref_client_rddata),
        .response_fault(ref_fault),
        .app_ready(native_ready),
        .app_write_ready(native_wrdy),
        .app_response(native_rsp),
        .app_response_data(native_rddata));
    if(RECORDING_ENABLE)assign command_pending=dut.g_recording.u_core.g_recording.command_full;
    else assign command_pending=reference.u_core.command_full;
end endgenerate
always @(negedge clk)begin #1;if(rst && (!RECORDING_ENABLE || !USE_RECORDING))begin
    if({ready[7:0],response[7:0],cmd,en,wren,wend,native_address,native_data,native_mask,client_rddata,fault} !==
       {ref_ready,ref_response,ref_cmd,ref_en,ref_wren,ref_wend,ref_native_address,ref_native_data,ref_native_mask,ref_client_rddata,ref_fault})
        $fatal(1,"default/idle owner8 legacy cycle miter mismatch");
    if(!RECORDING_ENABLE && (ready[8] || response[8] || |native_accept))$fatal(1,"disabled owner8 logic active");
end end

reg [255:0] model[0:4095],physical[0:4095];
reg [28:0] eq_addr[0:100000];reg [255:0] eq_data[0:100000];reg [31:0] eq_mask[0:100000];reg eq_write[0:100000];
reg [255:0] er_data[0:100000];integer er_owner[0:100000];
reg [255:0] nr_data[0:100000];integer nr_cycle[0:100000];
integer accept_count=0,issue_count=0,read_count=0,returned=0,nr_in=0,nr_out=0,cycle=0;
integer per_client[0:8],sequence_no[0:8],take_index[0:8];integer eq_slot[0:8][0:20000];integer native_owner,wanted;integer core_in=0,core_out=0;integer core_order[0:100000];integer core_take[0:8];reg [31:0] lane_coverage=0;integer single_lane_writes=0;integer max_tags=0,blocked=0,consecutive_returns=0;reg prior_return=0;
reg [31:0] random_state=SEED;
reg stalled=0;reg [319:0] held;
function [255:0] pattern(input integer owner,input integer seq);
 for(integer k=0;k<8;k=k+1)pattern[k*32+:32]=(seq*32'h9e3779b9)^(owner*32'h12121212)^k;
endfunction
always @(posedge clk)begin
 if(rst)begin
  cycle=cycle+1;
  if(stalled && held !== {cmd,native_address,native_data,native_mask})$fatal(1,"command changed under native stall");
  stalled=command_pending && !en;held={cmd,native_address,native_data,native_mask};
  if($countones(response)>1)$fatal(1,"nonexclusive handshake/response");
  if(|response && prior_return)consecutive_returns=consecutive_returns+1;
  prior_return=|response;
  for(integer i=0;i<9;i=i+1)if(response[i])begin
   if(returned>=read_count || er_owner[returned]!=i || er_data[returned]!==client_rddata)$fatal(1,"response lost/reordered/memory mismatch at%0d owner%0d wanted%0d",returned,i,er_owner[returned]);
   returned=returned+1;
  end
  if(en)begin
   if(!native_ready || (wren && !native_wrdy))$fatal(1,"native command/write data not jointly accepted");
   native_owner=native_address[14:11];
   if(RECORDING_ENABLE && native_accept!==(9'b1<<native_owner))$fatal(1,"native owner8 acceptance/tag truncation");
   if(RECORDING_ENABLE && (core_out>=core_in || core_order[core_out]!=eq_slot[native_owner][take_index[native_owner]]))$fatal(1,"core/native acceptance order mismatch");
   if(RECORDING_ENABLE)core_out=core_out+1;
   if(native_owner==8 && cmd==0)begin lane_coverage=lane_coverage|~native_mask;if($countones(~native_mask)==1)single_lane_writes=single_lane_writes+1;end
   if(take_index[native_owner]>=per_client[native_owner])$fatal(1,"native command without client acceptance");
   wanted=eq_slot[native_owner][take_index[native_owner]];
   if(!bd && native_owner!=0)$fatal(1,"non-BIST native issue before BIST completion");
   if(native_address!==eq_addr[wanted] || native_mask!==eq_mask[wanted] || native_data!==eq_data[wanted] || (cmd==0)!==eq_write[wanted])$fatal(1,"per-client native command order/data changed owner%0d at%0d",native_owner,take_index[native_owner]);
   take_index[native_owner]=take_index[native_owner]+1;
   if(eq_write[wanted])begin
    for(integer k=0;k<32;k=k+1)if(!eq_mask[wanted][k])model[eq_addr[wanted][14:3]][k*8+:8]=eq_data[wanted][k*8+:8];
   end else begin er_data[read_count]=model[eq_addr[wanted][14:3]];er_owner[read_count]=native_owner;read_count=read_count+1;end
   if(wren!==wend || wren!==(cmd==0))$fatal(1,"write handshake mismatch");
   if(cmd==0)begin
    for(integer k=0;k<32;k=k+1)if(!native_mask[k])physical[native_address[14:3]][k*8+:8]=native_data[k*8+:8];
   end else begin nr_data[nr_in]=physical[native_address[14:3]];nr_cycle[nr_in]=cycle;nr_in=nr_in+1;end
   issue_count=issue_count+1;
  end
  if(RECORDING_ENABLE)begin
   if($countones(core_accept)>1 || $countones(native_accept)>1 || (|native_accept)!==en)$fatal(1,"nonexclusive three-stage acceptance");
   for(integer i=0;i<9;i=i+1)if(core_accept[i])begin
    if(!CORE_ONLY && core_take[i]>=per_client[i])$fatal(1,"core accepted without local slot");
    core_order[core_in]=CORE_ONLY ? accept_count : eq_slot[i][core_take[i]];core_in=core_in+1;core_take[i]=core_take[i]+1;
   end
  end
  if(slot_accept!==(valid & ready))$fatal(1,"local slot acceptance fact mismatch");
  for(integer i=0;i<9;i=i+1)if(valid[i] && ready[i])begin
   eq_addr[accept_count]=address[i];
   eq_data[accept_count]=(i==1 || i==7)?0:data[i];
   eq_mask[accept_count]=(i==2 || i==5 || i==8)?mask[i]:0;
   eq_write[accept_count]=(i==1 || i==7)?0:((i==3)?1:write[i]);
eq_slot[i][per_client[i]]=accept_count;
   accept_count=accept_count+1;per_client[i]=per_client[i]+1;sequence_no[i]=sequence_no[i]+1;
   valid[i]<=0;
  end
  if(read_count-returned>max_tags)max_tags=read_count-returned;
  if(nr_in-nr_out==(1<<BITS))blocked=blocked+1;
  if(fault)$fatal(1,"unexpected native response fault");
 end
end
task zero_state;
 begin
  rst=0;bd=0;valid=0;native_rsp=0;stalled=0;core_in=0;core_out=0;lane_coverage=0;single_lane_writes=0;
  accept_count=0;issue_count=0;read_count=0;returned=0;nr_in=0;nr_out=0;cycle=0;max_tags=0;blocked=0;consecutive_returns=0;prior_return=0;
  for(integer i=0;i<9;i=i+1)begin per_client[i]=0;sequence_no[i]=0;take_index[i]=0;core_take[i]=0;end
  for(integer i=0;i<4096;i=i+1)begin model[i]=pattern(9,i);physical[i]=pattern(9,i);end
  repeat(4)@(negedge clk);rst=1;
 end
endtask
task native_drive(input integer pause);
 begin
  random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
  native_ready=random_state[2:0]!=0;native_wrdy=random_state[6:4]>1;
  native_rsp=0;native_rddata=pattern(99,cycle); // data changes even without valid
  if(nr_out<nr_in && cycle>nr_cycle[nr_out]+1 && pause==0 && random_state[12:10]!=0)begin
   native_rsp=1;native_rddata=nr_data[nr_out];nr_out=nr_out+1;
  end
 end
endtask
task offer(input integer i);
 begin
  if(!valid[i] && (i!=8 || (RECORDING_ENABLE && USE_RECORDING)))begin
   valid[i]=1;write[i]=random_state[(i+5)%32];
   address[i]=((i*256)+(sequence_no[i]%32))*8;
   data[i]=pattern(i,sequence_no[i]);mask[i]=(i==8)?~(32'h1<<(sequence_no[i]%32)):(random_state^(32'h80808080>>i));
  end
 end
endtask
initial begin
 zero_state();
 // BIST owns the bus before the completion epoch, even with other requests.
 for(integer k=0;k<1200;k=k+1)begin
  @(negedge clk);native_drive(0);if(k<500)begin offer(0);offer(1);offer(5);offer(8);end
  // Stop offering; retain every unaccepted request until its ready edge.
 end
 if(per_client[0]<100 || per_client[1]>1 || per_client[5]>1 || returned!=read_count)$fatal(1,"BIST epoch isolation failed");
 bd=1;
 if(RECORDING_ENABLE && USE_RECORDING)begin
  repeat(100)begin @(negedge clk);native_drive(0);end
  for(integer lane=0;lane<32;lane=lane+1)begin
   @(negedge clk);native_drive(0);offer(8);write[8]=1;
   while(valid[8])begin @(negedge clk);native_drive(0);end
  end
  repeat(150)begin @(negedge clk);native_drive(0);end
 end
 // Force the tag FIFO to fill, then drain under mixed competing clients.
 for(integer k=0;k<30000;k=k+1)begin
  @(negedge clk);native_drive(k<300?1:0);
  for(integer i=1;i<9;i=i+1)if(((random_state>>((i*3)%27))&31)==0 || k<1000)offer(i);
 end
 @(negedge clk);native_drive(0);
 for(integer k=0;k<5000;k=k+1)begin @(negedge clk);native_drive(0);end
 if(accept_count!=issue_count || read_count!=returned || nr_in!=nr_out || blocked==0 || consecutive_returns==0 || (RECORDING_ENABLE && core_in!=core_out))$fatal(1,"drain/tag-full mismatch accepted%0d issue%0d read%0d returned%0d blocked%0d",accept_count,issue_count,read_count,returned,blocked);
 for(integer i=0;i<9;i=i+1)if((i!=8 || (RECORDING_ENABLE && USE_RECORDING)) && per_client[i]<8)$fatal(1,"client%0d unexercised count%0d",i,per_client[i]);
 if(RECORDING_ENABLE && USE_RECORDING && (lane_coverage!=32'hffffffff || single_lane_writes<32))$fatal(1,"owner8 mask lane coverage");
 $display("PASS shared DDR pipeline seed=%0d tags=%0d clients=%0d commands=%0d reads=%0d full_tag_cycles=%0d core_commands=%0d native_commands=%0d masked memory/native stalls/consecutive returns/BIST epoch/order",SEED,1<<BITS,(RECORDING_ENABLE&&USE_RECORDING)?9:8,accept_count,returned,blocked,core_in,core_out);
 for(integer owner_index=0;owner_index<9;owner_index=owner_index+1)
  $display("OWNER index=%0d slot=%0d core=%0d native=%0d",owner_index,per_client[owner_index],core_take[owner_index],take_index[owner_index]);
 // A full global reset discards pending command/tags/data and rearms fault.
 @(negedge clk);offer(1);native_ready=0;repeat(3)@(negedge clk);zero_state();
 if(en || |response || fault)$fatal(1,"global reset retained traffic");
 // Reset with native reads already issued and response tags outstanding.
 bd=1;
 for(integer k=0;k<40;k=k+1)begin
  @(negedge clk);native_drive(1);offer(1);
 end
 if(nr_in==nr_out)$fatal(1,"in-flight reset fixture had no tags");
 zero_state();
 if(en || |response || fault)$fatal(1,"in-flight reset retained traffic");
 @(negedge clk);native_rsp=1;@(posedge clk);#1;if(!fault)$fatal(1,"unexpected untagged response not explicit");
 @(negedge clk);rst=0;native_rsp=0;repeat(3)@(negedge clk);rst=1;repeat(3)@(negedge clk);if(fault)$fatal(1,"fault did not reset");
 $finish;
end
endmodule
