#!/usr/bin/env python3
"""Read-only cross-project checks; never programs hardware or writes the synth tree.

First run run_packet_vectors.py beside this script. The C harness includes the
target's production firmware verbatim, retaining its transport-mock regression
and substituting this board's actual composite configuration descriptor.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BOARD = HERE.parents[1]
DEFAULT_SYNTH = BOARD.parents[2] / "Mega_138K/Dev/Gowin_Synthesizer"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd=None):
    result = subprocess.run([str(x) for x in command], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command}\n{result.stdout}")
    return result.stdout


def c_bytes(blob):
    return ",".join(f"0x{x:02x}" for x in blob)


CROSS_TEST = r'''
#include "cross_vectors.h"
static void cross_test(void) {
    fixture(); connect();
    assert(descriptor_size==124 && connected && mode==DEVICE_MIDI);
    assert(midi_in_ep==1 && midi_in_size==64 && !control_calls);
    const unsigned initial_out=out_calls;
    unsigned supported=0,ignored=0;
    for(unsigned i=0;i<cross_count;i++) {
        const struct cross_vector *v=&cross_vectors[i];
        unsigned before=generic_writes;
        forward_midi(v->packet);
        assert(generic_writes==before+(v->kind>=0));
        if(v->kind>=0) {
            assert(regs[0x54/4]==((unsigned)v->kind<<14 | v->a<<7 | v->b));
            supported++;
        } else ignored++;
        memcpy(payload,v->packet,4); rx_result=4; reply_pid=in_pid;
        before=generic_writes; poll_midi();
        assert(generic_writes==before+(v->kind>=0));
        if(v->kind>=0)assert(regs[0x54/4]==((unsigned)v->kind<<14 | v->a<<7 | v->b));
        before=generic_writes; poll_midi(); // exact DATA PID replay
        assert(generic_writes==before);
    }
    // Full FS packets and a final short packet; every event still has four bytes.
    for(unsigned first=0;first<cross_count;first+=16) {
        unsigned count=cross_count-first; if(count>16)count=16;
        unsigned expected=0,last=first;
        for(unsigned j=0;j<count;j++) {
            const struct cross_vector *v=&cross_vectors[first+j];
            memcpy(payload+j*4,v->packet,4);
            if(v->kind>=0){expected++;last=first+j;}
        }
        unsigned before=generic_writes;
        rx_result=count*4; reply_pid=in_pid; poll_midi();
        assert(generic_writes==before+expected);
        if(expected) {
            const struct cross_vector *v=&cross_vectors[last];
            assert(regs[0x54/4]==((unsigned)v->kind<<14 | v->a<<7 | v->b));
        }
    }
    rx_result=USB_RES_NAK;
    regs[0x40/4]=0x8000000c; lights(); assert(!frame());
    assert(!send(1,payload,4) && !send(2,payload,4));
    regs[0x40/4]=0; assert(out_calls==initial_out);
    fixture(); memcpy(descriptor,cross_hs,sizeof cross_hs);
    descriptor_size=sizeof cross_hs; rejected(); // FS host must reject MPS512
    fixture(); connect(); assert(connected && midi_in_ep==1 && midi_in_size==64);
    printf("PASS cross vectors: %u supported, %u intentionally ignored; direct, poll, duplicate PID, FS packet batching; generic OUT=0; HS descriptor rejected\n",supported,ignored);
    // Capture the actual production Push frame header; pixel FIFO remains mocked.
    fixture(); fixture_vid=0x2982; fixture_pid=0x9999; descriptor_error=1;
    expected_ep=2; expected_size=512; connect();
    unsigned before=out_calls; assert(frame()==1);
    assert(out_calls-before==641 && captured_headers==1);
    const uint8_t expected_header[16]={0xff,0xcc,0xaa,0x88};
    assert(!memcmp(captured_header,expected_header,16));
    printf("CAPTURE_PUSH_HEADER ");
    for(unsigned i=0;i<16;i++)printf("%02x",captured_header[i]);
    puts("");
    fixture(); connect();
}
'''


def native_cross(usb, fs, hs, vectors, output):
    source = (usb / "sim/test_generic_midi.c").read_text()
    assert source.count('#include "../firmware.c"') == 1
    source = source.replace('#include "../firmware.c"',
        'int usbhw_transfer_out_preloaded(uint8_t,int,int,int,uint8_t,int);\n'
        '#include SYNTH_FIRMWARE')
    source, count = re.subn(r"static const uint8_t g1_config\[\]=\{.*?\n\};",
        "static const uint8_t g1_config[]={" + c_bytes(fs) + "};", source, flags=re.S)
    assert count == 1
    source = source.replace("assert(descriptor_size==101)", "assert(descriptor_size==124)")
    source = source.replace("static uint32_t now_ms;", "static uint32_t now_ms;\n"
        "static uint8_t captured_header[16]; static unsigned captured_headers;")
    old = "assert(mode==DEVICE_PUSH);out_calls++;return USB_RES_OK;"
    assert source.count(old) == 1
    source = source.replace(old,
        "assert(mode==DEVICE_PUSH);out_calls++;"
        "if(ep==1 && n==16 && buf){memcpy(captured_header,buf,16);captured_headers++;}"
        "return USB_RES_OK;")
    source = source.replace("int main(int argc,char **argv){", CROSS_TEST + "\nint main(int argc,char **argv){")
    source = source.replace("assert(out_calls==2);", "assert(out_calls==2); cross_test();")
    source = source.replace("G1 descriptors", "actual GW25K 124-byte FS descriptors")
    header = ["struct cross_vector { uint8_t packet[4]; int kind; unsigned a,b; };",
              "static const struct cross_vector cross_vectors[]={"]
    for v in vectors:
        packet = bytes.fromhex(v["packethex"])
        assert len(packet) == 4
        header.append("{{" + c_bytes(packet) + "}," +
                      f'{int(v["kind"])},{int(v["expecta"])},{int(v["expectb"])}' + "},")
    header += ["};", "static const unsigned cross_count=sizeof cross_vectors/sizeof cross_vectors[0];",
               "static const uint8_t cross_hs[]={" + c_bytes(hs) + "};"]
    (output / "cross_harness.c").write_text(source)
    (output / "cross_vectors.h").write_text("\n".join(header) + "\n")
    compiler = shutil.which("clang") or shutil.which("gcc")
    assert compiler, "C compiler required"
    include = usb / "vendor/usb_host_fs_8fc3/firmware"
    with tempfile.TemporaryDirectory(prefix="gw25k-synth-cross-") as temporary:
        executable = Path(temporary) / "cross_test"
        command = [compiler, "-std=c99", "-O1", "-g", "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer", f'-DSYNTH_FIRMWARE="{usb / "firmware.c"}"',
            "-I", include, "-I", include / "usb", output / "cross_harness.c", "-o", executable]
        compile_log = run(command)
        test_log = run([executable])
    (output / "native_compile.log").write_text(compile_log)
    (output / "native_test.log").write_text(test_log)
    assert "PASS cross vectors:" in test_log and "PASS generic firmware:" in test_log
    match = re.search(r"CAPTURE_PUSH_HEADER ([0-9a-f]+)", test_log)
    assert match
    return {"passed": True, "sanitizers": ["address", "undefined"],
            "vector_count": len(vectors), "supported": sum(int(v["kind"]) >= 0 for v in vectors),
            "ignored": sum(int(v["kind"]) < 0 for v in vectors),
            "compiler": run([compiler, "--version"]).splitlines()[0],
            "production_push_header": match[1], "output": test_log,
            "method": "Production firmware included verbatim; USB/MMIO mocked. Upstream mock regression retained with actual FS config and additional RTL vectors. Enumeration transport/PHY are not emulated."}


def panel_check(push_header, usb):
    spec = importlib.util.spec_from_file_location("cross_panel_display", BOARD / "tools/panel_display.py")
    panel = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = panel
    spec.loader.exec_module(panel)
    hello = panel.Frame(panel.HELLO, 0x138025, 0)
    assert panel.decode_frame(panel.encode_frame(hello)) == hello
    pixels = panel.rgb888_to_rgb565(bytes([255,0,0,0,255,0,0,0,255]))
    assert pixels.hex() == "00f8e0071f00"
    tile = panel.Frame(panel.TILE, 0x138025, 0, channel=1,
        payload=panel.tile_payload(0,1,0,0,3,1,pixels))
    assert panel.decode_frame(panel.encode_frame(tile)) == tile
    try:
        panel.decode_frame(bytes.fromhex(push_header))
    except ValueError as error:
        assert str(error) == "invalid PL magic"
        rejection = str(error)
    else:
        raise AssertionError("Push frame unexpectedly accepted as PL")
    # Formula comparison is source-derived; no claim of target pixel-RTL simulation.
    streamer = (usb / "rtl/push2_screen_fifo_streamer.sv").read_text()
    assert "count[0]?16'hffe7:16'hf3e7" in streamer
    push_pixels = b"".join(struct.pack("<H", value ^ (0xFFE7 if i & 1 else 0xF3E7))
        for i, value in enumerate(struct.unpack("<3H", pixels)))
    image = panel.demo_image()
    covered = bytearray(panel.WIDTH * panel.HEIGHT)
    outgoing = len(panel.encode_frame(panel.Frame(panel.END, 1, 252, channel=1,
        payload=struct.pack("<HHI",0,0,1))))
    count = 0
    for x,y,w,h,data in panel.iter_tiles(image):
        for row in range(y,y+h):
            for col in range(x,x+w):
                index = row * panel.WIDTH + col
                assert not covered[index]
                covered[index] = 1
        payload = panel.tile_payload(0,1,x,y,w,h,data)
        outgoing += len(panel.encode_frame(panel.Frame(panel.TILE,1,count,channel=1,payload=payload)))
        count += 1
    assert all(covered) and count == 252 and outgoing == 129640
    return {"checks_passed": True, "interfaces_compatible": False,
        "actual_push_header_rejection": rejection, "pl_rgb565le": pixels.hex(),
        "push_formula_pixels": push_pixels.hex(), "pixel_check_method": "PL production Python; Push source-derived XOR formula",
        "full_frame_tiles": count, "full_frame_pixels_bytes": len(image),
        "full_frame_out_bytes_excluding_handshake_heartbeat_replies": outgoing,
        "fs_raw_payload_only_max_fps_upper_bound": 12_000_000 / 8 / len(image),
        "full_frame_60fps_pixel_bits_per_second": len(image) * 60 * 8}


def verify_hashes(record):
    values = record["sha256"]
    mismatches = [p for p,h in values.items() if not (BOARD / p).is_file() or sha(BOARD / p) != h]
    return {"count": len(values), "stable": not mismatches, "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synth", type=Path, default=DEFAULT_SYNTH)
    parser.add_argument("--vectors", type=Path, default=HERE / "generated/usb_midi_vectors.csv")
    parser.add_argument("--output", type=Path, default=BOARD / "reports/compatibility_gowin_synthesizer_20261017")
    args = parser.parse_args()
    synth = args.synth.resolve()
    usb = synth / "migration/gw138k_audio/push2_workstation/usb_a"
    output = args.output.resolve()
    # Keep all generated files in this board project or /private/tmp.
    assert output.is_relative_to(BOARD) or output.is_relative_to(Path("/private/tmp"))
    output.mkdir(parents=True, exist_ok=True)
    run([sys.executable, BOARD / "tools/generate_usb_descriptors.py", "--check"])
    manifest = json.loads((BOARD / "config/usb_descriptors.json").read_text())
    fs = bytes.fromhex(manifest["descriptors"]["full_speed"]["0x0200"]["hex"])
    hs = bytes.fromhex(manifest["descriptors"]["high_speed"]["0x0200"]["hex"])
    with args.vectors.open(newline="") as f:
        vectors = list(csv.DictReader(f))
    assert vectors
    vector_report_path = args.vectors.parent / "packet_vectors_report.json"
    vector_report = json.loads(vector_report_path.read_text())
    assert vector_report["csv_sha256"] == sha(args.vectors)
    assert vector_report["wire_packets"] == len(vectors)
    assert all(sha(BOARD / p) == h for p,h in vector_report["production_sources"].items())
    assert sha(HERE / "tb_packet_vectors.v") == vector_report["testbench_sha256"]
    relevant = ["firmware.c", "sim/test_generic_midi.c", "LATEST_WORKSTATION.json",
        "tools/build_current_workstation.py", "build.py", "rtl/push2_usb_a_control.sv",
        "rtl/push2_screen_fifo_streamer.sv", "rtl/display_data/push2_surface_pixels.sv",
        "rtl/audio/gw138k_event_workstation.sv", "vendor/usb_host_fs_8fc3/firmware/minlibc.h",
        "vendor/usb_host_fs_8fc3/firmware/usb/usb_core.h",
        "vendor/usb_host_fs_8fc3/firmware/usb/usb_defs.h",
        "vendor/usb_host_fs_8fc3/firmware/usb/usb_hw.h"]
    target_hashes = {p: sha(usb / p) for p in relevant}
    build = json.loads((BOARD / "reports/last_build.json").read_text())
    validation = json.loads((BOARD / "reports/validation.json").read_text())
    native = native_cross(usb, fs, hs, vectors, output)
    panel = panel_check(native["production_push_header"], usb)
    assert target_hashes == {p: sha(usb / p) for p in relevant}
    build_binding, validation_binding = verify_hashes(build), verify_hashes(validation)
    assert build_binding["stable"] and validation_binding["stable"]
    assert all(sha(BOARD / artifact["path"]) == artifact["sha256"] for artifact in build["artifacts"])
    latest = json.loads((usb / "LATEST_WORKSTATION.json").read_text())
    builder = (usb / "tools/build_current_workstation.py").read_text()
    base_match = re.search(r"BASE\s*=\s*ROOT\s*/\s*['\"]([^'\"]+)['\"]", builder)
    assert base_match
    result = {"generated_at": datetime.now().astimezone().isoformat(),
        "scope": "Offline current-source interface compatibility detection; no hardware access, no flashing",
        "detection_checks_passed": True, "fully_compatible": False,
        "keyboard_to_synth_midi": "source-level and production-firmware/RTL-vector cross-test compatible at FS",
        "synth_to_keyboard_guidance": "not implemented in target generic mode",
        "synth_to_keyboard_panel": "not compatible; target PL adapter absent",
        "synth_root": str(synth), "synth_git_head": run(["git","-C",synth,"rev-parse","HEAD"]).strip(),
        "synth_latest_record": {k: latest[k] for k in ("build", "user_code", "flashed_at", "bitstream_sha256", "timing_closed", "coordination") if k in latest},
        "recorded_full85_build_exists": (usb / latest["build"]).is_dir(),
        "current_workstation_required_base": base_match[1],
        "current_workstation_required_base_exists": (usb / base_match[1]).is_dir(),
        "synth_source_sha256": target_hashes,
        "board_descriptor_sha256": sha(BOARD / "config/usb_descriptors.json"),
        "board_descriptor_rom_sha256": sha(BOARD / "rtl/usb_board/generated/usb_composite_desc_rom.v"),
        "vectors_sha256": sha(args.vectors), "runner_sha256": sha(__file__),
        "vector_generation": vector_report,
        "vector_runner_sha256": sha(HERE / "run_packet_vectors.py"),
        "board_build_input_binding": build_binding, "board_regression_input_binding": validation_binding,
        "board_build_artifacts_hash_verified": True,
        "board_build_artifacts": build["artifacts"], "native_cross_test": native, "panel_checks": panel,
        "limitations": ["USB enumeration transport/PHY, actual cabling, power and audio hardware are not exercised",
            "Target recorded full85 image and current-workstation full83 base missing; findings cannot be bound to flashed 0x85",
            "All channels/cables merged; realtime, SysEx and channel pressure not forwarded",
            "Existing generic note path does not feed Push score-guide played_valid"]}
    (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(native["output"], end="")
    print(f"PASS detection checks; full interface compatibility=False; report: {output / 'result.json'}")


if __name__ == "__main__":
    main()
