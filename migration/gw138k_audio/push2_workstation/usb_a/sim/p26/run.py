#!/usr/bin/env python3
"""P26 focused direct screen-FIFO and unchanged scheduler checks."""
from pathlib import Path
from datetime import datetime
import hashlib,json,re,shutil,subprocess,sys,xml.etree.ElementTree as ET

here=Path(__file__).resolve().parent
usb_a=here.parents[1]
build=Path(sys.argv[1]).resolve()
out=build/datetime.now().strftime('p26_latency_%H%M%S_%f');out.mkdir();print(out,flush=True)
src=build/'Prj1/src/usb_a';fw=build/'firmware'
tb=out/'tb_screen_fifo_streamer.sv';shutil.copy2(here/tb.name,tb)
latency_tb=out/'tb_interaction_latency.sv';shutil.copy2(here/latency_tb.name,latency_tb)
rtl=[src/'push2_screen_fifo_streamer.sv',src/'usbh_core.sv',src/'usbh_sie.sv',
     src/'usbh_crc5.sv',src/'usbh_crc16.sv',src/'usbh_fifo.sv',tb]
assert (usb_a/'firmware.c').read_bytes()==(fw/'firmware.c').read_bytes()
project=build/'Prj1'
all_sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList')
    if f.get('type')=='file.verilog']
audio_sources=[f for f in all_sources if not any(x in str(f.relative_to(project)) for x in
    ['vendor/','src/memory/','src/platform/','src/top/','src/ae350/riscv_',
     'workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
inputs=rtl+[latency_tb,*audio_sources,usb_a/'firmware.c',usb_a/'sim/test_hotplug.c',
    fw/'usb/usb_hw.h',Path(__file__)]
(out/'inputs.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in inputs},indent=2)+'\n')
commands=[
 ('rtl_compile',['iverilog','-g2012','-s','tb_screen_fifo_streamer','-I'+str(src),
    '-o',str(out/'rtl_test'),*map(str,rtl)]),
 ('rtl_simulation',['vvp',str(out/'rtl_test')]),
 ('firmware_compile',['gcc','-std=c99','-O2','-I'+str(fw),'-I'+str(fw/'usb'),
    str(usb_a/'sim/test_hotplug.c'),'-o',str(out/'firmware_test')]),
 ('firmware_simulation',[str(out/'firmware_test')]),
 ('latency_compile',['verilator','--binary','--timing','-O3','-j','4','-Wno-fatal',
    '--top-module','tb_interaction_latency','--Mdir',str(out/'latency_obj'),
    '-I'+str(project),'-I'+str(src),*map(str,audio_sources),str(latency_tb)])]
logs={}
for name,command in commands:
    log=out/(name+'.log')
    with log.open('w') as stream:result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
    logs[name]=log.read_text()
    if result.returncode:print(logs[name][-8000:]);raise SystemExit(result.returncode)
    for line in logs[name].splitlines():
        if line.startswith(('PASS','packet=')):print(line,flush=True)
cycles=[]
for line in logs['rtl_simulation'].splitlines():
    if line.startswith('packet=') and 'pixel_stalls=0' in line:cycles.append(int(line.rsplit('=',1)[1]))
assert cycles==[769,769],cycles
latency_rows=[]
latency_pattern=re.compile(r'LATENCY source=(\d+) offset_ns=(\d+) wire_us=([\d.]+) '
    r'source_to_core_us=([\d.]+) complete_to_core_us=([-\d.]+) '
    r'source_to_pcm32_us=([\d.]+) source_to_dac16_us=([\d.]+)')
for source,name in enumerate(['push_mmio','computer_115200','din_31250']):
    for offset in [0,5000,10000,15000,20000]:
        command=[str(out/'latency_obj/Vtb_interaction_latency'),f'+SOURCE={source}',f'+OFFSET_NS={offset}']
        log=out/f'latency_{name}_{offset}.log'
        with log.open('w') as stream:result=subprocess.run(command,cwd=project,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:print(log.read_text()[-8000:]);raise SystemExit(result.returncode)
        match=latency_pattern.search(log.read_text());assert match,log.read_text()
        values=list(map(float,match.groups()[2:]))
        latency_rows.append(dict(source=name,offset_ns=offset,wire_us=values[0],
            source_to_core_us=values[1],complete_to_core_us=values[2],
            source_to_pcm32_us=values[3],source_to_dac16_us=values[4]))
for name in ['push_mmio','computer_115200','din_31250']:
    rows=[row for row in latency_rows if row['source']==name]
    print('LATENCY',name,'dac16_us',min(r['source_to_dac16_us'] for r in rows),
        max(r['source_to_dac16_us'] for r in rows),flush=True)
result=dict(passed=True,hardware_tested=False,baseline_packet_load_cycles=1793,
    candidate_packet_load_cycles=769,clock_hz=48000000,
    baseline_packet_load_us=1793/48,candidate_packet_load_us=769/48,
    saved_per_packet_cycles=1024,saved_per_frame_cycles=1024*640,
    saved_per_frame_ms=1024*640/48000000*1000,
    frame_payload_floor_ms=327696*8/12000000*1000,
    protocol='unchanged 16-byte header plus 640 512-byte pixel blocks',
    scheduler='unchanged MIDI poll every 4 pixel blocks, lights every 32 blocks, ACK-only PID toggles',
    digital_audio_latency=latency_rows,
    latency_boundaries=dict(push_mmio='firmware MMIO word accepted after USB IN; excludes physical pad and host poll',
        computer_115200='first UART start bit through final 16-bit DAC observation',
        din_31250='first UART start bit through final 16-bit DAC observation'))
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
