#!/usr/bin/env python3
"""Identify the 138K debugger, program SRAM, verify UserCode, leave Flash intact."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
from netlist import connector_wiring

ROOT = Path(__file__).resolve().parent
SERIAL = '2025030317'
PROGRAMMER = Path.home() / '.local/opt/gowin-1.9.12.03/Programmer/bin/programmer_cli'

def debugger():
    matches = []
    for path in Path('/sys/bus/usb/devices').iterdir():
        try:
            if ((path/'idVendor').read_text().strip(), (path/'idProduct').read_text().strip(),
                (path/'serial').read_text().strip()) == ('0403', '6010', SERIAL):
                matches.append(path)
        except (FileNotFoundError, OSError):
            continue
    if len(matches)!=1:
        raise RuntimeError(f'未找到唯一的 138K 下载器 {SERIAL}，当前匹配 {len(matches)} 个；请连接板卡的 USB JTAG/UART')
    return matches[0]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--location', type=int, help='explicit programmer cable location; normally read from USB topology')
    parser.add_argument('--inventory', action='store_true')
    args = parser.parse_args()
    try:
        usb = debugger()
    except RuntimeError as error:
        print(error)
        raise SystemExit(2)
    # Existing verified records: sysfs 3-5 => 0x35 = 53, 3-6 => 0x36 = 54.
    # The bus occupies the upper nibble, the direct USB port the lower nibble.
    # Hubs or larger indices require the explicitly scanned programmer location.
    match = re.fullmatch(r'(\d+)-(\d+)', usb.name)
    if args.location is None and not match:
        parser.error('下载器连接经过 Hub，请用 --location 指定 --scan-cables L 返回的位置')
    if args.location is None and (int(match[1])>15 or int(match[2])>15):
        parser.error('USB 编号超出已核对的直连编码，请用 --location 指定扫描值')
    location = args.location if args.location is not None else ((int(match[1]) << 4) | int(match[2]))
    common = [str(PROGRAMMER), '--device','GW5AST-138C','--cable-index','5',
              '--location',str(location),'--frequency','0.9MHz']
    if args.inventory:
        result = subprocess.run([str(PROGRAMMER), '--scan-cables','L'], capture_output=True,text=True,timeout=30)
        print(json.dumps(dict(usb=str(usb),location=location,serial=SERIAL),indent=2))
        print(result.stdout+result.stderr)
        raise SystemExit(result.returncode)
    build = args.build.resolve() if args.build else Path((ROOT/'LATEST_BUILD.txt').read_text().strip())
    meta = json.loads((build/'build.json').read_text())
    if not meta.get('bitstream_generated') or not meta.get('routed_timing_passed'):
        parser.error('未通过构建')
    if meta.get('superseded') or not meta.get('netlist_wiring_verified') or meta['wiring']!=connector_wiring()[1]:
        parser.error('位流引脚未通过当前网表追线校验，请重新构建')
    fs = build/'impl/pnr/touchboard.fs'
    for name,digest in meta['inputs'].items():
        if hashlib.sha256((build/name).read_bytes()).hexdigest()!=digest:
            parser.error(f'构建输入已变化：{name}')
    if hashlib.sha256((ROOT/'input_netlist.tel').read_bytes()).hexdigest()!=meta['netlist_sha256']:
        parser.error('网表已变化，请重新构建')
    digest = hashlib.sha256(fs.read_bytes()).hexdigest()
    if digest!=meta['bitstream_sha256']:
        parser.error('位流 hash 不符')
    header=fs.read_text()[:2000]
    if '//Device Version: C' not in header or '//Part Number: GW5AST-LV138PG484AC2/I1' not in header:
        parser.error('位流器件不符')
    code=re.search(r'//UserCode: (0x[0-9a-fA-F]+)',header)[1]
    if code.lower()!=meta['user_code'].lower():
        parser.error('UserCode 不符')
    output=ROOT/'results'/datetime.now().strftime('sram_%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True)
    evidence=dict(started_at=datetime.now().astimezone().isoformat(),build=str(build),bitstream_sha256=digest,
                  target_code=code,usb=str(usb),location=location,serial=SERIAL,
                  flash_written=False,hardware_touch_verified=False,operations=[])
    with Path('/tmp/gw138k_2025030317.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        for name,extra in [('before',['--operation_index','0']),
                           ('sram',['--operation_index','2','--fsFile',str(fs)]),
                           ('after',['--operation_index','0'])]:
            debugger() # Check identity again immediately before each operation.
            command=common+extra
            print(name,flush=True)
            result=subprocess.run(command,capture_output=True,text=True,timeout=180)
            text=result.stdout+result.stderr
            (output/(name+'.log')).write_text(text)
            success=(result.returncode==0 and 'Finished.' in text and not re.search(r'\b(error|failed|failure)\b',text,re.I))
            if name in ('sram','after'):
                success=success and ('User Code is: '+code).lower() in text.lower()
            if name=='before':
                old_code=re.search(r'User Code is:\s*(0x[0-9a-fA-F]+)',text,re.I)
                success=success and old_code is not None
                evidence['previous_code']=old_code[1] if old_code else None
            evidence['operations'].append(dict(name=name,passed=success,command=command))
            (output/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
            print(text,flush=True)
            if not success: raise SystemExit(f'{name} 未通过，详见 {output}')
        evidence['sram_programmed']=True
        (output/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
        meta['sram_programmed']=True
        meta['programming_evidence']=str(output)
        (build/'build.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(f'SRAM 下载并读回通过：{code}；现在可打开 monitor.py --gui',flush=True)

if __name__=='__main__':
    main()
