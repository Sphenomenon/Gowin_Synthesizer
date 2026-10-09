#!/usr/bin/env python3
"""Full coefficient CRC through NOR/internal UART/native DDR pipeline with contention."""
from pathlib import Path
import argparse,subprocess,tempfile,json,hashlib,threading
from build_cnn_flash_image import build_image,load_words
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'rtl/music'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,help='use the frozen full-workstation RTL; only RX baud is accelerated for the full-content case');p.add_argument('--output',type=Path);p.add_argument('--buffered-clients',action='store_true');a=p.parse_args()
if a.build:
 SRC=a.build.resolve()/'Prj1/rtl/music'
 meta=json.loads((a.build/'build_metadata.json').read_text())
 assert meta['full_workstation'] and meta['buffered_ddr_clients']==a.buffered_clients
original=(ROOT/'sim/model_flash/tb_flash_serial_boot.sv').read_text()
start=original.index('    wire ready=(cycles%19')
end=original.index('    reg held=0;',start)
text=original[:start]+'''    wire ready,rsp;wire [15:0] rdata;
    wire credit,nreq,nwrite,nready,nresponse;
    wire [28:0] naddr;wire [255:0] ndata,nread;wire [31:0] nmask;
    wire [2:0] app_cmd;wire app_en,app_wr;wire [28:0] app_addr;
    wire [255:0] app_data,client_data;wire [31:0] app_mask;
    reg app_rsp=0;reg [255:0] app_return=0;
    wire arb_fault;
    basic_pitch_ddr_read_credit credit_guard(.clk_i(clk),.rst_ni(rst_n),
        .fifo_ready_i(1'b1),.read_accept_i(ready && !wr),.response_valid_i(rsp),.credit_o(credit));
    basic_pitch_ddr16_port port(.clk_i(clk),.rst_ni(rst_n),
        .req_valid_i(req && (wr || credit)),.req_write_i(wr),.req_byte_addr_i(addr),
        .req_wdata_i(wdata),.req_ready_o(ready),.rsp_valid_o(rsp),.rsp_rdata_o(rdata),
        .ddr_req_o(nreq),.ddr_write_o(nwrite),.ddr_address_o(naddr),
        .ddr_data_o(ndata),.ddr_mask_o(nmask),.ddr_ready_i(nready),
        .ddr_response_i(nresponse),.ddr_read_data_i(client_data));
    basic_pitch_ddr_arbiter_pipeline arbiter(.clk(clk),.reset_n(rst_n),.bist_done(1'b1),
        .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),.bist_ready(),.bist_response(),
        .scan_valid(cycles%23==0),.scan_address(29'h800),.scan_ready(),.scan_response(),
        .display_valid(1'b0),.display_address(29'd0),.display_ready(),.display_response(),
        .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),.audio_ready(),.audio_response(),
        .music_valid(nreq),.music_write(nwrite),.music_address(naddr),.music_data(ndata),.music_mask(nmask),.music_ready(nready),.music_response(nresponse),
        .delay_valid(1'b0),.delay_write(1'b0),.delay_address(29'd0),.delay_data(256'd0),.delay_ready(),.delay_response(),
        .writer_valid(cycles%17==0),.writer_address(29'h1000),.writer_data(256'hc0ffee),.writer_ready(),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
        .app_cmd(app_cmd),.app_en(app_en),.app_wren(app_wr),.app_wend(),.app_address(app_addr),.app_data(app_data),.app_mask(app_mask),
        .app_ready(cycles%13>=3),.app_write_ready(cycles%19>=4),.app_response(app_rsp),
        .app_response_data(app_return),.response_data(client_data),.response_fault(arb_fault));
    localparam integer BLOCKS=(WORDS+15)/16;
    reg [255:0] physical[0:BLOCKS-1];
    reg [255:0] response_queue[0:255];
    integer resp_in=0,resp_out=0,physical_writes=0;
    always @(posedge clk)begin
        app_rsp<=0;
        if(!rst_n)begin resp_in=0;resp_out=0;physical_writes=0;end
        else begin
            if(arb_fault)$fatal(1,"shared native response fault");
            if(resp_out!=resp_in && cycles%11>=2)begin
                app_rsp<=1;app_return<=response_queue[resp_out%256];resp_out=resp_out+1;
            end
            if(app_en)begin
                if(app_addr>=(`BP_DDR_NN_MODEL_BYTE_BASE>>2) &&
                   app_addr<(`BP_DDR_NN_MODEL_BYTE_BASE>>2)+8*BLOCKS)begin
                    if(app_wr)begin
                        for(integer k=0;k<32;k=k+1)if(!app_mask[k])
                            physical[(app_addr-(`BP_DDR_NN_MODEL_BYTE_BASE>>2))>>3][8*k+:8]<=app_data[8*k+:8];
                        physical_writes=physical_writes+1;
                    end else begin
                        response_queue[resp_in%256]=physical[(app_addr-(`BP_DDR_NN_MODEL_BYTE_BASE>>2))>>3];resp_in=resp_in+1;
                    end
                end else if(!app_wr)begin response_queue[resp_in%256]=256'h5ca1;resp_in=resp_in+1;end
            end
        end
    end
'''+original[end:]
start=text.index('    always @(posedge clk) begin\n        cycles<=cycles+1;')
end=text.index('    task send_byte',start)
text=text[:start]+'''    always @(posedge clk)begin
        cycles<=cycles+1;
        if(!rst_n)begin writes<=0;reads<=0;held<=0;end
        else begin
            if(held && {wr,addr,wdata}!==held_cmd)$fatal(1,"model command changed under backpressure");
            held<=req && !ready;held_cmd<={wr,addr,wdata};
            if(req && ready)begin
                if(wr)begin
                    if(addr!==`BP_DDR_NN_MODEL_BYTE_BASE+2*writes)$fatal(1,"write skipped/repeated");
                    memory[writes]<=wdata;writes<=writes+1;
                end else begin
                    if(addr!==`BP_DDR_NN_MODEL_BYTE_BASE+2*reads)$fatal(1,"read skipped/repeated");
                    reads<=reads+1;
                end
            end
            if(done && (expected!==actual || writes!=physical_writes))$fatal(1,"premature model commit");
        end
    end
'''+text[end:]
# Existing NOR/UART success oracle and full coefficient expected/actual CRC
# checks remain exact, now driven by physical masked native-memory responses.
if a.buffered_clients:text=text.replace('basic_pitch_ddr_arbiter_pipeline arbiter(', 'basic_pitch_ddr_client_queues arbiter(')
text=text.replace('    initial begin #1500000000;', '    always @(posedge clk) if(WORDS>100 && cycles!=0 && cycles%4000000==0) begin $display("progress cycles=%0d status=%h bridge=%0d writes=%0d reads=%0d",cycles,status,bridge_state,writes,reads);$fflush();end\n    initial begin #1500000000;')
parser_original=(SRC/'basic_pitch_uart_model_loader.sv').read_text()
frozen_parser='parameter integer BAUD' not in parser_original
if frozen_parser:
 anchor='basic_pitch_uart_model_loader #(.WORDS(WORDS),.BAUD(BAUD)) parser ('
 assert text.count(anchor)==1
 text=text.replace(anchor,'basic_pitch_uart_model_loader #(.WORDS(WORDS)) parser (')
