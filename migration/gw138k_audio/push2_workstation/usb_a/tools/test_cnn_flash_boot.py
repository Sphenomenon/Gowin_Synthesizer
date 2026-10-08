#!/usr/bin/env python3
"""SPI-pin/DDR-contract fault-injection tests for CNN Flash boot (no PCM)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from build_cnn_flash_image import build_image, load_words,validate_image,pack_flash
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'rtl/music'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--skip-full-model', action='store_true')
    args = ap.parse_args()
    results=[]
    with tempfile.TemporaryDirectory(prefix='cnn_flash_') as tmp:
        out=Path(tmp)
        for words,divider,cases in [(31,4,list(range(11))),(1,1,[0,1,7,8]),(65536,1,[0] if not args.skip_full_model else [])] + ([] if args.skip_full_model else [(52239,4,[0])]):
            vals=load_words(SRC/'weights/cnn_ddr_blob.mem') if words==52239 else [(i*7919 ^ 0xA53C)&65535 for i in range(words)]
            image,manifest=build_image(vals)
            img=out/f'{words}.hex';img.write_text('\n'.join(f'{b:02x}' for b in image)+'\n')
            exe=out/f'{words}.vvp'
            cmd=['iverilog','-g2012','-I',str(SRC),'-s','tb_boot_model',
                 '-P',f'tb_boot_model.WORDS={words}','-P',f'tb_boot_model.CLK_DIV={divider}',
                 '-o',str(exe),str(ROOT/'sim/model_flash/tb_boot_model.sv')]+[str(SRC/f) for f in
                 ('basic_pitch_boot_model_loader.sv','basic_pitch_flash_model_loader.sv','basic_pitch_uart_model_loader.sv','basic_pitch_uart_rx.sv')]
            subprocess.run(cmd,check=True,capture_output=True,text=True)
            for case in cases:
                modes=[0,1] if case==0 and words<100 else [0]
                for mode in modes:
                    run=subprocess.run(['vvp',str(exe),f'+IMAGE={img}',f'+CASE={case}',f'+ZERO_RSP={mode}'],capture_output=True,text=True,timeout=180)
                    print(run.stdout.strip(),flush=True)
                    if run.returncode or 'PASS ' not in run.stdout:
                        raise RuntimeError(run.stdout+run.stderr)
                    results.append(dict(words=words,clk_div=divider,case=case,zero_response=mode,
                                        payload_crc32=manifest['payload_crc32'],log=run.stdout.strip()))
        # Host format/range validation, independent of RTL parsing.
        vals=load_words(SRC/'weights/cnn_ddr_blob.mem');image,manifest=build_image(vals)
        assert len(vals)==52239 and len(image)==104510 and manifest['payload_crc32']=='AF01A61B'
        validate_image(image)
        host_rejects=0
        for corrupt in [image[:-1],image+b'\x00',b'\x00'+image[1:],image[:32]+bytes([image[32]^1])+image[33:]]:
            try:validate_image(corrupt)
            except ValueError:host_rejects+=1
            else:raise AssertionError('host accepted corrupt image')
        for binary,base,capacity in [(b'x'*(0x600000+1),0x600000,0x1000000),(b'x',0x600001,0x1000000),(b'x',0xff0000,0x1000000)]:
            try:pack_flash(binary,image,base,capacity)
            except ValueError:host_rejects+=1
            else:raise AssertionError('host accepted overlapping/overflow partition')
        assert host_rejects==7
        assert image[:4]==b'BPF1' and image[32:34]==bytes.fromhex('7305')
        result=dict(passed=True,tests=results,full_model_manifest=manifest,
                    model_mem_sha256=hashlib.sha256((SRC/'weights/cnn_ddr_blob.mem').read_bytes()).hexdigest(),
                    hardware_tested=False,host_invalid_cases_rejected=host_rejects)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(f'PASS {len(results)} SPI/DDR cases and host format checks',flush=True)
if __name__=='__main__':main()
