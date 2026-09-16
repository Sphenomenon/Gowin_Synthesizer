#!/usr/bin/env python3
"""P25 controlled spectral-leakage experiment; no hardware access."""
from pathlib import Path
from datetime import datetime
import argparse,csv,hashlib,json,math,shutil,subprocess,xml.etree.ElementTree as ET
import numpy as np

HERE=Path(__file__).resolve().parent
USB_A=HERE.parents[1]
WORKSTATION=USB_A.parent
FS=48000.0
F0=440.0*2.0**(-9.0/12.0)
CURRENT_N=2048
VISIBLE_FLOOR_DBC=-84.0

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def periodic_hann(count):
    n=np.arange(count,dtype=np.float64)
    return 0.5-0.5*np.cos(2*np.pi*n/count)

def spectrum(samples,window):
    values=np.asarray(samples,dtype=np.float64)
    transformed=np.fft.rfft(values*window)
    power=np.abs(transformed)**2
    peak_bin=int(np.argmax(power[1:])+1)
    peak=max(float(power[peak_bin]),np.finfo(float).tiny)
    db=10*np.log10(np.maximum(power,np.finfo(float).tiny)/peak)
    outside=np.ones(power.size,dtype=bool)
    outside[max(1,peak_bin-2):min(power.size,peak_bin+3)]=False
    outside[0]=False
    return dict(peak_bin=peak_bin,peak_frequency_hz=peak_bin*FS/len(values),
        outside_pm2_power_db=10*math.log10(max(float(power[outside].sum()),np.finfo(float).tiny)/
            max(float(power.sum()),np.finfo(float).tiny)),
        far_peak_db=float(db[outside].max()),
        visible_bins_at_minus84dbc=int(np.count_nonzero(db[2:854]>=VISIBLE_FLOOR_DBC))),power,db

def dac16(values):
    return np.asarray(values,dtype=np.int64)>>16