cases=[];simulation_overrides=[];original_sources=[]
with tempfile.TemporaryDirectory(prefix='cnn_flash_native_pipeline_') as tmp:
 tb=Path(tmp)/'tb.sv';tb.write_text(text)
 for words,baud in [(31,115200),(52239,3125000)]:
  vals=load_words(SRC/'weights/cnn_ddr_blob.mem') if words==52239 else [(i*7919^0xa53c)&65535 for i in range(words)]
  image,manifest=build_image(vals);model=Path(tmp)/'geometry_coefficients.hex';model.write_text('\n'.join(f'{b:02x}' for b in image)+'\n')
  exe=Path(tmp)/'sim'
  sources=[tb]+[SRC/n for n in ('basic_pitch_flash_serial_boot.sv','basic_pitch_flash_model_loader.sv','basic_pitch_flash_io_guard.sv','basic_pitch_uart_model_loader.sv','basic_pitch_uart_rx.sv','basic_pitch_ddr16_port.sv','basic_pitch_ddr_read_credit.sv','basic_pitch_ddr_arbiter_pipeline.sv')]+[ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1/src/control/uart_tx.v']
  if a.buffered_clients:sources.append(SRC/'basic_pitch_ddr_client_queues.sv')
  original_sources=list(sources)
  if frozen_parser:
   anchor='.CLK_HZ(50_000_000), .BAUD(115200)'
   assert parser_original.count(anchor)==1
   parser_text=parser_original.replace(anchor,f'.CLK_HZ(50_000_000), .BAUD({baud})')
   parser_temp=Path(tmp)/'frozen_parser.sv';parser_temp.write_text(parser_text)
   sources=[parser_temp if path==SRC/'basic_pitch_uart_model_loader.sv' else path for path in sources]
   simulation_overrides.append(dict(words=words,baud=baud,kind='UART RX instance baud only',
    original_sha256=hashlib.sha256(parser_original.encode()).hexdigest(),
    simulated_sha256=hashlib.sha256(parser_text.encode()).hexdigest(),
    unchanged=parser_text==parser_original))
  c=subprocess.run(['iverilog' ,'-g2012','-I',str(SRC),'-s','tb_flash_serial_boot',f'-Ptb_flash_serial_boot.WORDS={words}',f'-Ptb_flash_serial_boot.BAUD={baud}','-o',str(exe)]+list(map(str,sources)),capture_output=True,text=True)
  assert c.returncode==0,c.stdout+c.stderr
  run=subprocess.Popen(['vvp',str(exe),f'+IMAGE={model}','+CASE=0'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  timer=threading.Timer(1200,run.kill);timer.start();lines=[]
  try:
   for line in run.stdout:lines.append(line);print(line.strip(),flush=True)
   run.wait()
  finally:timer.cancel()
  log=''.join(lines)
  assert run.returncode==0 and 'PASS serial' in log,log
  cases.append(dict(words=words,baud=baud,payload_crc32=manifest['payload_crc32'],passed=True,log=log.strip()))
report=dict(passed=True,frozen_build=str(a.build) if a.build else None,simulation_overrides=simulation_overrides,buffered_clients=a.buffered_clients,cases=cases,hardware_tested=False,pcm_saved=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in original_sources if p.is_relative_to(ROOT)},scope='NOR -> two-pass internal UART -> original parser -> DDR16/credit -> registered shared arbiter -> independent masked native memory; concurrent scan/writer and native stalls')
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
