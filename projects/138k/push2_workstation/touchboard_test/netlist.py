"""Trace the actual netlist through the standard isolated 8-pin resistor arrays."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SIGNALS = {'sda1':'SDA1','scl1':'SCL1','sda2':'SDA2','scl2':'SCL2',
           'sda3':'SDA3','scl3':'SCL3','change_n':'CHANGE12','ws2812_din':'WS2812_DIN'}

def connector_wiring():
    text=(ROOT/'input_netlist.tel').read_text().split('$NETS',1)[1].split('$SCHEDULE',1)[0]
    pattern=re.compile(r"(?m)^('[^']+'|[A-Za-z0-9_+-]+)\s*;\s*")
    matches=list(pattern.finditer(text))
    nets={}
    for i,match in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        nets[match[1].strip("'")]=re.findall(r'\b[A-Za-z]+\d+\.\d+\b',text[match.end():end])
    pin_nets={pin:name for name,pins in nets.items() for pin in pins}
    u4={}
    for port,signal in SIGNALS.items():
        arrays=[p for p in nets[signal] if p.startswith(('RN1.','RN2.'))]
        if len(arrays)!=1: raise ValueError(f'{signal}: expected one series array pin')
        array,number=arrays[0].split('.')
        # Standard 0603x4 isolated array: 1-8, 2-7, 3-6, 4-5.
        opposite=f'{array}.{9-int(number)}'
        outputs=[p for p in nets[pin_nets[opposite]] if p.startswith('U4.')]
        if len(outputs)!=1: raise ValueError(f'{signal}: expected one U4 output')
        u4[port]=int(outputs[0].split('.')[1])
    for pin in (11,12):
        assert pin_nets[f'U4.{pin}']=='GND'
    for pin in (13,14):
        assert pin_nets[f'U4.{pin}']=='3V3'
    assert 'U4.1' not in pin_nets and 'U4.2' not in pin_nets
    return u4,{port:15-pin for port,pin in u4.items()}

if __name__=='__main__':
    import json
    header,wiring=connector_wiring()
    print(json.dumps(dict(u4=header,pmod=wiring,array_pairs=[[1,8],[2,7],[3,6],[4,5]]),indent=2))
