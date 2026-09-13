#!/usr/bin/env python3
"""Stage the preserved full audio/display design, then add the real AE350."""
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
TEAM=ROOT.parents[2]/'Mega_138K/Dev/Prj1'
sys.path.insert(0,str(TEAM/'scripts'))
from gowin_paths import gowin_shell,gowin_simlib
from build_boot import CC

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-ddr',action='store_true',help='include CPU external DDR bridge and read-owner arbitration')
    parser.add_argument('--with-ui',action='store_true',help='include AE350 UI pages and frame-boundary publication (implies DDR)')
    parser.add_argument('--with-usb',action='store_true',help='include pure RTL FS USB-MIDI host (implies UI and DDR)')
    parser.add_argument('--prepare-only',action='store_true',help='freeze all inputs without launching Gowin')
    args=parser.parse_args()
    if args.with_usb:args.with_ui=True
    if args.with_ui:args.with_ddr=True
    out=PROJECT/'results'/datetime.datetime.now().strftime('ae350_workstation_build_%Y%m%d_%H%M%S_%f')
    # The base manifest remains historical; final inputs are frozen separately.
    subprocess.run([sys.executable,str(PROJECT/'scripts/build.py'),'--prepare-only','--output',str(out)],check=True)
    stage=out/'Prj1';dest=stage/'src/ae350';dest.mkdir()
    for source in (ROOT/'video').glob('*.v'):
        shutil.copy2(source,stage/'src/video'/source.name)
    if args.with_ddr:
        shutil.copy2(ROOT/'ddr/hdmi_display.v',stage/'src/video/hdmi_display.v')
        for source in (ROOT/'ddr').glob('*.sv'):shutil.copy2(source,dest/source.name)
        shutil.copy2(ROOT/'ddr/gw138k_ddr_workstation_top.v',dest/'gw138k_ddr_workstation_top.v')
    if args.with_ui:
        for name in ['hdmi_display.v','video_ddr_scanout.v']:shutil.copy2(ROOT/'ui'/name,stage/'src/video'/name)
        for source in (ROOT/'ui').glob('*.sv'):shutil.copy2(source,dest/source.name)
        shutil.copy2(ROOT/'ui/gw138k_ui_workstation_top.v',dest/'gw138k_ui_workstation_top.v')
    for source in list((ROOT/'vendor').glob('*.v'))+[
            ROOT/'rtl/gw138k_cpu_pll_cell.v',ROOT/'rtl/gw138k_boot_memory.sv']+list((ROOT/'integration').glob('*.v'))+list((ROOT/'integration').glob('*.sv')):
        shutil.copy2(source,dest/source.name)
    shutil.copy2(ROOT/'vendor/riscv_ae350_config.v',stage/'riscv_ae350_config.v')
    for suffix in ['sdc','cst']:
        shutil.copy2(ROOT/'integration'/('workstation.'+suffix),stage/'constraints'/('tang_mega_138k.'+suffix))
    if args.with_ddr:
        with (stage/'constraints/tang_mega_138k.sdc').open('a') as f:f.write((ROOT/'ddr/ddr.sdc').read_text())
    if args.with_ui:
        with (stage/'constraints/tang_mega_138k.sdc').open('a') as f:f.write((ROOT/'ui/ui.sdc').read_text())
        with (stage/'constraints/tang_mega_138k.cst').open('a') as f:f.write('\nIO_LOC "pc_uart_rx_i" V14;\nIO_PORT "pc_uart_rx_i" IO_TYPE=LVCMOS33 PULL_MODE=UP;\n')
    if args.with_usb:
        usb=PROJECT/'usb_host'
        usb_dest=stage/'src/usb_host';usb_dest.mkdir()
        # Generation uses the local, pinned Amaranth environment; Python is a
        # build tool only. No USB instructions/firmware enter the bitstream.
        subprocess.run([str(usb/'.venv/bin/python'),str(usb/'scripts/generate.py'),
                        '--output',str(usb_dest/'gw138k_usb_host_core.v')],check=True)
        for source in list((usb/'rtl').glob('*.sv'))+list((usb/'integration').glob('*.v'))+list((usb/'integration').glob('*.sv')):
            shutil.copy2(source,usb_dest/source.name)
        shutil.copy2(usb/'vendor/usb_host_example/src/usb1_host/usb_fs_phy.v',usb_dest/'usb_fs_phy.v')
        for suffix in ['sdc','cst']:
            with (stage/('constraints/tang_mega_138k.'+suffix)).open('a') as f:
                f.write('\n'+(usb/'integration'/('usb.'+suffix)).read_text())
    firmware=stage/'firmware';firmware.mkdir(exist_ok=True)
    for source in [ROOT/'firmware/boot.ld',ROOT/'integration/services_main.c',PROJECT/'firmware/audio_services.h']:
        shutil.copy2(source,firmware/source.name)
    entry='services_main.c'
    if args.with_ddr:
        shutil.copy2(ROOT/'ddr/services_ddr.c',firmware/'services_ddr.c');entry='services_ddr.c'
    if args.with_ui:
        for source in list((ROOT/'ui').glob('*.c'))+list((ROOT/'ui').glob('*.h')):shutil.copy2(source,firmware/source.name)
        shutil.copy2(ROOT/'ui/ui.ld',firmware/'boot.ld');entry='ui_main.c'
    start=(ROOT/'firmware/boot.S').read_text()
    before=start.index('    li s1, 0');after=start.index('fail:',before)
    initialize=''
    if args.with_ui:
        initialize='''    la t0, __data_load_start
    la t1, __data_start
    la t2, __data_end
1:  bgeu t1, t2, 2f
    lw t3, 0(t0)
    sw t3, 0(t1)
    addi t0, t0, 4
    addi t1, t1, 4
    j 1b
2:  la t1, __bss_start
    la t2, __bss_end
3:  bgeu t1, t2, 4f
    sw zero, 0(t1)
    addi t1, t1, 4
    j 3b
4:
'''
    start=start[:before]+initialize+'    call services_main\n    j halt\n'+start[after:]
    (firmware/'start.S').write_text(start)
    cmd=[str(CC),'-march=rv32im_zicsr','-mabi=ilp32','-msmall-data-limit=0','-O2','-ffreestanding',
        '-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles','-Wl,--build-id=none',
        '-Wl,-T,firmware/boot.ld','-o','firmware/boot.elf','firmware/start.S','firmware/'+entry]
    if args.with_ui:cmd.extend(['firmware/ui_render.c','firmware/ui_runtime.c'])
    p=subprocess.run(cmd,cwd=stage,capture_output=True,text=True)
    (out/'firmware.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise SystemExit('firmware compile failed: '+str(out))
    subprocess.run([str(CC.with_name('riscv64-unknown-elf-objcopy')),'-O','binary','firmware/boot.elf','firmware/boot.bin'],cwd=stage,check=True)
    binary=(firmware/'boot.bin').read_bytes();assert len(binary)<=16384
    binary+=bytes(16384-len(binary))
    (firmware/'boot.mem').write_text(''.join(f'{int.from_bytes(binary[i:i+4],"little"):08x}\n' for i in range(0,len(binary),4)))
    tree=ET.parse(stage/'Prj1.gprj');files=tree.find('FileList')
    for source in sorted(dest.glob('*')):ET.SubElement(files,'File',path=source.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    if args.with_usb:
        for source in sorted(usb_dest.iterdir()):
            if source.suffix in ['.sv','.v']:ET.SubElement(files,'File',path=source.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    ET.indent(tree,space='    ');tree.write(stage/'Prj1.gprj',encoding='utf-8',xml_declaration=True)
    tcl=stage/'scripts/build.tcl'
    top='gw138k_ddr_workstation_top' if args.with_ddr else 'gw138k_workstation_top'
    if args.with_ui:top='gw138k_ui_workstation_top'
    if args.with_usb:top='gw138k_usb_workstation_top'
    tcl.write_text(tcl.read_text().replace('-top_module gw138k_audio_display_top','-top_module '+top).replace('set_option -use_mspi_as_gpio 1','set_option -use_mspi_as_gpio 1\nset_option -use_cpu_as_gpio 1'))
    hashes={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
    (out/'workstation_inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
    if args.prepare_only:
        (out/'prepared.json').write_text(json.dumps(dict(top_module=top,cpu_external_ddr=args.with_ddr,
            cpu_ui=args.with_ui,usb_rtl_host=args.with_usb,hardware_tested=False),indent=2)+'\n')
        print(out,flush=True)
        return 0
    env=dict(os.environ,PRJ1_FLOW='all',GOWIN_SIMLIB=str(gowin_simlib()),PRJ1_DDR_REFERENCE=str(next((out/'reference').glob('*.vo'))))
    print(out,flush=True)
    with (out/'gowin.log').open('w') as log:p=subprocess.run([str(gowin_shell()),'scripts/build.tcl'],cwd=stage,env=env,stdout=log,stderr=subprocess.STDOUT)
    changed=[f for f,h in hashes.items() if hashlib.sha256((stage/f).read_bytes()).hexdigest()!=h]
    (out/'tool_result.json').write_text(json.dumps(dict(exit_code=p.returncode,top_module=top,cpu_external_ddr=args.with_ddr,cpu_ui=args.with_ui,usb_rtl_host=args.with_usb,inputs_unchanged=not changed,changed=changed,timing_audited=False,hardware_tested=False),indent=2)+'\n')
    print('Tool finished',p.returncode,'; separate routed audit required',flush=True)
    return p.returncode or bool(changed)
if __name__=='__main__':raise SystemExit(main())
