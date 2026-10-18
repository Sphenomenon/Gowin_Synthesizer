#!/usr/bin/env python3
"""Render the actual feedback RTL with a labeled synthetic test vector.

Run where iverilog/vvp exist (e.g. WSL). Produces PNG without Pillow. This is
an RTL layout fixture, never a hardware capture or evidence of DDR operation.
"""
from pathlib import Path
import argparse
import math
import shutil
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "feedback_preview"


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", action="store_true", help="render a rejected second capture with the explicit HOLD label")
    parser.add_argument("--analysis", action="store_true", help="render final-PCM FFT and stereo image layout")
    args = parser.parse_args()
    for tool in ("iverilog", "vvp"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} required; run this script using Python in WSL")
    OUT.mkdir(parents=True, exist_ok=True)
    samples = [round((.625 * math.sin(2 * math.pi * n / 64) + .125 * math.sin(6 * math.pi * n / 64)) * (2**31 - 1)) for n in range(512)]
    pairs = []
    for n, value in enumerate(samples):
        left = max(-32768, min(32767, (value + (32767 if value < 0 else 32768)) >> 16))
        right = round(.35 * math.sin(2 * math.pi * n / 128 + .6) * 32767)
        pairs.append(((left & 65535) << 16) | (right & 65535))
        if args.analysis:
            samples[n] = (left + right) << 15
    (OUT / "pcm.hex").write_text("".join(f"{value:08x}\n" for value in pairs), encoding="ascii")
    (OUT / "samples.hex").write_text("".join(f"{value & 0xffffffff:08x}\n" for value in samples), encoding="ascii")
    # Use relative paths so Verilog strings never contain Windows backslashes.
    (OUT / "preview.sv").write_text('''`timescale 1ns/1ps
module preview;
localparam integer HOLD_PREVIEW=HOLD_MODE_VALUE;
localparam integer ANALYSIS_PREVIEW=ANALYSIS_MODE_VALUE;
reg clk=0, source_clk=0, reset_n=0, start=0, sample_valid=0;
always #5 clk=~clk;
always #10 source_clk=~source_clk;
reg [31:0] stimulus[0:511];
reg [31:0] saved_wave[0:511];
reg [31:0] pcm_stimulus[0:511],output_pcm=0;
reg [31:0] sample_data=0;
wire frame_ready,busy,frame_done,pixel_valid;
wire [63:0] pixels;
integer fd,i,count=0,cycles=0,start_cycle=0,pass_index=0;
feedback_renderer #(.ENABLE_ANALYSIS(ANALYSIS_PREVIEW)) dut(.clk(clk),.rst_n(reset_n),.start(start),.frame_ready(frame_ready),.busy(busy),.frame_done(frame_done),
.pixel_valid(pixel_valid),.pixel_ready(1'b1),.pixel_data(pixels),.source_clk(source_clk),.source_reset_n(reset_n),
.sample_data(sample_data),.sample_valid(sample_valid),.output_pcm(output_pcm),.active_voices(32'h80010005),.status_data(32'h00000000),
.trigger_reference(ANALYSIS_PREVIEW ? 32'd3 : 32'd0),
.memory_status(32'h3),.underruns(32'h0),.frame_count(32'h75));
generate if(ANALYSIS_PREVIEW) begin
    integer image_i;
    always @(negedge clk) if(HOLD_PREVIEW && pass_index==1 && frame_ready && !busy) begin
        if(dut.peak_left!==16'd16384 || dut.peak_right!==16'd16384)
            $fatal(1,"HOLD did not update stereo peaks");
        for(image_i=0;image_i<65536;image_i=image_i+1)
            if(dut.g_analysis.u_analysis.image_pixels[image_i] !== (image_i==16512))
                $fatal(1,"HOLD stereo image did not refresh to the new DC point");
    end
end endgenerate
always @(posedge clk) begin
    cycles=cycles+1;
    if(start && frame_ready) start_cycle=cycles;
    if(pixel_valid) begin
    if(!HOLD_PREVIEW || pass_index==1)
        $fwrite(fd,"%c%c%c%c%c%c",pixels[23:16],pixels[15:8],pixels[7:0],pixels[55:48],pixels[47:40],pixels[39:32]);
    count=count+1;
    end
end
initial begin
    $readmemh("samples.hex",stimulus);
    $readmemh("pcm.hex",pcm_stimulus);
    fd=$fopen("preview.rgb","wb");
    #31; reset_n=1;
    if(!ANALYSIS_PREVIEW) begin @(negedge source_clk); sample_data=32'hffe00000; sample_valid=1; end
    for(i=0;i<1024;i=i+1) begin @(negedge source_clk); sample_data=stimulus[i%512];output_pcm=pcm_stimulus[i%512]; sample_valid=1; end
    @(negedge source_clk); sample_valid=0;
    wait(frame_ready); @(negedge clk); start=1; @(negedge clk); start=0;
    wait(frame_done); @(negedge clk);
    if(count!=1036800) $fatal(1,"incorrect frame pixel count");
    if(cycles-start_cycle!=1036805) $fatal(1,"unexpected full-frame raster latency");
    if(HOLD_PREVIEW) begin
        for(i=0;i<512;i=i+1) saved_wave[i]=dut.u_align.trace_samples[i];
        count=0; pass_index=1;
        for(i=0;i<1024;i=i+1) begin @(negedge source_clk); sample_data=32'h40000000;output_pcm=32'h40004000; sample_valid=1; end
        @(negedge source_clk); sample_valid=0;
        wait(frame_ready);
        if(!dut.waveform_held || dut.snapshot_peak!==32'h40000000) $fatal(1,"HOLD must preserve waveform while updating live peak");
        for(i=0;i<512;i=i+1) if(saved_wave[i]!==dut.u_align.trace_samples[i]) $fatal(1,"HOLD changed the waveform");
        @(negedge clk); start=1; @(negedge clk); start=0;
        wait(frame_done); @(negedge clk);
        if(count!=1036800) $fatal(1,"incorrect held-frame pixel count");
    end
    $fclose(fd); $display("PASS actual feedback RTL 1920x1080 preview fixture"); $finish;
end
initial begin #40000000; $fatal(1,"timeout"); end
endmodule
'''.replace("HOLD_MODE_VALUE", str(int(args.hold))).replace("ANALYSIS_MODE_VALUE", str(int(args.analysis))), encoding="ascii")
    sources = [ROOT / "src/video" / name for name in (
        "feedback_capture.v", "feedback_wave_align.v", "feedback_dashboard.v", "feedback_renderer.v", "video_font_5x7.v",
        "output_audio_capture.v", "output_audio_analysis.v", "audio_analysis_rom.v")]
    subprocess.run(["iverilog", "-g2012", "-s", "preview", "-o", "preview.vvp", *map(str, sources), "preview.sv"], cwd=OUT, check=True)
    subprocess.run(["vvp", "preview.vvp"], cwd=OUT, check=True, timeout=180)
    width, height = 1920, 1080
    rgb = (OUT / "preview.rgb").read_bytes()
    if len(rgb) != width * height * 3:
        raise SystemExit(f"Unexpected RGB length {len(rgb)}")
    scanlines = b"".join(b"\0" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += png_chunk(b"tEXt", b"Description\0RTL preview / synthetic audio fixture / not hardware evidence")
    png += png_chunk(b"IDAT", zlib.compress(scanlines, 9)) + png_chunk(b"IEND", b"")
    target = OUT / ("feedback_analysis_hold.png" if args.analysis and args.hold else "feedback_analysis.png" if args.analysis else
                    "feedback_dashboard_hold.png" if args.hold else "feedback_dashboard.png")
    target.write_bytes(png)
    # Keep per-mode source and raw pixels so a later HOLD run cannot replace
    # the evidence for the normal preview.
    shutil.copyfile(OUT / "preview.sv", target.with_suffix(".sv"))
    shutil.copyfile(OUT / "preview.rgb", target.with_suffix(".rgb"))
    (OUT / "README.txt").write_text(
        "RTL PREVIEW ONLY. Synthetic left fixture: 0.625*sin(2*pi*n/64)+0.125*sin(6*pi*n/64). "
        "With --analysis, left is rounded PCM16; right is 0.35*sin(2*pi*n/128+0.6) PCM16; "
        "512 stereo pairs repeat twice for the FFT; the waveform is their mid signal. "
        "With --hold, a second +0.5 block updates analysis/peaks while the first waveform stays held. "
        "Memory calibration/BIST/underrun/frame values are testbench fixtures. Not an FPGA/DDR/HDMI hardware capture.\n",
        encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
