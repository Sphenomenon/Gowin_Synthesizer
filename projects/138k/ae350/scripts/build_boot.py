#!/usr/bin/env python3
"""Freeze, compile and build the standalone AE350 SRAM boot probe."""
import argparse,datetime,hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
WORKSPACE=PROJECT.parents[1]
TEAM=WORKSPACE/'Mega_138K/Dev/Prj1'
CC=Path('/home/sphenicidition/.local/opt/amd/2025.2.1/gnu/riscv/lin/bin/riscv64-unknown-elf-gcc')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flow',choices=['syn','all'],default='all')
    args=parser.parse_args()
    out=PROJECT/'results'/datetime.datetime.now().strftime('ae350_boot_build_%Y%m%d_%H%M%S_%f')
    out.mkdir();stage=out/'project';stage.mkdir()
    for name in ['rtl','vendor','firmware','constraints']:shutil.copytree(ROOT/name,stage/name)
    shutil.copy2(ROOT/'vendor/riscv_ae350_config.v',stage/'riscv_ae350_config.v')
    for source in [TEAM/'src/platform/reset_release.v',TEAM/'src/control/uart_tx.v',TEAM/'vendor/sipeed_dvi/video_pll_init.v']:
        shutil.copy2(source,stage/'vendor'/source.name)
    command=[str(CC),'-march=rv32im_zicsr','-mabi=ilp32','-nostdlib','-nostartfiles','-Wl,--build-id=none',
        '-Wl,-T,firmware/boot.ld','-o','firmware/boot.elf','firmware/boot.S']
    p=subprocess.run(command,cwd=stage,capture_output=True,text=True);(out/'firmware.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise SystemExit('Firmware failed: '+str(out))
    objcopy=CC.with_name('riscv64-unknown-elf-objcopy')
    subprocess.run([str(objcopy),'-O','binary','firmware/boot.elf','firmware/boot.bin'],cwd=stage,check=True)
    binary=(stage/'firmware/boot.bin').read_bytes()
    if len(binary)>16384:raise SystemExit('Boot ROM overflow')
    binary+=bytes(16384-len(binary))
    (stage/'firmware/boot.mem').write_text(''.join(f'{int.from_bytes(binary[i:i+4],"little"):08x}\n' for i in range(0,len(binary),4)))
    dis=subprocess.run([str(CC.with_name('riscv64-unknown-elf-objdump')),'-d','firmware/boot.elf'],cwd=stage,capture_output=True,text=True,check=True)
    (out/'firmware.dis').write_text(dis.stdout)
    files=[*sorted((stage/'rtl').glob('*')), *sorted((stage/'vendor').glob('*.v'))]
    entries=''.join(f'<File path="{p.relative_to(stage)}" type="file.verilog" enable="1"/>\n' for p in files)
    entries+='<File path="constraints/boot.cst" type="file.cst" enable="1"/>\n<File path="constraints/boot.sdc" type="file.sdc" enable="1"/>\n'
    (stage/'boot.gprj').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<Project><Template>FPGA</Template><Version>5</Version><Device name="GW5AST-138C" pn="GW5AST-LV138PG484AC2/I1">gw5ast138c-006</Device><FileList>'+entries+'</FileList></Project>\n')
    (stage/'build.tcl').write_text('open_project boot.gprj\nset_option -top_module gw138k_ae350_boot_top\nset_option -output_base_name boot\nset_option -verilog_std sysv2017\nset_option -use_sspi_as_gpio 1\nset_option -use_mspi_as_gpio 1\nset_option -use_cpu_as_gpio 1\nset_option -timing_driven 1\nset_option -correct_hold_violation 1\nset_option -place_option 2\nset_option -route_option 1\nset_option -gen_text_timing_rpt 1\nset_option -gen_sdf 1\nset_option -gen_verilog_sim_netlist 1\nrun '+args.flow+'\n')
    hashes={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
    (out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(out,flush=True)
    with (out/'gowin.log').open('w') as log:p=subprocess.run(['gw_sh','build.tcl'],cwd=stage,stdout=log,stderr=subprocess.STDOUT)
    changed=[f for f,h in hashes.items() if hashlib.sha256((stage/f).read_bytes()).hexdigest()!=h]
    (out/'tool_result.json').write_text(json.dumps({'exit_code':p.returncode,'inputs_unchanged':not changed,'changed':changed,'flow':args.flow,'timing_audited':False,'hardware_tested':False},indent=2)+'\n')
    print('Tool finished',p.returncode,'; timing/netlist audit required',flush=True)
    return p.returncode or bool(changed)
if __name__=='__main__':raise SystemExit(main())
