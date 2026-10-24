#!/usr/bin/env python3
"""Decode actual I2S output samples and check channel isolation and frequency."""
import argparse, json, math, pathlib, subprocess, tempfile
root=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
modes=parser.add_mutually_exclusive_group()
modes.add_argument('--isolate',action='store_true',help='Check silence / left / silence / right diagnostic mode')
modes.add_argument('--continuous',action='store_true',help='Check uninterrupted left 1kHz and right 1.5kHz tones')
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='audio-sim-') as tmp:
    binary=pathlib.Path(tmp)/'audio.vvp'
    defines=['-DCHANNEL_ISOLATION_TEST'] if args.isolate else (['-DCONTINUOUS_TONE_TEST'] if args.continuous else [])
    subprocess.run(['iverilog','-g2012']+defines+
                   ['-s','tb_audio','-o',str(binary),
                    str(root/'rtl/ak4493_pin_test.v'),str(root/'tests/tb_audio.v')],check=True)
    p=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,check=True)
    rows=[]
    for line in p.stdout.splitlines():
        if line.startswith('PCM '):
            _,frame,ch,value,mute=line.split()
            n=int(value,16); n=n if n<2**31 else n-2**32
            rows.append((int(frame),int(ch),n,int(mute)))
    assert len(rows)==2000
    channels=[[r[2] for r in rows if r[1]==ch] for ch in (0,1)]
    # Continuous mode starts tones after warm-up; the cycling modes start silent.
    assert all(r[2]==0 for r in rows[:2*(16 if args.continuous else 200)])
    if args.continuous:
        # Check every settled frame, including each former cycling boundary.
        for ch in (0,1):
            expected=[channels[ch][32+i] for i in range(96)]
            assert any(expected)
            assert all(value==expected[i%96] for i,value in enumerate(channels[ch][32:]))
    def rms(xs): return math.sqrt(sum(x*x for x in xs)/len(xs))
    # Omit transitions; each interior covers one full 96-frame common period.
    checks=[]
    for phase,start in [(1,16+192+24),(2,16+384+24),(3,16+576+24)]:
        for ch in (0,1):
            xs=channels[ch][start:start+96]
            active=args.continuous or (((phase==1 and ch==0) or (phase==3 and ch==1)) if args.isolate else (phase==3 or phase==ch+1))
            if not active: assert all(x==0 for x in xs)
            else:
                hz=1000 if ch==0 else 1500
                energy=abs(sum(x*complex(math.cos(2*math.pi*hz*i/48000),-math.sin(2*math.pi*hz*i/48000)) for i,x in enumerate(xs)))
                assert energy>96*rms(xs)*0.70
                assert max(abs(x) for x in xs)<18000000
                assert abs(sum(xs))<96
            checks.append({'phase':phase,'channel':ch,'active':active,'rms':rms(xs)})
    result={'passed':True,'decoded_samples':len(rows),'sample_rate':48000,'format':'I2S 32-bit',
            'peak_dbfs':-42,'isolate_channels':args.isolate,'continuous_tones':args.continuous,'checks':checks}
    name='simulation_continuous.json' if args.continuous else ('simulation_channel_isolation.json' if args.isolate else 'simulation.json')
    (root/'reports'/name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
