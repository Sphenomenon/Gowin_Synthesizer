#!/usr/bin/env python3
"""NOR->internal 8N1->original BPN1->DDR compatibility transport tests."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
from build_cnn_flash_image import build_image,load_words
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'rtl/music'
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path)
    args=ap.parse_args();results=[]
    with tempfile.TemporaryDirectory(prefix='bp_flash_serial_') as tmp:
        tmp=Path(tmp)
        for words,baud,cases in [(31,3125000,list(range(13))),(1,3125000,[0]),(31,115200,[0]),(52239,3125000,[0])]:
            vals=load_words(SRC/'weights/cnn_ddr_blob.mem') if words==52239 else [(i*7919^0xA53C)&65535 for i in range(words)]
            image,m=build_image(vals);p=tmp/f'{words}_{baud}.hex';p.write_text('\n'.join(f'{b:02x}' for b in image)+'\n')
            exe=tmp/f'{words}_{baud}.vvp'
            sources=[ROOT/'sim/model_flash/tb_flash_serial_boot.sv']+[SRC/n for n in ('basic_pitch_flash_serial_boot.sv','basic_pitch_flash_model_loader.sv','basic_pitch_flash_io_guard.sv','basic_pitch_uart_model_loader.sv','basic_pitch_uart_rx.sv')]+[ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1/src/control/uart_tx.v']
            cmd=['iverilog','-g2012','-I',str(SRC),'-s','tb_flash_serial_boot','-P',f'tb_flash_serial_boot.WORDS={words}','-P',f'tb_flash_serial_boot.BAUD={baud}','-o',str(exe)]+[str(s) for s in sources]
            subprocess.run(cmd,check=True,capture_output=True,text=True)
            for case in cases:
                run=subprocess.run(['vvp',str(exe),f'+IMAGE={p}',f'+CASE={case}'],capture_output=True,text=True,timeout=180)
                print(run.stdout.strip(),flush=True)
                assert run.returncode==0 and 'PASS serial' in run.stdout,run.stdout+run.stderr
                results.append(dict(words=words,baud=baud,case=case,payload_crc32=m['payload_crc32'],log=run.stdout.strip()))
        d=dict(passed=True,tests=results,hardware_tested=False,pcm_saved=False,internal_protocol_only=True,
            source_sha256={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
            notes='Default fast simulation uses 16 clocks/bit; separate case uses actual 50MHz/115200 timing. Independent NOR and DDR address/content/order/backpressure oracle; precheck faults emit no DDR writes. Full model is 52239 words.')
        if args.output:args.output.write_text(json.dumps(d,indent=2)+'\n')
        print(f'PASS {len(results)} serial-transport cases',flush=True)
if __name__=='__main__':main()
