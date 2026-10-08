#!/usr/bin/env python3
"""Build the complete deployed full85 workstation with CNN Flash boot added.

Never operates hardware or edits LATEST_WORKSTATION. Prepare/SYN use no
UserCode. Full builds require a fresh explicit UserCode and retain the frozen
DDR/display/audio sources, clock constraints and timing checks.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from build_full_song_83_bp_ddr_isolation import FROZEN
from workstation_memory import audit
from build_cnn_flash_image import build_image,load_words,pack_flash,gowin_data_fs
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1'
BASE_FS_SHA='7f96a42b0adf4e87863089d610a454e570876a78c7917d892949116918015444'
OVERLAYS=[f'rtl/music/{name}' for name in (
    'basic_pitch_pcm_pipeline.sv','basic_pitch_workstation_link.sv',
    'basic_pitch_uart_model_loader.sv','basic_pitch_flash_model_loader.sv',
    'basic_pitch_boot_model_loader.sv','basic_pitch_flash_map.svh')]
CST='''// SOM configuration Flash, x1 SPI after FPGA configuration (MSPI-as-GPIO).
// GW5AST-LV138PG484AC2/I1; board PCB nets and UG986 PG484A agree.
IO_LOC "flash_clk" L12;
IO_PORT "flash_clk" IO_TYPE=LVCMOS33 PULL_MODE=DOWN DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_cs_n" T19;
IO_PORT "flash_cs_n" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_mosi" P22;
IO_PORT "flash_mosi" IO_TYPE=LVCMOS33 PULL_MODE=NONE DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_miso" R22;
IO_PORT "flash_miso" IO_TYPE=LVCMOS33 PULL_MODE=UP BANK_VCCIO=3.3;
// IO2/WP and IO3/HOLD released high for read-only x1 SPI. Board pull-ups also
// keep them high during configuration and before user logic takes ownership.
IO_LOC "flash_wp_n" P21;
IO_PORT "flash_wp_n" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_hold_n" R21;
IO_PORT "flash_hold_n" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8 BANK_VCCIO=3.3;
'''
SDC='''
# New calibration level CDC; only the first sampling D pin is asynchronous.
set_false_path -to [get_pins {u_music/model_memory_meta*/D}]
# Conservatively constrain the NOR input relative to the 50-MHz sampling clock.
# SPI toggles every 4 clk50 cycles (6.25 MHz); 15 ns allows NOR tCLQV+PCB flight.
# No blanket input false-path or relaxation of existing workstation clocks.
set_input_delay 15.000 -clock [get_clocks {clk_50m}] [get_ports {flash_miso}]
'''

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_json(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def used_codes():
    codes=set()
    for p in list(ROOT.glob('*.json'))+list((ROOT/'reports').glob('*.json'))+list((ROOT/'results').rglob('*metadata.json')):
        # A failed attempt that emitted no bitstream did not release a code.
        status=p.parent/'tool_result.json'
        if status.exists() and not (p.parent/'Prj1/impl/pnr/Prj1.fs').exists():
            try:
                if json.loads(status.read_text())['exit_code']!=0:continue
            except (KeyError,ValueError):pass
        try:codes.update(int(s,16) for s in re.findall(r'0x([0-9A-Fa-f]{8})',p.read_text()))
        except (OSError,UnicodeError):continue
    return codes

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--flow',choices=('prepare','syn','all','pnr'),default='syn')
    ap.add_argument('--output',type=Path)
    ap.add_argument('--user-code')
    ap.add_argument('--synthesis-from',type=Path,help='reuse identical successful RTL synthesis after a CST-only failure')
    args=ap.parse_args()
    if args.synthesis_from and args.flow!='all':ap.error('--synthesis-from requires --flow all')
    if args.flow=='all' and (not args.user_code or not re.fullmatch('[0-9A-Fa-f]{8}',args.user_code) or int(args.user_code,16)==0):
        ap.error('--flow all requires a fresh nonzero eight-hex-digit --user-code')
    if args.flow in ('prepare','syn') and args.user_code:ap.error('Prepare/SYN assign no UserCode')
    if args.flow=='all' and int(args.user_code,16) in used_codes():ap.error('UserCode already recorded')
    if args.flow=='pnr' and (args.output is None or args.user_code):ap.error('PNR needs existing --output, keeps its original UserCode')
    output=(args.output or ROOT/'results'/datetime.now().strftime('workstation_flash_boot_%Y%m%d_%H%M%S_%f')).resolve()
    stage=output/'Prj1'
    if args.flow!='pnr':
        assert sha(BASE/'Prj1/impl/pnr/Prj1.fs')==BASE_FS_SHA,'deployed bitstream drift'
        originals=json.loads((BASE/'workstation_inputs.json').read_text())
        assert all(sha(BASE/'Prj1'/p)==h for p,h in originals.items()),'deployed source drift'
        assert not output.exists(),'refusing to overwrite candidate'
        shutil.copytree(BASE/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','*.user','__pycache__'))
        for rel in OVERLAYS:shutil.copy2(ROOT/rel,stage/rel)
        top=stage/'src/push2/gw138k_push_workstation_top.v';s=top.read_text()
        assert s.count('    input wire sd_miso,')==1
        s=s.replace('    input wire sd_miso,','''    input wire flash_miso,
    output wire flash_clk,flash_cs_n,flash_mosi,flash_wp_n,flash_hold_n,
    input wire sd_miso,''')
        assert s.count('    basic_pitch_workstation_link u_music (')==1
        s=s.replace('    basic_pitch_workstation_link u_music (','''    assign flash_wp_n=1'b1;
    assign flash_hold_n=1'b1;
    basic_pitch_workstation_link #(.USE_FLASH_WEIGHTS(1'b1)) u_music (''')
        anchor='.memory_calibrated(memory_calibrated),.model_serial(pc_uart_rx_i),'
        assert s.count(anchor)==1
        s=s.replace(anchor,anchor+'\n        .flash_miso(flash_miso),.flash_cs_n(flash_cs_n),.flash_clk(flash_clk),.flash_mosi(flash_mosi),')
        top.write_text(s)
        tree=ET.parse(stage/'Prj1.gprj');fl=tree.find('FileList');present={f.attrib['path'] for f in fl}
        for rel in OVERLAYS:
            if rel not in present and not rel.endswith('.svh'):
                ET.SubElement(fl,'File',path=rel,type='file.cst' if rel.endswith('.cst') else 'file.verilog',enable='1')
        tree.write(stage/'Prj1.gprj',encoding='UTF-8',xml_declaration=True)
        # Gowin supports one active CST; a second CST replaces the first.
        cst_files=[f.attrib['path'] for f in fl if f.attrib['type']=='file.cst' and f.attrib.get('enable')=='1']
        assert cst_files==['constraints/tang_mega_138k.cst'],'baseline must have one complete pin CST'
        cst=stage/cst_files[0];cst.write_text(cst.read_text()+'\n'+CST)
        sdc=stage/'constraints/tang_mega_138k.sdc';sdc.write_text(sdc.read_text()+SDC)
        tcl=stage/'scripts/build.tcl';s=tcl.read_text()
        assert 'set_option -use_mspi_as_gpio 1' in s and 'set_option -use_cpu_as_gpio 1' in s
        s=re.sub(r'(?m)^set_option -(?:user_code|inc_pnr).*\n','',s)
        if args.user_code:s=s.replace('set flow all','set_option -user_code '+args.user_code.upper()+'\nset flow all')
        tcl.write_text(s)
        inputs={str(p.relative_to(stage)):sha(p) for p in stage.rglob('*') if p.is_file()}
        changed=sorted(p for p,h in inputs.items() if originals.get(p)!=h)
        allowed=set(OVERLAYS+['src/push2/gw138k_push_workstation_top.v','Prj1.gprj','scripts/build.tcl',
                             'constraints/tang_mega_138k.cst','constraints/tang_mega_138k.sdc'])
        assert set(changed)==allowed,(changed,allowed)
        write_json(output/'workstation_inputs.json',inputs)
        write_json(output/'build_metadata.json',dict(baseline=str(BASE.relative_to(ROOT)),baseline_fs_sha256=BASE_FS_SHA,
            user_code=('0x'+args.user_code.upper()) if args.user_code else None,changed_from_base=changed,
            git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            hardware_tested=False,flash_model_base='0x00600000',full_workstation=True))
        image,manifest=build_image(load_words(stage/'rtl/music/weights/cnn_ddr_blob.mem'))
        assert manifest['word_count']==52239 and manifest['payload_crc32']=='AF01A61B'
        (output/'cnn_model.bin').write_bytes(image);(output/'cnn_model.data.fs').write_text(gowin_data_fs(image));write_json(output/'cnn_model.json',manifest)
    else:
        inputs=json.loads((output/'workstation_inputs.json').read_text())
        assert json.loads((output/'build_metadata.json').read_text())['user_code'],'PNR release needs assigned code'
    if args.synthesis_from:
        previous=args.synthesis_from.resolve();old_inputs=json.loads((previous/'workstation_inputs.json').read_text())
        assert all(sha(previous/'Prj1'/p)==h for p,h in old_inputs.items()),'old synthesis input drift'
        exceptions={'Prj1.gprj','constraints/cnn_flash.cst','constraints/tang_mega_138k.cst'}
        assert {p:h for p,h in inputs.items() if p not in exceptions}=={p:h for p,h in old_inputs.items() if p not in exceptions},'synthesis reuse requires exact RTL/IP/memory/options'
        oldsyn=previous/'Prj1/impl/gwsynthesis'
        assert 'GowinSynthesis finish' in (previous/'gowin_all.log').read_text() and (oldsyn/'Prj1.vg').exists()
        assert not (previous/'Prj1/impl/pnr/Prj1.fs').exists(),'CST repair reuse is for unreleased failure only'
        shutil.copytree(oldsyn,stage/'impl/gwsynthesis')
        m=json.loads((output/'build_metadata.json').read_text());m['synthesis_from']=str(previous.relative_to(ROOT));m['cst_repair']='append Flash pins to the single original complete CST';write_json(output/'build_metadata.json',m)
    for rel,(staged,h) in FROZEN.items():assert sha(ROOT/rel)==sha(stage/staged)==h,rel
    assert all(sha(stage/p)==h for p,h in inputs.items()),'candidate input drift'
    print(output,flush=True)
    if args.flow=='prepare':return
    actual_flow='pnr' if args.synthesis_from else args.flow
    with (output/('gowin_'+args.flow+'.log')).open('w') as log:
        run=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,
                           env=dict(os.environ,PRJ1_FLOW=actual_flow),stdout=log,stderr=subprocess.STDOUT)
    changed=[p for p,h in inputs.items() if sha(stage/p)!=h]
    record=dict(exit_code=run.returncode,flow=args.flow,inputs_unchanged=not changed,changed=changed,hardware_tested=False)
    write_json(output/'tool_result.json',record)
    if run.returncode or changed:raise SystemExit('build/input check failed: '+str(output))
    report=audit(output,'full' if args.flow in ('all','pnr') else 'synthesis_only')
    print('SYN BSRAM',report['bsram'],'PNR BSRAM',report.get('pnr_bsram'),flush=True)
    if args.flow in ('all','pnr'):
        assert report['pnr_available'] and report['pnr_bsram']<=260,'Flash boot added BSRAM'
        fs=stage/'impl/pnr/Prj1.fs';binary=stage/'impl/pnr/Prj1.bin'
        code=json.loads((output/'build_metadata.json').read_text())['user_code']
        assert re.search(r'//UserCode: (0x[0-9A-Fa-f]{8})',fs.read_text()[:1000])[1].lower()==code.lower()
        packed,manifest=pack_flash(binary.read_bytes(),(output/'cnn_model.bin').read_bytes())
        (output/'workstation_with_cnn.bin').write_bytes(packed)
        manifest.update(bitstream_fs_sha256=sha(fs),bitstream_bin_sha256=sha(binary),user_code=code,
                        boot_image_sha256=sha(output/'workstation_with_cnn.bin'))
        write_json(output/'flash_bundle.json',manifest)
        print('FLASH BUNDLE',output/'workstation_with_cnn.bin',flush=True)
if __name__=='__main__':main()
