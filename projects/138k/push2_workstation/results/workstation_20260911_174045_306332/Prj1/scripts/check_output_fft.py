"""Compare every complex RTL FFT bin with an independent floating-point DFT.

Uses Python's standard library only. The oracle is the direct Fourier sum,
not the HDL butterfly schedule, address order or quantization implementation.
Run with Icarus available (WSL). Evidence is simulation, not a board capture.
"""
from pathlib import Path
import cmath
import hashlib
import json
import math
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/fft_reference"

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(9031024)
    left, right = [], []
    for n in range(1024):
        l = .43*math.sin(2*math.pi*15.25*n/1024)+.12*math.cos(2*math.pi*147*n/1024)+rng.uniform(-.03,.03)
        r = .29*math.cos(2*math.pi*37.375*n/1024)+.17*math.sin(2*math.pi*289.5*n/1024)+rng.uniform(-.04,.04)
        left.append(round(l*32767)); right.append(round(r*32767))
    (OUT / "pcm.hex").write_text("".join(f"{l&65535:04x}{r&65535:04x}\n" for l,r in zip(left,right)))
    bench = '''`timescale 1ns/1ps
module fft_reference;
reg clk=0,source_clk=0,reset_n=0,valid=0;
always #5 clk=~clk;always #11 source_clk=~source_clk;
reg [31:0] pair=0,stimulus[0:1023];wire ready;
output_audio_analysis dut(.clk(clk),.reset_n(reset_n),.source_clk(source_clk),.source_reset_n(reset_n),
.pcm_pair(pair),.sample_valid(valid),.release_frame(1'b0),.ready(ready),.peak_left(),.peak_right(),
.image_gain(),.sequence_data(),.skipped_data(),.display_read_enable(1'b0),.spectrum_column(9'd0),
.image_addr(16'd0),.spectrum_left(),.spectrum_right(),.image_hit());
integer i,j,fdl,fdr;reg dumped=0;
always @(negedge clk) if(dut.state==14 && !dut.channel && dut.index==0 && !dumped) begin
for(j=0;j<1024;j=j+1) $fwrite(fdl,"%h %h\\n",dut.real_ram[j],dut.imag_ram[j]);
$fclose(fdl);dumped=1;
end
initial begin
$readmemh("pcm.hex",stimulus);fdl=$fopen("left_fft.txt","w");fdr=$fopen("right_fft.txt","w");
repeat(4) @(negedge source_clk);reset_n=1;
for(i=0;i<1024;i=i+1) begin @(negedge source_clk);pair=stimulus[i];valid=1;end
@(negedge source_clk);valid=0;wait(ready);
for(i=0;i<1024;i=i+1) $fwrite(fdr,"%h %h\\n",dut.real_ram[i],dut.imag_ram[i]);
$fclose(fdr);if(!dumped)$fatal(1,"missing left transform");
$display("PASS complex RTL transform export");$finish;
end
initial begin #3000000;$fatal(1,"FFT timeout");end
endmodule
'''
    (OUT / "fft_reference.sv").write_text(bench)
    sources = [ROOT / "src/video" / n for n in ("output_audio_analysis.v", "output_audio_capture.v", "audio_analysis_rom.v")]
    subprocess.run(["iverilog", "-g2012", "-s", "fft_reference", "-o", "fft.vvp", *map(str,sources), "fft_reference.sv"], cwd=OUT, check=True)
    result = subprocess.run(["vvp", "fft.vvp"], cwd=OUT, text=True, capture_output=True, timeout=180)
    (OUT / "simulation.log").write_text(result.stdout+result.stderr)
    assert result.returncode == 0 and "PASS " in result.stdout, result.stdout+result.stderr
    def signed(word):
        v = int(word,16)
        return v-(1<<24) if v & (1<<23) else v
    def dft(samples):
        windowed = [v*.5*(1-math.cos(2*math.pi*n/1024)) for n,v in enumerate(samples)]
        result = []
        for k in range(1024):
            step = cmath.exp(-2j*math.pi*k/1024)
            phase = 1+0j
            total = 0j
            for value in windowed:
                total += value*phase
                phase *= step
            result.append(total/16) # FFT/N and six retained fractional bits
        return result
    report = {"board_tested": False, "reference": "Direct floating-point DFT with ideal periodic Hann", "points_per_channel": 1024,
              "sample_rate_hz": 48828.125, "bin_spacing_hz": 48828.125/1024, "fractional_guard_bits": 6,
              "fixture": "Independent L/R fractional-bin and integer-bin multitone mixtures with deterministic noise", "channels": {}}
    for name,samples in (("left",left),("right",right)):
        observed = [complex(*(signed(word) for word in line.split())) for line in (OUT/f"{name}_fft.txt").read_text().splitlines()]
        expected = dft(samples)
        assert len(observed)==1024
        errors = [abs(a-b) for a,b in zip(observed,expected)]
        assert max(errors)<64, (name,max(errors))
        report["channels"][name] = {"bins_checked": 1024, "maximum_complex_error_guard_units": max(errors),
                                     "rms_complex_error_guard_units": math.sqrt(sum(e*e for e in errors)/1024),
                                     "error_limit_guard_units": 64}
    paths = sources+[Path(__file__),OUT/"pcm.hex",OUT/"fft_reference.sv",OUT/"left_fft.txt",OUT/"right_fft.txt",OUT/"simulation.log"]
    report["sha256"] = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (OUT/"comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="sha256"},indent=2))
    print("PASS all 2048 complex bins against independent direct DFT")

if __name__=="__main__":
    main()