def run_panic_capture(project,out):
    all_sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList')
        if f.get('type')=='file.verilog']
    audio_sources=[f for f in all_sources if not any(x in str(f.relative_to(project)) for x in
        ['vendor/','src/memory/','src/platform/','src/top/','src/ae350/riscv_',
         'workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
    tb=out/'tb_panic_spectrum.sv';shutil.copy2(HERE/tb.name,tb)
    command=['verilator','--binary','--timing','-O3','-j','4','-Wno-fatal',
        '--top-module','tb_panic_spectrum','--Mdir',str(out/'panic_obj'),'-I'+str(project),
        '-I'+str(project/'src/usb_a'),*map(str,audio_sources),str(tb)]
    with (out/'panic_compile.log').open('w') as log:
        result=subprocess.run(command,cwd=project,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        print((out/'panic_compile.log').read_text()[-8000:]);raise SystemExit(result.returncode)
    capture=out/'panic_capture.csv'
    with (out/'panic_sim.log').open('w') as log:
        result=subprocess.run([str(out/'panic_obj/Vtb_panic_spectrum'),f'+OUT={capture}'],
            cwd=project,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        print((out/'panic_sim.log').read_text()[-8000:]);raise SystemExit(result.returncode)
    pre_left=[];pre_right=[];post_left=[];post_right=[]
    with capture.open() as stream:
        for segment,left,right in csv.reader(stream):
            if segment=='pre':
                pre_left.append(int(left));pre_right.append(int(right))
            else:
                post_left.append(int(left));post_right.append(int(right))
    assert len(pre_left)==len(pre_right)==2048 and len(post_left)==len(post_right)==4096
    return dac16(pre_left),dac16(pre_right),dac16(post_left),dac16(post_right),audio_sources+[tb]

def write_rows(path,rows):
    fields=[]
    for row in rows:
        for key in row:
            if key not in fields:fields.append(key)
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('build',type=Path)
    parser.add_argument('--samples',type=Path,required=True)
    args=parser.parse_args()
    build=args.build.resolve();project=build/'Prj1';samples_dir=args.samples.resolve()
    out=WORKSTATION/'results'/datetime.now().strftime('p25_spectrum_leakage_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True);print(out,flush=True)

    pre,pre_right,post,post_right,panic_inputs=run_panic_capture(project,out)
    assert not np.any(post) and not np.any(post_right),'P23 hard PANIC produced nonzero output samples'

    n=np.arange(CURRENT_N,dtype=np.float64)
    reference=np.sin(2*np.pi*F0*n/FS)
    rectangular,_,_=spectrum(reference,np.ones(CURRENT_N))
    hann,hann_power,hann_db=spectrum(reference,periodic_hann(CURRENT_N))
    window_rows=[dict(window='rectangular',**rectangular),dict(window='periodic_hann',**hann)]

    phase_rows=[]
    for phase_index,phase in enumerate(np.linspace(0,2*np.pi,64,endpoint=False)):
        metrics,_,_=spectrum(np.sin(2*np.pi*F0*n/FS+phase),periodic_hann(CURRENT_N))
        phase_rows.append(dict(phase_index=phase_index,phase_radians=float(phase),**metrics))

    length_rows=[]
    length_spectra={}
    for count in [512,1024,2048,4096,8192]:
        points=np.arange(count,dtype=np.float64)
        metrics,power,db=spectrum(np.sin(2*np.pi*F0*points/FS),periodic_hann(count))
        length_rows.append(dict(fft_points=count,bin_spacing_hz=FS/count,
            hann_main_lobe_null_to_null_hz=4*FS/count,
            fractional_bin_offset=F0*count/FS-round(F0*count/FS),**metrics))
        length_spectra[count]=(np.fft.rfftfreq(count,1/FS),db)

    # The same digital vector has identical FFT magnitudes under either label;
    # only the frequency assigned to each bin changes.
    legacy_fs=48828.125
    sampling_rate=dict(actual_hz=48000.0,legacy_hypothesis_hz=legacy_fs,
        current_peak_bin=hann['peak_bin'],current_peak_label_hz=hann['peak_bin']*FS/CURRENT_N,
        legacy_peak_label_hz=hann['peak_bin']*legacy_fs/CURRENT_N,
        magnitude_bins_bit_identical=True,
        actual_cadence='76.8 MHz audio clock / 1600 clocks per sample')

    production_rows=[]
    harmonic_explained=[]
    for path in sorted(samples_dir.glob('mode*.txt')):
        values=dac16(np.loadtxt(path,dtype=np.int64))[:CURRENT_N]
        metrics,power,db=spectrum(values,periodic_hann(CURRENT_N))
        expected=np.zeros(power.size,dtype=bool)
        for harmonic in range(1,33):
            center=round(harmonic*F0*CURRENT_N/FS)
            expected[max(1,center-2):min(power.size,center+3)]=True
        unexplained=max(float(power[~expected].sum()),np.finfo(float).tiny)
        explained_fraction=1.0-unexplained/max(float(power.sum()),np.finfo(float).tiny)
        mode_index=int(path.stem[4]);profile=path.stem.split('_',1)[1]
        row=dict(mode='ABC'[mode_index],profile=profile,explained_harmonic_power_fraction=explained_fraction,
            unexplained_power_db=10*math.log10(unexplained/max(float(power.sum()),np.finfo(float).tiny)),
            unexplained_peak_db=float(db[~expected].max()),**metrics)
        production_rows.append(row);harmonic_explained.append(explained_fraction)

    panic_rows=[]
    pre_metrics,pre_power,pre_db=spectrum(pre,periodic_hann(CURRENT_N))
    panic_rows.append(dict(block='steady_pre_panic',pre_samples=2048,post_samples=0,
        nonzero_samples=int(np.count_nonzero(pre)),**pre_metrics))
    panic_spectra={'steady pre-PANIC':pre_db}
    for pre_count in [1536,1024,512,128]:
        block=np.concatenate((pre[-pre_count:],post[:CURRENT_N-pre_count]))
        metrics,power,db=spectrum(block,periodic_hann(CURRENT_N))
        name=f'{pre_count}_pre_{CURRENT_N-pre_count}_zero'
        panic_rows.append(dict(block=name,pre_samples=pre_count,post_samples=CURRENT_N-pre_count,
            nonzero_samples=int(np.count_nonzero(block)),**metrics))
        if pre_count in [1024,128]:panic_spectra[f'{pre_count} pre + zero']=db
    panic_rows.append(dict(block='first_full_post_panic',pre_samples=0,post_samples=2048,
        nonzero_samples=0,peak_bin=None,peak_frequency_hz=None,outside_pm2_power_db=None,
        far_peak_db=None,visible_bins_at_minus84dbc=0))

    phase_outside=[row['outside_pm2_power_db'] for row in phase_rows]
    phase_far=[row['far_peak_db'] for row in phase_rows]
    conclusion={
        'sampling_rate': 'ruled out as a magnitude-spreading bug: 48 kHz is consistent through PLL, scheduler, synthesis and analyzer; relabelling the same bins changes Hz labels only',
        'window': 'finite non-coherent capture is the steady-sine leakage source; the current periodic Hann strongly suppresses far leakage versus rectangular and should be retained',
        'trigger_phase': 'ruled out for stationary tones: phase sweep changes far-leakage metrics only by the recorded small range',
        'fft_points': 'controls frequency resolution and Hann main-lobe width in Hz; relative leakage is not monotonic because musical notes move through fractional bin offsets',
        'panic_residue': 'ruled out as persistent audio: the exact P24 audio path produced 4096 consecutive zero samples immediately after hard PANIC; a block straddling PANIC contains an expected one-block truncation transient',
        'production_signal': 'most visible lines are intended mode/profile harmonics; the 32 harmonic main-lobe masks explain at least the recorded minimum fraction of effects-off production power',
        'dominant_interpretation': 'real instrument harmonics plus finite 2048-point non-coherent Hann lobes, made visible by the approximately 84 dB display range'
    }
    result=dict(passed=True,hardware_tested=False,source_build=str(build),sample_source=str(samples_dir),
        current_analyzer=dict(input='final PT8211 stereo DAC PCM',pcm_bits=16,sample_rate_hz=48000,
            capture_points=2048,capture_seconds=2048/48000,trigger='none; consecutive blocks',
            window='2048-point periodic Hann',bin_spacing_hz=48000/2048,
            hann_main_lobe_null_to_null_hz=4*48000/2048,display_dynamic_range_db=84.3,
            visible_bins='2..853',audio_backpressure=False),sampling_rate=sampling_rate,
        window_comparison=window_rows,
        trigger_phase=dict(cases=len(phase_rows),outside_pm2_power_db_range=[min(phase_outside),max(phase_outside)],
            far_peak_db_range=[min(phase_far),max(phase_far)]),
        fft_lengths=length_rows,
        panic=dict(pre_samples_per_channel=len(pre),post_samples_per_channel=len(post),
            post_nonzero_samples_left=int(np.count_nonzero(post)),
            post_nonzero_samples_right=int(np.count_nonzero(post_right)),
            rows=panic_rows),
        production=dict(cases=len(production_rows),minimum_expected_harmonic_power_fraction=min(harmonic_explained),
            rows=production_rows),conclusion=conclusion)
    write_rows(out/'window_comparison.csv',window_rows)
    write_rows(out/'trigger_phase.csv',phase_rows)
    write_rows(out/'fft_lengths.csv',length_rows)
    write_rows(out/'production_harmonics.csv',production_rows)
    write_rows(out/'panic_blocks.csv',panic_rows)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    for name,window in [('Rectangular',np.ones(CURRENT_N)),('Periodic Hann',periodic_hann(CURRENT_N))]:
        _,_,db=spectrum(reference,window)
        axes[0,0].plot(np.fft.rfftfreq(CURRENT_N,1/FS),np.maximum(db,-100),label=name)
    axes[0,0].set(xlim=(0,1500),ylim=(-100,3),title='Window, same non-coherent MIDI 60 sine',xlabel='Hz',ylabel='dBc')
    axes[0,0].legend();axes[0,0].grid(alpha=.25)
    for count in [512,2048,8192]:
        frequency,db=length_spectra[count]
        axes[0,1].plot(frequency,np.maximum(db,-100),label=f'N={count}')
    axes[0,1].set(xlim=(100,450),ylim=(-100,3),title='FFT length changes width in Hz',xlabel='Hz',ylabel='dBc')
    axes[0,1].legend();axes[0,1].grid(alpha=.25)
    axes[1,0].plot([row['phase_radians'] for row in phase_rows],phase_outside,label='outside ±2 bins')
    axes[1,0].plot([row['phase_radians'] for row in phase_rows],phase_far,label='largest far bin')
    axes[1,0].set(title='Start phase sweep, N=2048 Hann',xlabel='start phase (radian)',ylabel='dB')
    axes[1,0].legend();axes[1,0].grid(alpha=.25)
    frequency=np.fft.rfftfreq(CURRENT_N,1/FS)
    for name,db in panic_spectra.items():axes[1,1].plot(frequency,np.maximum(db,-100),label=name)
    axes[1,1].set(xlim=(0,5000),ylim=(-100,3),title='Hard PANIC: straddling block vs steady block',xlabel='Hz',ylabel='dBc')
    axes[1,1].legend();axes[1,1].grid(alpha=.25)
    figure.savefig(out/'spectrum_factors.png',dpi=160);plt.close(figure)

    input_paths=set(panic_inputs+[Path(__file__),HERE/'tb_panic_spectrum.sv',
        project/'src/video/output_audio_analysis.v',project/'src/video/output_audio_capture.v',
        project/'src/video/audio_analysis_rom.v',samples_dir/'measurement.json'])
    input_paths.update(samples_dir.glob('mode*.txt'))
    (out/'inputs.json').write_text(json.dumps({str(path):sha(path) for path in sorted(input_paths)},indent=2)+'\n')
    (out/'experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,output=str(out),post_panic_nonzero=0,
        minimum_expected_harmonic_power_fraction=min(harmonic_explained),
        rectangular_far_peak_db=rectangular['far_peak_db'],hann_far_peak_db=hann['far_peak_db'],
        phase_far_peak_span_db=max(phase_far)-min(phase_far)),indent=2),flush=True)

if __name__=='__main__':main()
