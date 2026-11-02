#!/usr/bin/env python3
"""Selected full83 CNN on parsed PCM WAV; excludes physical TF/SPI and UART.

Without --wav, write an explicitly labelled 48k test audio fixture. This fixture
is validation input only and is never compiled into the demonstration candidate.
"""
from pathlib import Path
import argparse, hashlib, json, math, shutil, struct, subprocess, wave, xml.etree.ElementTree as ET
p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--wav',type=Path)
a=p.parse_args();stage=a.project.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
fixture=out/'input.wav'
if a.wav:shutil.copyfile(a.wav,fixture)
else:
    with wave.open(str(fixture),'wb') as w:
        w.setparams((2,2,48000,0,'NONE','not compressed'))
        for i in range(96000):
            # Piano-like harmonic C4. This is audio input, never a score.
            t=i/48000;env=min(1.,i/96)*math.exp(-1.4*(t%0.5))
            sample=int(11000*env*sum(math.sin(2*math.pi*261.625565*k*t)/k**2 for k in range(1,7)))
            w.writeframesraw(struct.pack('<hh',sample,sample))
raw=fixture.read_bytes();(out/'cnn_fixture.mem').write_text(''.join(f'{b:02x}\n' for b in raw))
files=ET.parse(stage/'Prj1.gprj').find('FileList')
names=[x.get('path') for x in files if x.get('enable')=='1' and x.get('path').startswith('rtl/music/') and x.get('path').endswith('.sv')]
first='rtl/music/basic_pitch_nn_ddr.sv';names.remove(first);names.insert(0,first)
names+=['rtl/timing/gw138k_level_cdc.sv','rtl/memory/workstation_sdp.sv','src/storage/tf_wav_pcm_decoder.v','src/storage/tf_wav_chunk_parser.v','src/usb_a/push2_score_guide.sv']
sources=[stage/n for n in names]+[Path(__file__).with_name('tb_cnn_demo_inference.sv')]
# Keep all readmemh files relative to the selected stage, without copying or
# altering the algorithm sources used by the simulation.
for folder in ('rtl','sim'):
    if (stage/folder).exists():(out/folder).symlink_to(stage/folder,target_is_directory=True)
metadata=dict(scope='WAV_bytes_to_CQT_CNN_Viterbi_actual_score_to_original_Push_guide',physical_TF_tested=False,UART_tested=False,
    fixture_kind='user_WAV' if a.wav else 'generated_audio_validation_only',wav_sha256=hashlib.sha256(raw).hexdigest(),
    parameters=dict(WIN_LEN=43844,FRAMES=3),sources={str(s):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources})
(out/'inputs.json').write_text(json.dumps(metadata,indent=2)+'\n')
commands=[['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal','--top-module','tb_cnn_demo_inference','--Mdir',str(out/'obj'),'-I'+str(stage/'rtl/music'),'-I'+str(stage),f'-GFILE_BYTES={len(raw)}',*map(str,sources)],[str(out/'obj/Vtb_cnn_demo_inference')]]
for i,cmd in enumerate(commands):
    with (out/f'{i}.log').open('w') as log:r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    text=(out/f'{i}.log').read_text()
    if r.returncode:print(text[-8000:]);raise SystemExit(r.returncode)
    if i==1:
        print(text)
        if 'PASS CNN demo inference cleanup:' not in text:raise SystemExit('missing PASS')
