#!/usr/bin/env python3
"""Verify frozen Apache SBC input and emit a separately adapted build tree.

This is not selected by stage_ae350_firmware or any workstation profile.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    source = root / "firmware/ae350/third_party/sbc_oi"
    frozen = source / "upstream"
    manifest_path = source / "upstream_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    actual = {str(p.relative_to(frozen)): sha(p) for p in frozen.rglob("*") if p.is_file()}
    if actual != manifest["files"]:
        raise ValueError("SBC upstream inventory or bytes drifted")
    if output.exists():
        raise ValueError("SBC output must not already exist")
    output.mkdir(parents=True)
    shutil.copytree(frozen / "decoder", output / "decoder")
    arithmetic = source / "a138_sbc_arithmetic.h"
    shutil.copy2(arithmetic, output / "decoder/include/a138_sbc_arithmetic.h")
    changes = []

    def adapt(name, old, new, count=1):
        path = output / "decoder" / name
        text = path.read_text()
        if text.count(old) != count:
            raise ValueError("SBC adaptation anchor drift: " + name)
        path.write_text(text.replace(old, new))
        changes.append(dict(file=name, old=old, new=new, count=count))

    adapt("include/oi_bitstream.h", "OI_ASSERT((bitPtr) < 32);", "OI_ASSERT((bitPtr) <= 32);")
    adapt("include/oi_bitstream.h", "(result) = (value) << (bitPtr);",
          "(result) = (bits) ? ((value) << (bitPtr)) : 0;")
    adapt("include/oi_bitstream.h", "(result) >>= 32 - (bits);",
          "(result) = (bits) ? ((result) >> (32 - (bits))) : 0;")
    adapt("srce/decoder-private.c", "*scale_factor++ = OI_BITSTREAM_ReadUINT4Aligned(bs);",
          "*scale_factor++ = OI_BITSTREAM_ReadUINT(bs, 4);")
    adapt("include/oi_codec_sbc_private.h", '#include "oi_codec_sbc.h"',
          '#include "oi_codec_sbc.h"\n#include "a138_sbc_arithmetic.h"')
    adapt("srce/readsamplesjoint.inc", "*(s - NROF_SUBBANDS) = mid + side;",
          "*(s - NROF_SUBBANDS) = a138_sbc_clip32((int64_t)mid + side);")
    adapt("srce/readsamplesjoint.inc", "dequant = mid - side;",
          "dequant = a138_sbc_clip32((int64_t)mid - side);")
    adapt("srce/synthesis-sbc.c", "#define LONG_MULT_DCT(K, sample) (MUL_16S_32S_HI(K, sample) << 2)",
          "#define LONG_MULT_DCT(K, sample) ((((int64_t)(K) * (sample)) >> 16) * 4)")
    adapt("srce/synthesis-sbc.c", "int32_t f0, f1, f2, f3, f4, f7, f8, f9, f10;",
          "int64_t f0, f1, f2, f3, f4, f7, f8, f9, f10;")
    adapt("srce/synthesis-sbc.c", "int32_t y0, y1, y2, y3;", "int64_t y0, y1, y2, y3;")
    # Cast before input addition/subtraction; assigning an overflowing int32
    # expression to int64 would be too late.
    for index in (0, 1):
        adapt("srce/synthesis-sbc.c", "(in["+str(index)+"]", "((int64_t)in["+str(index)+"]", 2)
    adapt("srce/synthesis-sbc.c", "int32_t pa;\n  int32_t pb;", "int64_t pa;\n  int64_t pb;")
    for old, new in (("-y2", "-y2"), ("-y3", "-y3"), ("y3", "y3"), ("y2", "y2"), ("y1", "y1"), ("y0", "y0")):
        adapt("srce/synthesis-sbc.c", "(int16_t)"+old+";", "a138_sbc_clip16("+new+");", 2 if old == "y1" else 1)
    adapt("srce/synthesis-dct8.c", "(y) = (x) - ((y) << 1);", "(y) = (x) - ((y) * 2);")
    adapt("srce/synthesis-dct8.c", "#define FIX_MULT_DCT(K, x) (MUL_32S_32S_HI(K, x) << 2)",
          "#define FIX_MULT_DCT(K, x) (a138_sbc_mul32x64_hi(K, x) * 4)")
    for declaration in ("L00, L01, L02, L03, L04, L05, L06, L07", "L25", "in0, in1, in2, in3", "in4, in5, in6, in7"):
        adapt("srce/synthesis-dct8.c", "int32_t "+declaration+";", "int64_t "+declaration+";")
    path = output / "decoder/srce/synthesis-dct8.c"
    text = path.read_text()
    pattern = r"\(int16_t\)SCALE\(([^\n]*)\);"
    if len(re.findall(pattern, text)) != 8:
        raise ValueError("SBC DCT narrowing anchors drifted")
    path.write_text(re.sub(pattern, r"a138_sbc_clip16(SCALE(\1));", text))
    changes.append(dict(file="srce/synthesis-dct8.c", pattern=pattern, count=8))
    adapt("srce/synthesis-8-generated.c", "int32_t pcm_a, pcm_b;", "int64_t pcm_a, pcm_b;")
    path = output / "decoder/srce/synthesis-8-generated.c"
    text = path.read_text()
    pattern = r"(\(MUL_16S_16S\([^\n]*?\)\)) << ([1-5])"
    if len(re.findall(pattern, text)) != 27:
        raise ValueError("SBC generated synthesis anchors drifted")
    path.write_text(re.sub(pattern, lambda m: m[1] + " * " + str(1 << int(m[2])) + "LL", text))
    changes.append(dict(file="srce/synthesis-8-generated.c", pattern=pattern, count=27))
    # Apache-2.0 section 4(b): adapted output files must prominently identify
    # the modifications while preserving every original attribution below.
    notice = ("/* Modified for the Gowin_Synthesizer AE350 SBC port, 2026-10-31.\n"
              " * Bitstream correctness and bounded fixed-point arithmetic adaptations.\n"
              " * See adaptation.json; original copyright and license notices follow. */\n")
    for name in sorted({change["file"] for change in changes}):
        path = output / "decoder" / name
        path.write_text(notice + path.read_text())
    result = dict(schema=1, scope="SBC source-stage only; no production profile selection",
                  upstream_revision=manifest["revision"], upstream_sha256=actual,
                  manifest_sha256=sha(manifest_path), adapter_sha256=sha(__file__),
                  arithmetic_sha256=sha(arithmetic), changes=changes,
                  adapted_sha256={str(p.relative_to(output)): sha(p)
                                  for p in output.rglob("*") if p.is_file()})
    (output / "adaptation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(Path(__file__).resolve().parents[1], args.output)
    print("PASS SBC input inventory", len(result["upstream_sha256"]))
