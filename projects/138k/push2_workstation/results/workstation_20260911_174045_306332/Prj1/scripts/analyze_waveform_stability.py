#!/usr/bin/env python3
"""Measure displayed-frame stability using real synth/capture RTL (WSL/Icarus).

Creates only build/wave_stability artifacts. The alignment comparison is a
software experiment over actual emitted audio, not a claim about hardware.
"""
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/wave_stability"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bench = (ROOT / "sim/tb_feedback_polyphonic.sv").read_text()
    bench = bench.replace("module tb_feedback_polyphonic;", "module tb_feedback_stability;\n"
        'integer trace_fd, audio_fd, dump_index;\ninitial trace_fd=$fopen("build/wave_stability/snapshots.txt","w");')
    bench = bench.replace("history[0:16383]", "history[0:65535]")
    bench = bench.replace("history_voices[0:16383]", "history_voices[0:65535]")
    bench = bench.replace("history_edge[0:16383]", "history_edge[0:65535]")
    bench = bench.replace("search_start=start_index+512;", """search_start=start_index+512;
            $fwrite(trace_fd,"%0d",start_index);
            for(dump_index=0;dump_index<512;dump_index=dump_index+1)
                $fwrite(trace_fd," %h",observed[dump_index]);
            $fwrite(trace_fd,"\\n");""")
    bench = bench.replace("repeat(10000+frames_checked*37)", "repeat(10600)")
    bench = bench.replace("repeat(3000) frame();", """repeat(45000) frame();
        $fclose(trace_fd);
        audio_fd=$fopen("build/wave_stability/audio.hex","w");
        for(dump_index=0;dump_index<history_count;dump_index=dump_index+1)
            $fwrite(audio_fd,"%h\\n",history[dump_index]);
        $fclose(audio_fd);
        $display("PASS stability trace: %0d audio samples, %0d snapshots",history_count,frames_checked);
        $finish;""")
    bench = bench.replace("#10000000;", "#100000000;")
    (OUT / "tb_feedback_stability.sv").write_text(bench)
    sources = sorted((ROOT / "src").rglob("*.v"))
    sources += sorted(p for p in (ROOT / "vendor").rglob("*.v") if "gowin_ddr3" not in p.parts)
    sources += sorted((ROOT / "sim/models").glob("*.v"))
    subprocess.run(["iverilog", "-g2012", "-s", "tb_feedback_stability", "-o",
                    str(OUT / "trace.vvp"), *map(str, sources), str(OUT / "tb_feedback_stability.sv")], cwd=ROOT, check=True)
    result = subprocess.run(["vvp", str(OUT / "trace.vvp")], cwd=ROOT, capture_output=True, text=True, timeout=180)
    (OUT / "trace.log").write_text(result.stdout + result.stderr)
    if result.returncode or "PASS stability" not in result.stdout:
        raise SystemExit(result.stdout + result.stderr)
    print(result.stdout.strip())

    def signed(word):
        value = int(word, 16)
        return value - (1 << 32) if value & (1 << 31) else value

    audio = [signed(word) for word in (OUT / "audio.hex").read_text().splitlines()]
    records = [line.split() for line in (OUT / "snapshots.txt").read_text().splitlines()]
    starts = [int(row[0]) for row in records]
    windows = [[signed(word) for word in row[1:]] for row in records]
    assert len(windows) >= 40 and all(len(w) == 512 for w in windows)
    for start, window in zip(starts, windows):
        assert audio[start:start+512] == window

    # Candidate windows always contain fresh, consecutive real mixed samples.
    # Search one extra 512-sample span, using 64 evenly spaced comparison points.
    aligned = [windows[0]]
    aligned_starts = [starts[0]]
    for start in starts[1:]:
        end = min(start+512, len(audio)-512)
        previous = aligned[-1]
        chosen = min(range(start, end+1), key=lambda candidate:
                     sum(abs((audio[candidate+k] >> 19) - (previous[k] >> 19)) for k in range(0, 512, 8)))
        aligned.append(audio[chosen:chosen+512])
        aligned_starts.append(chosen)

    def rms_pixels(a, b):
        return math.sqrt(sum(((x-y) / 8388608.0)**2 for x, y in zip(a, b)) / 512)

    raw_changes = [rms_pixels(a,b) for a,b in zip(windows, windows[1:])]
    aligned_changes = [rms_pixels(a,b) for a,b in zip(aligned, aligned[1:])]
    report = {
        "fixture": "Staggered C4/E4/G4/C5 sine voices, constant full sustain, real synth/capture RTL",
        "samples": len(audio), "snapshots": len(windows), "board_tested": False,
        "current_dds_trigger_rms_pixel_change_mean": statistics.mean(raw_changes),
        "current_dds_trigger_rms_pixel_change_max": max(raw_changes),
        "software_window_match_rms_pixel_change_mean": statistics.mean(aligned_changes),
        "software_window_match_rms_pixel_change_max": max(aligned_changes),
        "window_offsets": [a-b for a,b in zip(aligned_starts,starts)],
        "inputs_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    }
    # A normal pattern trigger has an explicit HOLD state instead of
    # publishing a bad match as though it were locked. Quantize only the
    # comparison; the displayed windows remain untouched Q1.31 samples.
    stable = [windows[0]]
    holds = [False]
    previous = windows[0]
    for start in starts[1:]:
        chosen = min(range(start, min(start+512, len(audio)-512)+1), key=lambda candidate:
                     sum(abs((audio[candidate+k] >> 23) - (previous[k] >> 23)) for k in range(0, 512, 8)))
        candidate = audio[chosen:chosen+512]
        score = sum(abs((a >> 23)-(b >> 23)) for a,b in zip(candidate,previous))
        held = score > 512*4
        if not held:
            previous = candidate
        stable.append(previous)
        holds.append(held)
    stable_changes = [rms_pixels(a,b) for a,b in zip(stable,stable[1:])]
    report["normal_pattern_trigger"] = {
        "full_window_mean_absolute_error_limit_pixels": 4,
        "new_windows": len(holds)-sum(holds), "held_frames": sum(holds),
        "frame_rms_change_mean": statistics.mean(stable_changes),
        "frame_rms_change_max": max(stable_changes),
        "note": "HOLD is explicit; waveform age differs from live peak/status. This mode must be chosen deliberately.",
    }
    (OUT / "comparison.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("inputs_sha256", "window_offsets")}, indent=2))
    # Inspectable animation; all data come from the saved RTL sample dump.
    payload = json.dumps({"raw": [[round(v/8388608,2) for v in w] for w in windows],
                          "aligned": [[round(v/8388608,2) for v in w] for w in aligned]})
    page = '''<!doctype html><meta charset="utf-8"><title>RTL chord stability</title>
<style>body{background:#101b2a;color:#e5f0fa;font:16px system-ui;margin:24px}canvas{width:100%;max-width:1100px;background:#0b1420;display:block;margin:10px 0}button,input{margin:8px}p{max-width:1000px}</style>
<h2>Actual RTL chord snapshots / software alignment experiment</h2>
<p>Continuous C4/E4/G4/C5, unchanged notes and gains. Top: current DDS trigger. Bottom: matching a fresh 512-sample window to the previous trace. This is simulation, not hardware footage.</p>
<button id="play">Pause</button><input id="frame" type="range" min="0" value="0"><span id="label"></span>
<canvas id="raw" width="1100" height="330"></canvas><canvas id="aligned" width="1100" height="330"></canvas>
<script>const data=PAYLOAD;let n=0,playing=true;const slider=document.getElementById('frame');slider.max=data.raw.length-1;
function draw(){for(const kind of ['raw','aligned']){const c=document.getElementById(kind),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);x.strokeStyle='#31506c';x.beginPath();x.moveTo(30,165);x.lineTo(1052,165);x.stroke();x.strokeStyle=kind==='raw'?'#f1c05a':'#3cdbab';x.beginPath();data[kind][n].forEach((v,i)=>i?x.lineTo(30+i*2,165-v):x.moveTo(30,165-v));x.stroke();x.fillStyle='#e5f0fa';x.fillText(kind==='raw'?'Current DDS reference':'Software window matching',30,22)}slider.value=n;document.getElementById('label').textContent=`Frame ${n+1}/${data.raw.length}`}
document.getElementById('play').onclick=()=>{playing=!playing;document.getElementById('play').textContent=playing?'Pause':'Play'};slider.oninput=()=>{n=+slider.value;draw()};setInterval(()=>{if(playing){n=(n+1)%data.raw.length;draw()}},100);draw();</script>'''
    (OUT / "comparison.html").write_text(page.replace("PAYLOAD", payload))


if __name__ == "__main__":
    main()
