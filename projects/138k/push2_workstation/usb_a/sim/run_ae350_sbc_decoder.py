#!/usr/bin/env python3
"""Check the unselected SBC source-stage against independent reference PCM."""
from pathlib import Path
import argparse
import array
import base64
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path,
                        help="Optional external 42-case vectors-v1 directory")
    parser.add_argument("--riscv-prefix", default="/opt/homebrew/bin/riscv64-elf")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output must not already exist")
    output.mkdir(parents=True)
    module_spec = importlib.util.spec_from_file_location("sbc_prepare", root / "tools/prepare_ae350_sbc.py")
    adapter = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(adapter)
    prepared = output / "adapted"
    adapter.prepare(root, prepared)
    decoder = prepared / "decoder"
    firmware = root / "firmware/ae350"
    fixture = root / "sim/ae350_sbc_fixture.c"
    commands = []

    def run(argv, name, expect=0):
        p = subprocess.run(list(map(str, argv)), cwd=root, capture_output=True, text=True, timeout=120)
        (output / (name + ".log")).write_text(p.stdout + p.stderr)
        commands.append(dict(argv=list(map(str, argv)), returncode=p.returncode))
        if expect is not None:
            assert p.returncode == expect, (name, p.returncode, p.stderr)
        return p

    host_cc = Path(shutil.which("cc")).resolve()
    common = [host_cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
              "-I" + str(firmware), "-I" + str(decoder / "include"), "-I" + str(decoder / "srce")]
    sources = [firmware / "sbc_decoder_service.c", *sorted((decoder / "srce").glob("*.c"))]
    for tag, san in (("native", False), ("sanitized", True)):
        run([*common, *(["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if san else []),
             fixture, *sources, "-o", output / tag], tag + "-compile")

    cases = []
    fixture_json = root / "sim/fixtures/ae350_sbc_reference.json"
    embedded = json.loads(fixture_json.read_text())
    for row in embedded["cases"]:
        tag = "builtin-" + row["name"]
        sbc, ref = output / (tag + ".sbc"), output / (tag + "-reference.pcm")
        sbc.write_bytes(base64.b64decode(row["sbc_base64"]))
        ref.write_bytes(base64.b64decode(row["reference_pcm_le_base64"]))
        assert sha(sbc) == row["sbc_sha256"] and sha(ref) == row["reference_sha256"]
        cases.append((tag, sbc, ref))
    if args.reference_root:
        reference = args.reference_root.resolve()
        original = json.loads((reference / "verification.json").read_text())
        for i, row in enumerate(original["cases"]):
            tag = f"{i:02d}"
            sbc, ref = reference / (tag + ".sbc"), reference / (tag + "-bluez.pcm")
            assert sha(sbc) == row["SBC_sha256"] and sha(ref) == row["reference_sha256"]
            cases.append(("external-" + tag, sbc, ref))
    comparisons = []
    for tag, sbc, ref in cases:
        native, sanitized = output / (tag + "-native.pcm"), output / (tag + "-sanitized.pcm")
        a = run([output / "native", sbc, native], tag + "-native")
        b = run([output / "sanitized", sbc, sanitized], tag + "-sanitized")
        assert "runtime error:" not in b.stderr and "Sanitizer" not in b.stderr
        assert native.read_bytes() == sanitized.read_bytes()
        # Inputs and reference explicitly contain little-endian signed 16-bit PCM.
        import struct
        raw, reference_bytes = native.read_bytes(), ref.read_bytes()
        assert len(raw) == len(reference_bytes) and len(raw) % 2 == 0
        values = struct.unpack("<" + "h" * (len(raw)//2), raw)
        refs = struct.unpack("<" + "h" * (len(raw)//2), reference_bytes)
        errors = [int(x) - int(y) for x, y in zip(values, refs)]
        energy, noise = sum(int(x)**2 for x in refs), sum(x*x for x in errors)
        max_error = max(map(abs, errors))
        assert max_error <= 8, (tag, max_error)
        comparisons.append(dict(case=tag, sbc_sha256=sha(sbc), reference_sha256=sha(ref),
                                output_sha256=sha(native), samples=len(values), max_abs_error=max_error,
                                rms_error=math.sqrt(noise/len(values)),
                                snr_db=10*math.log10(energy/noise) if noise else None,
                                fixture_summary=a.stderr.strip()))

    mutants = []
    # Fail before applying any adaptation when upstream bytes have drifted.
    bad_root = output / "bad-upstream"
    bad_vendor = bad_root / "firmware/ae350/third_party/sbc_oi"
    shutil.copytree(firmware / "third_party/sbc_oi", bad_vendor)
    header = bad_vendor / "upstream/decoder/include/oi_bitstream.h"
    header.write_bytes(header.read_bytes() + b"\n")
    try:
        adapter.prepare(bad_root, output / "bad-upstream-result")
        raise AssertionError("drifted upstream accepted")
    except ValueError as error:
        assert "inventory" in str(error)
    mutants.append("upstream-byte-drift")
    header.write_bytes(header.read_bytes().replace(b"OI_ASSERT((bitPtr) < 32);", b"OI_ASSERT((bitPtr) < 31);"))
    manifest_path = bad_vendor / "upstream_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["decoder/include/oi_bitstream.h"] = sha(header)
    manifest_path.write_text(json.dumps(manifest))
    try:
        adapter.prepare(bad_root, output / "bad-anchor-result")
        raise AssertionError("drifted adaptation anchor accepted")
    except ValueError as error:
        assert "anchor drift" in str(error)
    mutants.append("adaptation-anchor-drift")
    service = (firmware / "sbc_decoder_service.c").read_text()
    for tag, old, new in (
        ("history-not-cleared", "memset(d->workspace, 0, sizeof d->workspace);", "(void)0;"),
        ("stale-accepted", "if (epoch != d->last_epoch) return A138_SBC_STALE;", "if (0) return A138_SBC_STALE;"),
    ):
        mutated = output / (tag + ".c")
        assert old in service
        mutated.write_text(service.replace(old, new))
        exe = output / tag
        run([*common, fixture, mutated, *sources[1:], "-o", exe], tag + "-compile")
        p = run([exe, cases[0][1], output / (tag + ".pcm")], tag + "-run", expect=None)
        assert p.returncode != 0
        mutants.append(tag)
    for tag, relative, old, new in (
        ("crc-ignored", "srce/decoder-sbc.c", "if (crc != context->common.frameInfo.crc)", "if (0 && crc != context->common.frameInfo.crc)"),
        ("joint4-halfbyte-regression", "srce/decoder-private.c", "*scale_factor++ = OI_BITSTREAM_ReadUINT(bs, 4);", "*scale_factor++ = OI_BITSTREAM_ReadUINT4Aligned(bs);"),
    ):
        original = decoder / relative
        mutated = output / (tag + ".c")
        text = original.read_text()
        assert text.count(old) == (2 if tag == "crc-ignored" else 1)
        mutated.write_text(text.replace(old, new))
        exe = output / tag
        run([*common, fixture, *[mutated if s == original else s for s in sources], "-o", exe], tag + "-compile")
        if tag == "crc-ignored":
            p = run([exe, cases[0][1], output / (tag + ".pcm")], tag + "-run", expect=None)
            assert p.returncode != 0
        else:
            case = next(c for c in cases if c[0] == "builtin-12")
            pcm = output / (tag + ".pcm")
            p = run([exe, case[1], pcm], tag + "-run", expect=None)
            if p.returncode == 0:
                import struct
                a = struct.unpack("<" + "h"*(pcm.stat().st_size//2), pcm.read_bytes())
                b = struct.unpack("<" + "h"*(case[2].stat().st_size//2), case[2].read_bytes())
                assert max(abs(x-y) for x, y in zip(a,b)) > 8
        mutants.append(tag)

    # The first source-stage link measures decoder cost only, with section GC.
    # It cannot establish complete UI/business firmware capacity or CPU cycles.
    rv = output / "rv32"
    rv.mkdir()
    (rv / "stdlib.h").write_text("#include <stddef.h>\n")
    (rv / "string.h").write_text("#include <stddef.h>\nvoid *memset(void *, int, size_t);\nvoid *memcpy(void *, const void *, size_t);\n")
    budget = rv / "budget.c"
    budget.write_text('''#include "sbc_decoder_service.h"
static struct a138_sbc_decoder decoder;
static uint8_t compressed[224]; static int16_t pcm[256];
static struct a138_sbc_pcm result; volatile int status;
void sbc_decode_budget_entry(void) {
  struct a138_sbc_format format={48000,3,8,16,0,2,53};
  a138_sbc_init(&decoder); status=a138_sbc_begin(&decoder,1,&format);
  status=a138_sbc_decode(&decoder,1,compressed,sizeof compressed,pcm,256,&result);
  status=a138_sbc_cancel(&decoder,1);
}
''')
    linker = rv / "budget.ld"
    linker.write_text('''ENTRY(sbc_decode_budget_entry)
MEMORY { ILM (rx) : ORIGIN = 0x800000, LENGTH = 64K
         DLM (rw) : ORIGIN = 0x900000, LENGTH = 64K }
SECTIONS { .text : { *(.text*) *(.rodata*) } > ILM
 .data : { *(.data*) *(.bss*) *(COMMON) } > DLM }
''')
    gcc, size, nm = (Path(args.riscv_prefix + suffix).resolve() for suffix in ("-gcc", "-size", "-nm"))
    rvflags = [gcc, "-march=rv32im_zicsr", "-mabi=ilp32", "-O2", "-ffreestanding", "-fno-builtin",
               "-fno-pic", "-fno-stack-protector", "-ffunction-sections", "-fdata-sections", "-fno-common",
               "-fstack-usage", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter",
               "-I"+str(rv), "-I"+str(firmware), "-I"+str(decoder/"include")]
    objects = []
    for source in [budget, *sources, firmware / "ui_runtime.c"]:
        obj = rv / (source.stem + ".o")
        run([*rvflags, "-c", source, "-o", obj], "rv32-" + source.stem)
        objects.append(obj)
    run([gcc, "-march=rv32im_zicsr", "-mabi=ilp32", "-nostdlib", "-nostartfiles", "-Wl,--gc-sections",
         "-T", linker, *objects, "-Wl,-Map="+str(rv/"budget.map"), "-lgcc", "-o", rv/"budget.elf"], "rv32-link")
    size_output = run([size, rv / "budget.elf"], "rv32-size").stdout
    undefined = run([nm, "-u", rv / "budget.elf"], "rv32-undefined").stdout
    assert not undefined.strip()
    stack = []
    for path in rv.glob("*.su"):
        for row in path.read_text().splitlines():
            fields = row.split("\t")
            if len(fields) == 3:
                assert fields[2] == "static"
                stack.append(dict(function=fields[0], frame_bytes=int(fields[1])))
    # Source inventory includes all vendor headers and adapter controls, not just C TUs.
    inputs = {str(p.relative_to(root)): sha(p) for p in
              [Path(__file__).resolve(), fixture, fixture_json, root/"tools/prepare_ae350_sbc.py",
               firmware/"sbc_decoder_service.c", firmware/"sbc_decoder_service.h", firmware/"ui_runtime.c",
               *[p for p in (firmware/"third_party/sbc_oi").rglob("*") if p.is_file()]]}
    tools = {str(p): sha(p) for p in [host_cc, gcc, size, nm]}
    result = dict(schema=1, passed=True, scope="unselected SBC decoder source-stage",
                  cases=comparisons, behavioral_mutants_rejected=mutants,
                  rv32=dict(size_output=size_output, stack_frames=stack,
                            incremental_gc_sections=True, full_firmware_budget=False,
                            full_call_chain_stack_bound=False, CPU_cycles_measured=False),
                  standard_qualification_vectors=False, phone_interoperability=False,
                  hardware_operated=False, input_sha256=inputs, tool_sha256=tools, commands=commands)
    result["output_sha256"] = {str(p.relative_to(output)): sha(p) for p in output.rglob("*")
                                if p.is_file() and p.name != "verification.json"}
    (output / "verification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("PASS", len(cases), "reference cases;", len(mutants), "behavioral mutants rejected")
    print(size_output, end="")


if __name__ == "__main__":
    main()
