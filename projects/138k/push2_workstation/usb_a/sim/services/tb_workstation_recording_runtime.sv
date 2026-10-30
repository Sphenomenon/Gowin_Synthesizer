`timescale 1ns/1ps
module tb_workstation_recording_runtime;
parameter integer CASE=0;
reg memclk=0,srcclk=0,pclk=0,ctlclk=0;
reg memory_running=1;
always #5 if(memory_running)memclk=~memclk;
always #7 srcclk=~srcclk;
always #11 pclk=~pclk;
always #13 ctlclk=~ctlclk;
reg reset_n=0,preset_n=0,backend_ready=1;
reg fv=0,fe=0,f44=1;reg [31:0] fepoch=42,fseq=0,fpcm=0;
reg psel=0,penable=0,pwrite=0;reg [11:0] paddr=0;reg [31:0] pwdata=0;reg [3:0] pstrb=15;
wire pready,pslverr;wire [31:0] prdata;
reg seal_hold=0,seal_request=0;wire seal_ready,seal_done,seal_failed;wire [3:0] seal_code;
reg media_request=0,media_hold=0,runtime_done=0,ble_done=0;
wire media_ready,media_done,media_failed;wire [3:0] media_code;
wire runtime_request,ble_request,media_recording_request,media_recording_hold;
wire selected_seal_hold=CASE==8 ? media_recording_hold:seal_hold;
wire selected_seal_request=CASE==8 ? media_recording_request:seal_request;
workstation_media_preparation #(.ENABLE_BLE(1),.ENABLE_RECORDING(1)) media(
 .clk_i(ctlclk),.reset_ni(reset_n),.request_i(media_request),.hold_i(media_hold),
 .ready_o(media_ready),.done_o(media_done),.failed_o(media_failed),.failure_code_o(media_code),
 .runtime_request_o(runtime_request),.runtime_hold_o(),.runtime_ready_i(1'b1),.runtime_done_i(runtime_done),.runtime_failed_i(1'b0),.runtime_failure_code_i(4'd0),
 .ble_request_o(ble_request),.ble_hold_o(),.ble_ready_i(1'b1),.ble_done_i(ble_done),.ble_failed_i(1'b0),.ble_failure_code_i(4'd0),.ble_failure_code_o(),
 .recording_request_o(media_recording_request),.recording_hold_o(media_recording_hold),.recording_ready_i(seal_ready),.recording_done_i(seal_done),
 .recording_failed_i(seal_failed),.recording_failure_code_i(seal_code),.recording_failure_code_o());
wire rv,rw,rrdy,rrsp;wire [28:0] ra;wire [255:0] rd;wire [31:0] rm;
wire [3:0] state,failure;wire [31:0] frames,committed;wire captured;
wire [8:0] slot_accept,core_accept,native_accept;wire transport_fault;
wire [255:0] returned;wire [2:0] app_cmd;wire app_en,app_wren,app_wend;
wire [28:0] app_addr;wire [255:0] app_data;wire [31:0] app_mask;
reg force_stall=0,hold_response=0,inject_response=0,traffic=0;
integer cycles=0,slots=0,cores=0,natives=0,record_writes=0,record_reads=0;
wire app_ready=!force_stall && cycles%11!=0;
wire app_wrdy=!force_stall && cycles%7!=0;
reg mem_response=0;reg [255:0] mem_data=0;
workstation_recording_runtime #(.CAPACITY_FRAMES(64),.FIFO_ADDRESS_BITS(4),
 .DDR_BUDGET_CYCLES(20000),.SOURCE_GAP_CYCLES(20000)) dut(
 .reset_ni(reset_n),.source_clk_i(srcclk),.memory_clk_i(memclk),.control_clk_i(ctlclk),.backend_ready_i(backend_ready),
 .frame_valid_i(fv),.frame_error_i(fe),.frame_44k1_i(f44),.frame_epoch_i(fepoch),.frame_sequence_i(fseq),.frame_pcm_i(fpcm),
 .pclk(pclk),.preset_n(preset_n),.psel(psel),.penable(penable),.pwrite(pwrite),.paddr(paddr),.pwdata(pwdata),.pstrb(pstrb),
 .pready(pready),.pslverr(pslverr),.prdata(prdata),.seal_hold_i(selected_seal_hold),.seal_request_i(selected_seal_request),
 .seal_ready_o(seal_ready),.seal_done_o(seal_done),.seal_failed_o(seal_failed),.seal_failure_code_o(seal_code),
 .recording_valid_o(rv),.recording_write_o(rw),.recording_address_o(ra),.recording_data_o(rd),.recording_mask_o(rm),
 .recording_ready_i(rrdy),.recording_response_i(rrsp),.recording_native_accept_i(native_accept[8]),.recording_read_data_i(returned),
 .transport_fault_i(transport_fault),.object_state_o(state),.object_failure_o(failure),.object_frames_o(frames),
 .committed_frames_o(committed),.capture_o(captured));
workstation_recording_ddr_client_queues #(.TAG_BITS(3),.RECORDING_ENABLE(1)) owner8(
 .clk(memclk),.reset_n(reset_n),.bist_done(1'b1),
 .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),.bist_ready(),.bist_response(),
 .scan_valid(1'b0),.scan_address(29'd0),.scan_ready(),.scan_response(),
 .display_valid(1'b0),.display_address(29'd0),.display_ready(),.display_response(),
 .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),.audio_ready(),.audio_response(),
 .music_valid(1'b0),.music_write(1'b0),.music_address(29'd0),.music_data(256'd0),.music_mask(32'd0),.music_ready(),.music_response(),
 .delay_valid(1'b0),.delay_write(1'b0),.delay_address(29'd0),.delay_data(256'd0),.delay_ready(),.delay_response(),
 .writer_valid(1'b0),.writer_address(29'd0),.writer_data(256'd0),.writer_ready(),
 .cpu_valid(traffic && cycles%17==0),.cpu_write(1'b0),.cpu_address(29'h100),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
 .recording_valid(rv),.recording_write(rw),.recording_address(ra),.recording_data(rd),.recording_mask(rm),.recording_ready(rrdy),.recording_response(rrsp),
 .app_cmd(app_cmd),.app_en(app_en),.app_wren(app_wren),.app_wend(app_wend),.app_address(app_addr),.app_data(app_data),.app_mask(app_mask),
 .app_ready(app_ready),.app_write_ready(app_wrdy),.app_response(mem_response || inject_response),.app_response_data(mem_data),
 .response_data(returned),.response_fault(),.slot_accept_o(slot_accept),.core_accept_o(core_accept),.native_accept_o(native_accept),.transport_fault_o(transport_fault));
reg [7:0] memory[0:511];reg [255:0] pending_data[0:127];integer due[0:127];integer qin=0,qout=0,base;
reg [255:0] word_value;
always @(posedge memclk)begin
 cycles=cycles+1;mem_response<=0;
 if(!reset_n)begin qin=0;qout=0;end
 else begin
  if(slot_accept[8])slots=slots+1;if(core_accept[8])cores=cores+1;if(native_accept[8])natives=natives+1;
  if(!hold_response && qin!=qout && due[qout%128]<=cycles)begin mem_response<=1;mem_data<=pending_data[qout%128];qout=qout+1;end
  if(app_en)begin
   if(!app_ready || (app_wren && !app_wrdy))$fatal(1,"native acceptance violated readiness");
   if(app_addr[2:0]!=0)$fatal(1,"unaligned native address");
   if(app_wren)begin
    if(app_addr>=29'h0c140000 && app_addr<29'h0c140080)begin
     record_writes=record_writes+1;base=(app_addr-29'h0c140000)*4;
     for(integer b=0;b<32;b=b+1)if(!app_mask[b])memory[base+b]=app_data[b*8+:8];
    end
   end else begin
    word_value={8{32'hcafe1234}};
    if(app_addr>=29'h0c140000 && app_addr<29'h0c140080)begin
     record_reads=record_reads+1;base=(app_addr-29'h0c140000)*4;
     for(integer b=0;b<32;b=b+1)word_value[b*8+:8]=memory[base+b];
    end
    if(qin-qout>=128)$fatal(1,"fixture return overflow");
    pending_data[qin%128]=word_value;due[qin%128]=cycles+9;qin=qin+1;
   end
  end
 end
end
function automatic [31:0] pair(input integer n);
 reg [15:0] l,r;
 begin l=16'h1234+n*73;r=16'had98^(n*109);pair={r,l};end
endfunction
function automatic [7:0] expected_byte(input integer n);
 reg [31:0] p;
 begin p=pair(n/4);expected_byte=p>>(8*(n%4));end
endfunction
task automatic wait_mem(input integer n);repeat(n)@(negedge memclk);endtask
task automatic bus(input bit wr,input [11:0] address,input [31:0] data,input [3:0] strobes,input bit want_error,output reg [31:0] value);
 integer deadline;
 begin
  @(negedge pclk);psel=1;penable=0;pwrite=wr;paddr=address;pwdata=data;pstrb=strobes;
  @(negedge pclk);penable=1;deadline=cycles+25000;
  while(!pready && cycles<deadline)@(negedge pclk);
  if(!pready)$fatal(1,"APB deadline addr=%h",address);
  if(pslverr!==want_error)$fatal(1,"APB error mismatch addr=%h data=%h got=%b want=%b state=%d failure=%d",address,data,pslverr,want_error,state,failure);
  value=prdata;@(negedge pclk);psel=0;penable=0;pwrite=0;
 end
endtask
reg [31:0] temp;
task automatic wr(input [11:0] address,input [31:0] data);bus(1,address,data,15,0,temp);endtask
task automatic cmd(input integer op);wr(12'h008,op);endtask
task automatic rd32(input [11:0] address,output reg [31:0] data);bus(0,address,0,0,0,data);endtask
task automatic frame(input [31:0] seq,input integer index);
 reg [31:0] p;
 begin p=pair(index);@(negedge srcclk);fv=1;fseq=seq;fpcm={p[15:0],p[31:16]};@(negedge srcclk);fv=0;repeat(9)@(negedge srcclk);end
endtask
task automatic stage(input integer limit);
 begin wr(12'h010,32'h89abcdef);wr(12'h014,32'h01234567);wr(12'h018,limit);end
endtask
task automatic create_object(input integer limit,input integer count);
 begin
  stage(limit);
  fork
   cmd(1);
   begin wait(dut.command_valid && dut.command_address==12'h008);wait_mem(10);
    if(state!=0 || pready)$fatal(1,"CREATE completed before actual frame");
    frame(32'hffffffff,-1);for(integer n=0;n<count;n=n+1)frame(n,n);
   end
  join
 end
endtask
task automatic await_state(input integer want);
 integer deadline;
 begin deadline=cycles+25000;while(state!=want && cycles<deadline)@(negedge memclk);
 if(state!=want)$fatal(1,"state deadline got=%d failure=%d want=%d",state,failure,want);end
endtask
task automatic check_memory(input integer count);
 begin
  for(integer b=0;b<count*4;b=b+1)if(memory[b]!==expected_byte(b))$fatal(1,"PCM stereo/sequence byte mismatch index=%d got=%h expected=%h",b,memory[b],expected_byte(b));
  for(integer b=count*4;b<((count*4+31)/32)*32;b=b+1)if(memory[b]!==8'ha5)$fatal(1,"tail mask clobber index=%d",b);
 end
endtask
task automatic check_download(input integer start,input integer length);
 integer consumed,bytes,deadline,index;reg [31:0] status,word;reg [255:0] snap;
 begin
  wr(12'h040,start);wr(12'h044,length);cmd(7);consumed=0;
  while(consumed<length)begin
   deadline=cycles+25000;status=0;
   while(!status[8] && cycles<deadline)rd32(12'h048,status);
   if(!status[8])$fatal(1,"download valid deadline");
   cmd(8);rd32(12'h048,status);
   if(!status[7])$fatal(1,"snapshot missing");bytes=status[5:0];
   if(bytes==0 || bytes>32 || consumed+bytes>length || status[6]!=(consumed+bytes==length))$fatal(1,"snapshot bytes/last incoherent");
   for(integer i=0;i<8;i=i+1)begin index=(i*3)%8;rd32(12'h04c+index*4,word);snap[index*32+:32]=word;end
   wait_mem(17);rd32(12'h04c,word);if(word!==snap[31:0])$fatal(1,"snapshot changed under slow CPU");
   for(integer b=0;b<bytes;b=b+1)if(snap[b*8+:8]!==expected_byte(start+consumed+b))$fatal(1,"download byte mismatch offset=%d",start+consumed+b);
   cmd(9);consumed=consumed+bytes;
  end
 end
endtask
integer before_slots,before_native,before_reads,deadline;reg [31:0] value;
initial begin
 for(integer b=0;b<512;b=b+1)memory[b]=8'ha5;
 wait_mem(6);reset_n=1;preset_n=1;wait_mem(30);
 if(CASE==0)begin
  wr(12'h010,32'h12345678);bus(1,12'h011,0,15,1,value);bus(1,12'h010,0,1,1,value);rd32(12'h010,value);
  if(value!==32'h12345678)$fatal(1,"invalid APB write changed staging");
  traffic=1;create_object(17,17);await_state(3);
  if(frames!=17 || committed!=17 || !dut.service.quiescent)$fatal(1,"READY before committed drain");
  rd32(12'h024,value);if(value!=44100)$fatal(1,"wrong actual rate");rd32(12'h028,value);if(value!=42)$fatal(1,"wrong actual epoch");
  check_memory(17);cmd(5);check_download(3,58);cmd(6);wait_mem(15);cmd(4);await_state(0);
 end else if(CASE==1)begin
  create_object(64,3);await_state(1);deadline=cycles+100;while(!seal_ready && cycles<deadline)@(negedge ctlclk);
  if(!seal_ready)$fatal(1,"seal admission not ready");
  @(negedge ctlclk);seal_hold=1;seal_request=1;@(negedge ctlclk);seal_request=0;
  deadline=cycles+1000;while(!seal_done && !seal_failed && cycles<deadline)@(negedge ctlclk);
  if(!seal_done && !seal_failed)$fatal(1,"seal request lost when hold asserted with registered request");
  if(seal_failed || state!=3 || frames!=3 || committed!=3)$fatal(1,"normal media seal did not preserve READY object");
  check_memory(3);@(negedge ctlclk);seal_hold=0;
 end else if(CASE==2)begin
  force_stall=1;create_object(64,9);deadline=cycles+500;while(slots==0 && cycles<deadline)@(negedge memclk);
  if(slots!=1 || natives!=0)$fatal(1,"pre-native stall precondition");before_slots=slots;before_native=natives;
  cmd(3);await_state(5);bus(1,12'h008,4,15,1,value);wait_mem(30);
  if(slots!=before_slots || natives!=before_native || !dut.ddr_valid)$fatal(1,"cancel lost/duplicated published command");
  force_stall=0;deadline=cycles+500;while(!dut.service.quiescent && cycles<deadline)@(negedge memclk);wait_mem(10);
  if(natives!=before_native+1 || slots!=before_slots)$fatal(1,"cancel native commit duplicated/lost");cmd(4);await_state(0);
 end else if(CASE==3)begin
  create_object(17,17);await_state(3);check_memory(17);cmd(5);hold_response=1;wr(12'h040,0);wr(12'h044,68);before_reads=record_reads;cmd(7);
  deadline=cycles+500;while(record_reads==before_reads && cycles<deadline)@(negedge memclk);
  if(record_reads!=before_reads+1 || !dut.service.backend.read_outstanding)$fatal(1,"read reset precondition");
  @(negedge pclk);preset_n=0;psel=0;penable=0;wait_mem(20);
  if(state!=3 || !dut.service.reference_held || !dut.service.backend.reference_closing)$fatal(1,"observer reset abandoned object/reference");
  hold_response=0;wait_mem(50);if(dut.service.reference_held || dut.service.backend.discarded_responses_o!=1)$fatal(1,"observer reset stale return was not drained");
  preset_n=1;wait_mem(30);stage(17);cmd(5);check_download(5,31);cmd(6);wait_mem(15);cmd(4);
 end else if(CASE==4)begin
  create_object(1,1);await_state(3);@(negedge memclk);inject_response=1;wait_mem(2);inject_response=0;await_state(4);
  if(failure!=9 || !transport_fault)$fatal(1,"owner ledger fault missing");
  bus(1,12'h008,4,15,1,value);preset_n=0;wait_mem(8);preset_n=1;wait_mem(20);bus(1,12'h008,4,15,1,value);
  if(state!=4 || failure!=9)$fatal(1,"observer reset rearmed sticky transport fault");
 end else if(CASE==5)begin
  stage(64);
  fork
   bus(1,12'h008,1,15,1,value);
   begin wait(dut.command_valid && dut.command_address==12'h008);wait_mem(10);
    @(negedge ctlclk);seal_hold=1;seal_request=1;@(negedge ctlclk);seal_request=0;
   end
  join
  deadline=cycles+1000;while(!seal_done && !seal_failed && cycles<deadline)@(negedge ctlclk);
  if(!seal_done || seal_failed || state!=0)$fatal(1,"pending CREATE survived media seal");
  frame(0,0);wait_mem(30);if(state!=0 || frames!=0)$fatal(1,"late physical frame created object after seal");
  bus(1,12'h008,1,15,1,value);@(negedge ctlclk);seal_hold=0;
 end else if(CASE==6)begin
  stage(64);before_native=cycles;bus(1,12'h008,1,15,1,value);
  if(cycles-before_native<20000 || cycles-before_native>20100 || state!=0 || frames!=0)$fatal(1,"CREATE no-source deadline/state mismatch");
 end else if(CASE==7)begin
  create_object(64,3);f44=0;fepoch=43;frame(3,3);await_state(4);
  if(failure!=3 || dut.service.object_rate!=1 || dut.service.object_epoch!=42 || frames!=3)$fatal(1,"actual stream context changed immutable recording descriptor");
 end else if(CASE==8)begin
  create_object(64,3);force_stall=1;runtime_done=1;ble_done=1;
  deadline=cycles+100;while(!media_ready && cycles<deadline)@(negedge ctlclk);
  if(!media_ready)$fatal(1,"third-owner media admission unavailable");
  @(negedge ctlclk);media_hold=1;media_request=1;@(negedge ctlclk);media_request=0;
  // Old terminal levels at registered owner request delivery cannot complete this transaction.
  @(negedge ctlclk);runtime_done=0;ble_done=0;repeat(4)@(negedge ctlclk);runtime_done=1;
  @(negedge ctlclk);runtime_done=0;repeat(4)@(negedge ctlclk);ble_done=1;@(negedge ctlclk);ble_done=0;
  wait_mem(50);if(media_done || media_failed || state!=2 || committed!=0)$fatal(1,"third-owner media completed before actual DDR drain");
  bus(1,12'h008,1,15,1,value);bus(1,12'h008,3,15,1,value);force_stall=0;
  deadline=cycles+1000;while(!media_done && !media_failed && cycles<deadline)@(negedge ctlclk);
  if(!media_done || media_failed || state!=3 || frames!=3 || committed!=3)$fatal(1,"third-owner media did not await immutable READY");
  check_memory(3);repeat(10)@(negedge ctlclk);if(media_ready)$fatal(1,"third-owner media rearmed while held");
  media_hold=0;deadline=cycles+1000;while(!media_ready && cycles<deadline)@(negedge ctlclk);
  if(!media_ready)$fatal(1,"third-owner media did not rearm after release");
 end else if(CASE==9)begin
  create_object(17,17);await_state(3);cmd(5);wr(12'h040,0);wr(12'h044,68);cmd(7);
  value=0;while(!value[8])rd32(12'h048,value);cmd(8);
  fork
   bus(0,12'h04c,0,0,1,value);
   begin wait(dut.command_valid && dut.command_address==12'h04c);inject_response=1;wait_mem(3);inject_response=0;end
  join
  await_state(4);if(failure!=9 || dut.service.snapshot_available)$fatal(1,"same-edge transport fault exposed stale download snapshot");
 end else if(CASE==10)begin
  create_object(64,3);await_state(4);
  if(failure!=4 || frames!=3)$fatal(1,"source silence did not terminate capture with prefix preserved");
 end else if(CASE==11)begin
  f44=0;fepoch=43;create_object(9,9);await_state(3);check_memory(9);
  rd32(12'h024,value);if(value!=48000)$fatal(1,"48k actual source rate wrong");rd32(12'h028,value);if(value!=43)$fatal(1,"48k actual source epoch wrong");
 end else if(CASE==12)begin
  // Halt destination/controller clock while the physical source has no ready.
  @(negedge memclk);memory_running=0;
  for(integer n=0;n<64;n=n+1)begin
   @(negedge srcclk);fv=1;fseq=n;fpcm=32'h1234ad98;
  end
  @(negedge srcclk);fv=0;memory_running=1;wait_mem(100);
  if(!dut.pcm_loss || dut.drop_count==0)$fatal(1,"actual observation overflow was not sticky");
  fepoch=43;stage(9);
  fork
   bus(1,12'h008,1,15,1,value);
   begin wait(dut.command_valid && dut.command_address==12'h008);wait_mem(5);frame(64,0);end
  join
  if(state!=0)$fatal(1,"pre-recording observation loss admitted CREATE");
  @(negedge pclk);preset_n=0;wait_mem(10);preset_n=1;wait_mem(30);
  if(!dut.pcm_loss)$fatal(1,"CPU observer reset rearmed observation loss");stage(9);
  fork
   bus(1,12'h008,1,15,1,value);
   begin wait(dut.command_valid && dut.command_address==12'h008);wait_mem(5);frame(65,0);end
  join
  if(state!=0)$fatal(1,"observer reset admitted CREATE after sticky loss");
  @(negedge memclk);reset_n=0;preset_n=0;wait_mem(10);reset_n=1;preset_n=1;wait_mem(30);
  if(dut.pcm_loss || dut.drop_count!=0 || transport_fault)$fatal(1,"common controller reset did not restore loss channel");
  create_object(9,9);await_state(3);check_memory(9);
 end else if(CASE==13)begin
  create_object(64,3);force_stall=1;await_state(1);
  deadline=cycles+100;while(!seal_ready && cycles<deadline)@(negedge ctlclk);
  if(!seal_ready)$fatal(1,"observer seal admission not ready");
  @(negedge ctlclk);seal_hold=1;seal_request=1;@(negedge ctlclk);seal_request=0;
  deadline=cycles+100;while(!dut.seal_cdc.destination_pending && cycles<deadline)@(negedge memclk);
  if(!dut.seal_cdc.destination_pending)$fatal(1,"observer seal pending precondition");
  @(negedge pclk);preset_n=0;seal_hold=0;wait_mem(50);
  if(!dut.seal_cdc.source_pending || !dut.seal_cdc.destination_pending || !dut.seal_hold ||
    seal_ready || seal_done || seal_failed || state!=2)
   $fatal(1,"observer reset abandoned pending seal or its hold");
  preset_n=1;force_stall=0;
  deadline=cycles+1000;while(!seal_done && !seal_failed && cycles<deadline)@(negedge ctlclk);
  if(!seal_done || seal_failed || state!=3 || frames!=3 || committed!=3)
   $fatal(1,"observer reset lost real seal terminal or immutable object");
  check_memory(3);deadline=cycles+1000;
  while(!seal_ready && cycles<deadline)@(negedge ctlclk);
  if(!seal_ready)$fatal(1,"observer seal channel did not recover readiness");
 end
 $display("PASS runtime independent case=%0d cycles=%0d slots=%0d cores=%0d natives=%0d writes=%0d reads=%0d",CASE,cycles,slots,cores,natives,record_writes,record_reads);$finish;
end
initial begin #20000000;$fatal(1,"fixture global deadline");end
endmodule
