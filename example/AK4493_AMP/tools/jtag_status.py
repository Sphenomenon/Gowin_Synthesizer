#!/usr/bin/env python3
"""Measure audio-domain clock/frame progress against the FPGA 50 MHz counter."""
import argparse, csv, datetime, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time
root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root.parent/'RTL8723DS'))
from program_sram import verified_artifact

def decode(path):
    rows=list(csv.reader(path.read_text().splitlines()))
    start=next(i for i,r in enumerate(rows) if r==['Data:'])
    header=rows[start+1][1].strip()
    widths={'audio_debug[159:0]':5,'audio_debug[351:0]':11}
    if header not in widths:raise ValueError('Unexpected capture layout')
    words=widths[header]
    samples=[]
    for row in rows[start+2:]:
        if not row:continue
        v=int(row[1].strip(),16);w=[(v>>(32*i))&0xffffffff for i in range(words)]
        if w[0]!=0x414d5031: raise ValueError('Invalid AMP1 signature')
        samples.append({'audio_clocks':w[1],'frames':w[2], 'pdn':bool(w[3]&1),
                        'smute':bool(w[3]&2),'restart_n':bool(w[3]&4),
                        'plug_det':bool(w[3]&8),'phase':(w[3]>>4)&3,'heartbeat':w[4]})
        if words>5:
            if w[5]!=0x41444335:raise ValueError('Invalid ADC5 signature')
            raw=w[6]&0x3fff; raw=raw if raw<8192 else raw-16384
            samples[-1]['vccio5']={'raw':raw,'volts':raw*8/2048,
                'minimum_raw':(w[6]>>14)&0x3fff,'maximum_raw':w[7]&0x3fff,
                'count':w[8],'timeouts':w[9],'flags':w[10]&255,
                'age_cycles_mod_16777216':w[10]>>8}
    if len(samples)!=128:raise ValueError('Need 128 samples')
    # GAO exports circular RAM with a small wrapped tail on this tool version.
    # Rotate at the backward counter jump so first/last are chronological.
    backwards=[i+1 for i in range(len(samples)-1)
               if ((samples[i+1]['heartbeat']-samples[i]['heartbeat'])&0xffffffff)>0x80000000]
    if len(backwards)>1:raise ValueError('Invalid capture chronology')
    if backwards:
        cut=backwards[0];samples=samples[cut:]+samples[:cut]
    if any(((b['heartbeat']-a['heartbeat'])&0xffffffff)!=1 for a,b in zip(samples,samples[1:])):
        raise ValueError('50 MHz capture counter is not consecutive')
    return samples

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=pathlib.Path,default=root/'reports/last_build.json')
    p.add_argument('--output',type=pathlib.Path,default=root/'reports/jtag_status.json')
    a=p.parse_args();artifact,_=verified_artifact(a.manifest,allow_gao=True)
    manifest=json.loads(a.manifest.read_text())
    ide=pathlib.Path(os.environ.get('GW138K_IDE_DIR','/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE'))
    result={'captured_at':datetime.datetime.now().astimezone().isoformat(),'artifact':artifact,
            'capture_valid':False,'digital_passed':False,'analog_verified':False,'passed':False}
    a.output.parent.mkdir(exist_ok=True)
    try:
        scan=subprocess.run([str(ide.parent/'Programmer/bin/programmer_cli'),'--scan-cables'],capture_output=True,text=True,timeout=15)
        locations=re.findall(r'Gowin USB Cable\(FT2CH\)/0/[^\n]*\(USB location:(\d+)\)',scan.stdout)
        if scan.returncode or len(locations)!=1:raise ValueError('Need one channel-0 FT2CH cable')
        result['usb_location']=locations[0];captures=[]
        with tempfile.TemporaryDirectory(prefix='amp-gao-',dir='/private/tmp') as tmp:
            folder=pathlib.Path(tmp);definition=folder/'audio.gao'
            shutil.copy2(manifest['gao'][0]['definition'],definition)
            for i in range(2):
                if i:time.sleep(1)
                prefix=folder/f'capture{i}'
                process=subprocess.run([str(ide/'bin/gao_sh'),'-gao',str(definition),'-device','GW5AST-138C',
                                        '-cable','FT2CH','-location',locations[0],'-out',str(prefix)],
                                       env=dict(os.environ,DYLD_LIBRARY_PATH=str(ide/'lib'),DYLD_FRAMEWORK_PATH=str(ide/'lib')),
                                       capture_output=True,text=True,timeout=40)
                log=process.stdout+process.stderr
                if process.returncode or re.search(r'\berror\b',log,re.I):raise ValueError(log)
                saved=a.output.with_suffix(f'.{i}.csv')
                shutil.copy2(str(prefix)+'_core0_window0.csv',saved)
                samples=decode(saved)
                captures.append({'csv':str(saved.resolve()),'first':samples[0],'last':samples[-1]})
        first,last=[c['last'] for c in captures]
        delta={key:(last[key]-first[key])&0xffffffff for key in ('audio_clocks','frames','heartbeat')}
        if delta['heartbeat']==0:raise ValueError('50 MHz counter is stopped')
        seconds=delta['heartbeat']/50000000
        clocks=delta['audio_clocks']/seconds; fs=delta['frames']/seconds
        digital=(abs(clocks/12288000-1)<0.01 and abs(fs/48000-1)<0.01 and last['pdn'] and
                 last['restart_n'] and not last['smute'])
        result.update(capture_valid=True,captures=captures,counter_deltas=delta,interval_seconds=seconds,
                      measured_audio_clock_hz=clocks,measured_frame_hz=fs,digital_passed=digital)
        if 'vccio5' in last:
            rail=last['vccio5']; result['vccio5']=rail
            result['board_power_passed']=(rail['count']>first['vccio5']['count'] and
                rail['timeouts']==0 and bool(rail['flags']&1) and 3.0<=rail['volts']<=3.6)
        result['limitation']='Internal VCCIO5 ADC measures the FPGA IO supply, not the daughterboard supply. Counters verify FPGA clocks and generator state; DAC and amplifier analog output require measurement or listening.'
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as e:result['error']=str(e)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['digital_passed'] and result.get('board_power_passed',True) else 1
if __name__=='__main__':raise SystemExit(main())
