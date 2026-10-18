#!/usr/bin/env python3
"""Check RTL magnitude squares/wrap/isqrt against independent Python integer math."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    edge = [0, 1, -1, 1023, 1024, -1024, (1 << 47)-1, -(1 << 47), (1 << 46), -(1 << 46)]
    cases = [(a, b) for a in edge for b in edge]
    rng = random.Random(85050)
    cases += [(rng.randrange(-(1 << 47), 1 << 47), rng.randrange(-(1 << 47), 1 << 47)) for _ in range(2000)]
    lines = []
    for a, b in cases:
        magnitude = (((a >> 10)**2) + ((b >> 10)**2)) & ((1 << 64)-1)
        bits = ((a & ((1 << 48)-1)) << 80) | ((b & ((1 << 48)-1)) << 32) | math.isqrt(magnitude)
        lines.append(f'{bits:032x}')
    (out / 'cases.hex').write_text('\n'.join(lines) + '\n')
    tb = out / 'tb.sv'
    tb.write_text(f'''`timescale 1ns/1ps
module tb;
reg clk=0, rst=0;
always #10 clk=~clk;
reg [127:0] cases[0:{len(cases)-1}];
integer i, cycles;
basic_pitch_cqt_engine #(.WIN_LEN(256)) dut (
 .clk_i(clk), .rst_ni(rst), .start_i(1'b0), .octave_limit_i(5'd1), .frame_limit_i(9'd1),
 .win_we_i(1'b0), .win_addr_i(16'd0), .win_data_i(16'd0),
 .kre_data_i(16'd0), .kim_data_i(16'd0), .coeff_valid_i(1'b1), .klp_data_i(16'd0),
 .norm_log_data_i(16'd0), .loglut_data_i(16'd0), .sig_mem_ready_i(1'b0),
 .sig_mem_rsp_valid_i(1'b0), .sig_mem_rdata_i(16'd0));
initial begin
 $readmemh("{out / 'cases.hex'}", cases);
 repeat(4) @(negedge clk); rst=1;
 for(i=0;i<{len(cases)};i=i+1) begin
  @(negedge clk);
  dut.acc_re=cases[i][127:80]; dut.acc_im=cases[i][79:32];
  dut.state=dut.S_SQUARE;
  cycles=0;
  while(dut.state!=dut.S_LOG && cycles<40) begin
   @(negedge clk); cycles=cycles+1;
  end
  if(cycles!=34 || dut.root!==cases[i][31:0])
   $fatal(1,"magnitude case %0d cycles=%0d root=%h expected=%h",i,cycles,dut.root,cases[i][31:0]);
 end
 $display("PASS CQT magnitude Python oracle: {len(cases)} signed48 pairs, low64 wrap, exact unsigned sqrt32");
 $finish;
end
initial begin #2000000; $fatal(1,"timeout"); end
endmodule
''')
    src = ROOT / 'rtl/music/basic_pitch_cqt_engine.sv'
    binary = out / 'tb.vvp'
    result = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-I', str(ROOT / 'rtl/music'),
                             '-o', str(binary), str(src), str(tb)], capture_output=True, text=True)
    log = result.stdout + result.stderr
    if result.returncode == 0:
        result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)
        log += result.stdout + result.stderr
    (out / 'run.log').write_text(log)
    passed = result.returncode == 0 and 'PASS CQT magnitude Python oracle:' in log
    (out / 'result.json').write_text(json.dumps({'passed': passed, 'cases': len(cases),
        'oracle': 'Python exact signed arithmetic / uint64 wrap / math.isqrt',
        'source_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2)+'\n')
    print(log.splitlines()[-1] if passed else log[-3000:])
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
