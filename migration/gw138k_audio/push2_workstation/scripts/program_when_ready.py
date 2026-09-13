#!/usr/bin/env python3
"""Wait for user-selected CH569 ISP mode; read config, check target, flash + verify.

This writes CH569 program Flash. Never alters the boot pin or debug setting.
The bridge leaves USB off until an explicit FPGA HSPI Host-enable command.
"""
from pathlib import Path
from datetime import datetime
import argparse, hashlib, json, os, subprocess, time

BASE = Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("build", type=Path)
    ap.add_argument("--timeout", type=float, default=3600)
    args=ap.parse_args(); build=args.build.resolve()
    manifest=json.loads((build/"build.json").read_text())
    for name in ["probe.bin", "wch-ch56x-isp"]:
        assert hashlib.sha256((build/name).read_bytes()).hexdigest() == manifest["outputs"][name]
    out=BASE/"results"/datetime.now().strftime("program_%Y%m%d_%H%M%S_%f");out.mkdir()
    result={"build":str(build),"firmware_sha256":manifest["outputs"]["probe.bin"],
            "flash_attempted":False,"verified":False,"midi_accepted":False}
    def save(): (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    save();print(out,flush=True)
    print("Waiting for CH569 ISP 4348:55e0. No flash writes before identity/config checks.",flush=True)
    deadline=time.monotonic()+args.timeout
    last_node=None
    while time.monotonic() < deadline:
        found=[]
        for p in Path("/sys/bus/usb/devices").glob("*"):
            try:
                if (p/"idVendor").read_text().strip()=="4348" and (p/"idProduct").read_text().strip()=="55e0":
                    node=Path('/dev/bus/usb')/f'{int((p/"busnum").read_text()):03d}'/f'{int((p/"devnum").read_text()):03d}'
                    if node != last_node:
                        result['isp_seen']=True;result['isp_device_node']=str(node);save()
                        print('ISP detected at '+str(node)+'; waiting for USB access ACL.',flush=True)
                        last_node=node
                    # sysfs can precede the device node and desktop uaccess ACL.
                    if os.access(node,os.R_OK|os.W_OK): found.append(p.name)
            except (OSError,FileNotFoundError): pass
        if found: break
        time.sleep(.15)
    else:
        result["error"]="No accessible CH569 ISP connection acquired before watcher deadline";save();return
    if len(found)!=1: raise RuntimeError("Multiple WCH ISP devices; no programming")
    result["usb_path"]=found[0];save()
    def invoke(flags, log):
        cmd=[str(build/"wch-ch56x-isp"), *flags]
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        (out/log).write_bytes(p.stdout)
        text=p.stdout.decode(errors="replace");print(text,flush=True)
        if p.returncode: raise RuntimeError(f"{log}: ISP exit {p.returncode}")
        return text
    try:
        config=invoke(["-c"],"config_before.log")
        for expected in ["Found chip: CH569 [0x1069]", "Chip uid: CE 18 BA 10 53 5C DB 85", "nv=0xCFFFF245", "alt boot pin: PA13", "[6] BOOT_EN 1: enabled"]:
            if expected not in config: raise RuntimeError("Config guard failed: "+expected)
        result["config_checked"]=True;result["flash_attempted"]=True;save()
        programmed=invoke(["-c","-v","-r","-f",str(build/"probe.bin")],"flash_verify.log")
        if "isp_verify end with success" not in programmed: raise RuntimeError("No verify success marker")
        if "alt boot pin: PA13" not in programmed: raise RuntimeError("Missing post-program boot pin report")
        result["verified"]=True
    except Exception as e:
        result["error"]=str(e)
        raise
    finally: save()

if __name__ == "__main__": main()
