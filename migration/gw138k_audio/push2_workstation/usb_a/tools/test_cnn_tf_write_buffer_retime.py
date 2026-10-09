#!/usr/bin/env python3
"""Independent TF byte/ring oracle, with original control and native stalls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from cnn_ddr_pipeline_patch import TF_DMA, retime_tf_write_buffer,retime_tf_capture_limit,power_two_tf_ring

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



def buffered_native_tb(tb, stalled):
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
    ports = ['.clk(clk)', '.reset_n(rst_n)', ".bist_done(1'b1)"]
    for client in ['bist','scan','display','audio','music','delay','writer','cpu']:
        live = client == 'audio'
        ports += [f'.{client}_valid(' + ('app_en' if live else "1'b0") + ')',
                  f'.{client}_address(' + ('app_addr' if live else "29'd0") + ')',
                  f'.{client}_ready(' + ('audio_accept' if live else '') + ')']
        if client not in ['scan','display','writer']:
            ports += [f'.{client}_write(' + ('app_wren' if live else "1'b0") + ')']
        if client not in ['scan','display']:
            ports += [f'.{client}_data(' + ('app_wdata' if live else "256'd0") + ')']
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    original = (BASE / TF_DMA).read_text()
    patched = retime_tf_write_buffer(original)
    variants=[('original_control', original), ('retimed', patched),('registered_limit',retime_tf_capture_limit(patched)),('power_two_ring',power_two_tf_ring(retime_tf_capture_limit(patched)))]
    cases = []
    with tempfile.TemporaryDirectory(prefix='cnn_tf_stage_retime_') as temp:
        folder = Path(temp)
        for label, text in variants:
            src = folder / 'dma.v'
            src.write_text(text)
            for buffered,stalled in [(False,False),(False,True),(True,False),(True,True)]:
                tb = '`timescale 1ns/1ps\n' + (ROOT / 'sim/tf_audio/tb_tf_audio_ddr_dma.sv').read_text()
                if buffered:
                    tb = buffered_native_tb(tb,stalled)
                elif stalled:
                    tb = stalled_tb(tb)
                test = folder / 'tb.sv'
                test.write_text(tb)
                exe = folder / 'sim'
                compile_result = subprocess.run([
                    'iverilog', '-g2012', '-I', str(BASE), '-s',
                    'tb_tf_audio_ddr_dma', '-o', str(exe), str(src), str(test)
                ] + ([str(ROOT/'rtl/music/basic_pitch_ddr_arbiter_pipeline.sv'),str(ROOT/'rtl/music/basic_pitch_ddr_client_queues.sv')] if buffered else []), capture_output=True, text=True)
                assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
                result = subprocess.run(['vvp', str(exe)], capture_output=True,
                                        text=True, timeout=30)
                assert result.returncode == 0 and 'PASS' in result.stdout, result.stdout + result.stderr
                cases.append(dict(source=label, buffered_native=buffered,native_backpressure=stalled,
                                  passed=True, log=result.stdout.strip()))
    report = dict(passed=True, hardware_tested=False, pcm_saved=False, cases=cases,
                  variant_source_sha256={label:hashlib.sha256(text.encode()).hexdigest() for label,text in variants},
                  staged_source_sha256=hashlib.sha256(patched.encode()).hexdigest(),
                  original_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                  arbiter_sha256=hashlib.sha256((ROOT/'rtl/music/basic_pitch_ddr_arbiter_pipeline.sv').read_bytes()).hexdigest(),
                  client_queues_sha256=hashlib.sha256((ROOT/'rtl/music/basic_pitch_ddr_client_queues.sv').read_bytes()).hexdigest())
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
