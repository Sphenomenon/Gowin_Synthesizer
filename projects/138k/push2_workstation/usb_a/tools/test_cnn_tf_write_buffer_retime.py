#!/usr/bin/env python3
"""Independent TF byte/ring oracle, with original control and native stalls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from cnn_ddr_pipeline_patch import TF_BUFFER,TF_DMA, retime_tf_write_buffer,retime_tf_capture_limit,power_two_tf_ring,parallel_tf_byte_counters,retime_tf_read_total,fast_tf_read_availability,mask_tf_write_epoch,registered_tf_read_response,pipeline_tf_read_return,nibble_tf_byte_counters

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'


def stalled_tb(tb):
    # Pre-accept read requests may be replaced by the client's higher-priority
    # write request. Read wdata is don't-care. Only an unaccepted write beat
    # must preserve its address/data; the shared arbiter separately tests the
    # stable native command AFTER acceptance into its register.
    anchor = '    localparam integer MAX_SOURCE'
    assert tb.count(anchor) == 1
    tb = tb.replace(anchor, '''    reg [31:0] cycle=0;
    always @(posedge clk) cycle<=cycle+1;
    wire native_ready=cycle%11>3;
    wire native_wrdy=cycle%17>5;
    reg write_stalled=0;
    reg [284:0] held_write;
    always @(posedge clk) begin
        if(!rst_n || dut.restart_event) write_stalled=0;
        else begin
            if(write_stalled && (!app_en || !app_wren ||
                {app_addr,app_wdata}!==held_write))
                $fatal(1,"unaccepted write beat changed under stall");
            write_stalled=app_en && app_wren && !(native_ready && native_wrdy);
            held_write={app_addr,app_wdata};
        end
    end
''' + anchor, 1)
    tb = tb.replace(".app_rdy(1'b1)", '.app_rdy(native_ready)')
    tb = tb.replace(".app_wrdy(1'b1)", '.app_wrdy(native_wrdy)')
    tb = tb.replace('if (app_en && app_wren)',
                    'if (app_en && app_wren && native_ready && native_wrdy)')
    return tb.replace('if (app_en && !app_wren)',
                      'if (app_en && !app_wren && native_ready)')



def buffered_native_tb(tb, stalled, full_buffered=False):
    # Keep the real client interface and memory oracle separate: the TF FSM
    # sees its local request slot, while the memory accepts native commands
    # after stable selection, physical backpressure and response tagging.
    tb = tb.replace("    reg app_rvalid = 1'b0;", "    wire app_rvalid;")
    tb = tb.replace("    reg [255:0] app_rdata = 256'd0;", "    wire [255:0] app_rdata;")
    native = ["    wire audio_accept;", "    wire [2:0] native_cmd;",
              "    wire native_en,native_wren,native_wend,arbiter_fault;",
              "    wire [28:0] native_addr;wire [255:0] native_wdata;",
              "    wire [31:0] native_mask;reg native_rvalid=0;",
              "    reg [255:0] native_rdata=0;reg [31:0] cycles=0;",
              "    always @(posedge clk)cycles<=cycles+1;"]
    native += ["    wire native_ready=" + ("cycles%11>3" if stalled else "1'b1") + ";",
               "    wire native_wrdy=" + ("cycles%17>5" if stalled else "1'b1") + ";"]
    if full_buffered:
        native += ['    wire queue_valid,queue_write,queue_ready;',
                   '    wire [28:0] queue_address;wire [255:0] queue_data;',
                   '    tf_audio_ddr_command_buffer command_buffer(',
                   '        .clk(clk),.rst_n(rst_n),.in_valid(app_en),.in_write(app_wren),',
                   '        .in_address(app_addr),.in_data(app_wdata),.in_ready(audio_accept),',
                   '        .out_valid(queue_valid),.out_write(queue_write),',
                   '        .out_address(queue_address),.out_data(queue_data),.out_ready(queue_ready));']
    live_valid='queue_valid' if full_buffered else 'app_en'
    live_address='queue_address' if full_buffered else 'app_addr'
    live_ready='queue_ready' if full_buffered else 'audio_accept'
    live_write='queue_write' if full_buffered else 'app_wren'
    live_data='queue_data' if full_buffered else 'app_wdata'
    ports = ['.clk(clk)', '.reset_n(rst_n)', ".bist_done(1'b1)"]
    for client in ['bist','scan','display','audio','music','delay','writer','cpu']:
        live = client == 'audio'
        ports += [f'.{client}_valid(' + (live_valid if live else "1'b0") + ')',
                  f'.{client}_address(' + (live_address if live else "29'd0") + ')',
                  f'.{client}_ready(' + (live_ready if live else '') + ')']
        if client not in ['scan','display','writer']:
            ports += [f'.{client}_write(' + (live_write if live else "1'b0") + ')']
        if client not in ['scan','display']:
            ports += [f'.{client}_data(' + (live_data if live else "256'd0") + ')']
        if client in ['music','cpu']:
            ports += [f".{client}_mask(32'd0)"]
        if client != 'writer':
            ports += [f'.{client}_response(' + ('app_rvalid' if live else '') + ')']
    for port in ['cmd','en','wren','wend','address','data','mask','ready','write_ready','response','response_data']:
        value={'address':'addr','data':'wdata','write_ready':'wrdy',
               'response':'rvalid','response_data':'rdata'}.get(port,port)
        ports += ['.app_' + port + '(native_' + value + ')']
    ports += ['.response_data(app_rdata)', '.response_fault(arbiter_fault)']
    native += ['    basic_pitch_ddr_client_queues arbiter(' + ','.join(ports) + ');',
               '    always @(posedge clk)if(rst_n && arbiter_fault)$fatal(1,"TF native tag fault");']
    tb = tb.replace('    localparam integer MAX_SOURCE', '\n'.join(native) + '\n    localparam integer MAX_SOURCE', 1)
    tb = tb.replace(".app_rdy(1'b1)", '.app_rdy(audio_accept)')
    tb = tb.replace(".app_wrdy(1'b1)", '.app_wrdy(audio_accept)')
    start = tb.index("    reg read_pending = 1'b0;")
    memory = tb[start:]
    for source, dest in [('app_addr','native_addr'),('app_wdata','native_wdata'),
                         ('app_rvalid','native_rvalid'),('app_rdata','native_rdata'),
                         ('app_en','native_en'),('app_wren','native_wren')]:
        memory = memory.replace(source,dest)
    return tb[:start] + memory


def inflight_restart_tb(tb):
    # Restart after the TF command has entered its local slot, before its
    # tagged registered response returns. New input starts only after drain;
    # do not assert app_rvalid implies pending across an epoch cancellation.
    anchor='        $display("PASS tb_tf_audio_ddr_dma:'
    assert tb.count(anchor)==1
    scenario="""        restart_epoch;
        fork
            start_capture(32,8'h35);
            begin
                wait(dut.read_accept);
                @(negedge clk);restart_toggle=~restart_toggle;
            end
        join
        repeat(32)@(posedge clk);
        if(dut.read_pending || dut.read_buf_valid || output_count!=0)
            $fatal(1,"canceled read leaked old epoch bytes pending=%b valid=%b out=%0d",
                   dut.read_pending,dut.read_buf_valid,output_count);
        restart_epoch;
        start_capture(65,8'h93);
        wait_done_and_check(65,8'h93);
        check_ring_addresses(3);
"""
    return tb.replace(anchor,scenario+anchor,1)


def zero_response_tb(tb,stalled):
    if stalled:tb=stalled_tb(tb)
    tb=tb.replace("    reg app_rvalid = 1'b0;","    wire app_rvalid;")
    tb=tb.replace("    reg [255:0] app_rdata = 256'd0;","    reg [255:0] app_rdata;")
    tb=tb.replace("        app_rvalid <= 1'b0;",'')
    old="        if (read_pending) begin\n            app_rvalid <= 1'b1;\n            app_rdata <= read_data_q;\n        end"
    assert tb.count(old)==1;tb=tb.replace(old,'')
    ready='native_ready' if stalled else "1'b1"
    anchor='    always @(posedge clk) begin'
    assert tb.count(anchor)>=1
    return tb.replace(anchor,"    assign app_rvalid=app_en && !app_wren && "+ready+";\n    always @* lookup_latest(app_addr,app_rdata);\n"+anchor,1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--parallel-byte-counters',action='store_true')
    parser.add_argument('--build',type=Path)
    parser.add_argument('--retime-read-total',action='store_true')
    parser.add_argument('--fast-read-availability',action='store_true')
    parser.add_argument('--mask-write-epoch',action='store_true')
    parser.add_argument('--registered-response',action='store_true')
    parser.add_argument('--pipeline-read-return',action='store_true')
    parser.add_argument('--nibble-counters',action='store_true')
    parser.add_argument('--full-buffered-topology',action='store_true',help='include frozen TF command buffer ahead of real client queues/native pipeline')
    args = parser.parse_args()
    original = (BASE / TF_DMA).read_text()
    patched = retime_tf_write_buffer(original)
    variants=[('original_control', original), ('retimed', patched),('registered_limit',retime_tf_capture_limit(patched)),('power_two_ring',power_two_tf_ring(retime_tf_capture_limit(patched)))]
    if args.parallel_byte_counters:variants.append(('parallel_byte_counters',parallel_tf_byte_counters(variants[-1][1])))
    if args.retime_read_total:
        assert args.parallel_byte_counters
        variants.append(('prepared_read_total',retime_tf_read_total(variants[-1][1])))
    if args.fast_read_availability:
        assert args.retime_read_total
        variants.append(('grouped_read_availability',fast_tf_read_availability(variants[-1][1])))
    if args.mask_write_epoch:
        assert args.fast_read_availability
        variants.append(('masked_write_epoch',mask_tf_write_epoch(variants[-1][1])))
    if args.registered_response:
        assert args.mask_write_epoch
        variants.append(('registered_response',registered_tf_read_response(variants[-1][1])))
    if args.pipeline_read_return:
        assert args.mask_write_epoch and not args.registered_response
        variants.append(('pipelined_read_return',pipeline_tf_read_return(variants[-1][1])))
    if args.nibble_counters:
        assert args.parallel_byte_counters
        variants.append(('nibble_counters',nibble_tf_byte_counters(variants[-1][1])))
    if args.build:
        assert args.parallel_byte_counters and (args.build/'Prj1'/TF_DMA).read_text()==variants[-1][1],'frozen TF source differs from tested variant'
    bus_root=args.build/'Prj1/rtl/music' if args.build else ROOT/'rtl/music'
    arbiter_source=bus_root/'basic_pitch_ddr_arbiter_pipeline.sv'
    client_queues_source=bus_root/'basic_pitch_ddr_client_queues.sv'
    tf_buffer_source=args.build/'Prj1'/TF_BUFFER if args.build else ROOT/'rtl/display_data/tf_audio_ddr_command_buffer.sv'
    cases = []
    with tempfile.TemporaryDirectory(prefix='cnn_tf_stage_retime_') as temp:
        folder = Path(temp)
        for label, text in variants:
            src = folder / 'dma.v'
            src.write_text(text)
            cases_for_source=[(True,False,False),(True,True,False)] if label=='registered_response' else [(False,False,False),(False,True,False),(True,False,False),(True,True,False)]+([(False,False,True),(False,True,True)] if args.retime_read_total else [])
            for buffered,stalled,zero in cases_for_source:
                tb = '`timescale 1ns/1ps\n' + (ROOT / 'sim/tf_audio/tb_tf_audio_ddr_dma.sv').read_text()
                if zero:
                    tb = zero_response_tb(tb,stalled)
                elif buffered:
                    tb = buffered_native_tb(tb,stalled,args.full_buffered_topology)
                    if args.full_buffered_topology:tb=inflight_restart_tb(tb)
                elif stalled:
                    tb = stalled_tb(tb)
                if label=='registered_response':
                    tb=tb.replace('    initial begin', '    always @(posedge clk)if(rst_n && app_rvalid && dut.read_accept && !dut.read_pending)$fatal(1,\"new read got impossible same-cycle registered return\");\n    initial begin',1)
                test = folder / 'tb.sv'
                test.write_text(tb)
                exe = folder / 'sim'
                compile_result = subprocess.run([
                    'iverilog', '-g2012', '-I', str(BASE), '-s',
                    'tb_tf_audio_ddr_dma', '-o', str(exe), str(src), str(test)
                ] + ([str(arbiter_source),str(client_queues_source)]+([str(tf_buffer_source)] if args.full_buffered_topology else []) if buffered else []), capture_output=True, text=True)
                assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
                result = subprocess.run(['vvp', str(exe)], capture_output=True,
                                        text=True, timeout=30)
                assert result.returncode == 0 and 'PASS' in result.stdout, result.stdout + result.stderr
                cases.append(dict(source=label, buffered_native=buffered,native_backpressure=stalled,
                                  zero_cycle_response=zero,full_buffered_topology=buffered and args.full_buffered_topology,inflight_restart=buffered and args.full_buffered_topology,passed=True, log=result.stdout.strip()))
    report = dict(passed=True,source_bound=bool(args.build),build=str(args.build) if args.build else None, hardware_tested=False, pcm_saved=False, cases=cases,
                  variant_source_sha256={label:hashlib.sha256(text.encode()).hexdigest() for label,text in variants},
                  staged_source_sha256=hashlib.sha256(patched.encode()).hexdigest(),
                  original_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                  arbiter_source=str(arbiter_source),arbiter_sha256=hashlib.sha256(arbiter_source.read_bytes()).hexdigest(),
                  client_queues_source=str(client_queues_source),client_queues_sha256=hashlib.sha256(client_queues_source.read_bytes()).hexdigest(),
                  tf_command_buffer_source=str(tf_buffer_source) if args.full_buffered_topology else None,
                  tf_command_buffer_sha256=hashlib.sha256(tf_buffer_source.read_bytes()).hexdigest() if args.full_buffered_topology else None)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
