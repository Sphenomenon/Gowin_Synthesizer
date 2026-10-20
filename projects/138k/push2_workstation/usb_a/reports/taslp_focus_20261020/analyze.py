from pathlib import Path
import re,json,math,collections
import numpy as np

ROOT=Path(__file__).resolve().parents[6]
OUT=Path(__file__).resolve().parent
BUILD=ROOT/'projects/138k/push2_workstation/usb_a/results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1'
pat=re.compile(r'^\s*(\w+)\s+\\(u_managed/u_audio/u_workstation/(\S+))\s+\(')
cs=collections.defaultdict(collections.Counter)
for line in (BUILD/'impl/pnr/Prj1.vo').open():
    m=pat.match(line)
    if not m:continue
    typ,name,rel=m.groups()
    if rel.startswith('engine/'): group='engine'
    elif rel.startswith('effects/'):
        rest=rel[len('effects/'):]
        group=rest.split('/')[0] if '/' in rest else 'effects_router'
    else:continue
    cs[group][typ]+=1
resources={}
for name,c in cs.items():
    resources[name]={
        'LUT_ALU':sum(v for k,v in c.items() if k.startswith('LUT') or k=='ALU'),
        'ordinary_FF':sum(v for k,v in c.items() if k.startswith('DFF')),
        'native_DSP':2*c['MULT27X36']+c['MULTALU27X18']+.5*c['MULT12X12'],
        'BSRAM':sum(v for k,v in c.items() if k.startswith(('SDP','DP','pROM'))),
        'primitives':dict(c)}

FS=48000.;CLK=76800000.;BLOCK=18432
# Sizing assumptions only: main 2*32-bit states + four 27-bit coefficients;
# secondary/longitudinal 2*32-bit states + three 27-bit coefficients;
# shared stereo body: 2*32-bit states + six 27-bit coefficients.
tiers=[]
for name,v,n,s,k,l in [('prototype',8,64,8,64,0),('recommended',32,64,16,64,0),('extended',32,128,24,128,4)]:
    primary=v*n; secondary=88*s; body=k; longitudinal=v*l
    data_bits=primary*172+(secondary+longitudinal)*145+body*226
    total=primary+secondary+body+longitudinal
    tiers.append(dict(name=name,voices=v,primary=primary,secondary=secondary,body=body,longitudinal=longitudinal,total_sections=total,
       raw_bytes=math.ceil(data_bits/8),ideal_capacity_BSRAM=math.ceil(data_bits/BLOCK),
       section_updates_per_sec=int(total*FS),ideal_cycles_4_issue_lanes=math.ceil(total/4),
       all_hammers_active_mul_per_sample=primary*4+secondary*3+body*6+longitudinal*3))

# Pole quantization diagnostic: coefficient rounding only, no state quantization.
# It is not an end-to-end fixed-point simulation or a listening score.
notes=np.arange(21,109)
freqs=440.*2.**((notes-69)/12)
t60s=np.array([.25,1.,5.,10.,20.])
rows=[]
for bits in [18,24,27,32]:
    frac=bits-2
    all_cents=[];all_t=[];stable_count=0;max_r=0.;real_count=0
    for f in freqs:
        for t in t60s:
            r=10.**(-3./(FS*t));a1=-2*r*math.cos(2*math.pi*f/FS);a2=r*r
            aq1=np.rint(a1*2**frac)/2**frac;aq2=np.rint(a2*2**frac)/2**frac
            roots=np.roots([1,aq1,aq2]);qr=float(np.max(np.abs(roots)))
            stable=bool(qr<1)
            stable_count+=stable;max_r=max(max_r,qr)
            if np.all(np.abs(roots.imag)<1e-10):real_count+=1;continue
            qf=abs(np.angle(roots[0]))*FS/(2*np.pi)
            cents=1200*np.log2(qf/f)
            all_cents.append(abs(cents))
            if stable:
                qt=-3/(FS*np.log10(qr));all_t.append(abs(qt/t-1)*100)
    rows.append({'coefficient_bits':bits,'fractional_bits':frac,'cases':len(freqs)*len(t60s),'stable_cases':stable_count,'real_pole_cases':real_count,'max_abs_pitch_error_cents':float(max(all_cents)),'max_abs_T60_error_percent':float(max(all_t))})

# A0 examples, using T60=10 seconds.
a0=[]
for bits in [18,24,27,32]:
    frac=bits-2;f=27.5;t=10.;r=10**(-3/(FS*t))
    a1=round(-2*r*math.cos(2*math.pi*f/FS)*2**frac)/2**frac
    a2=round(r*r*2**frac)/2**frac
    roots=np.roots([1,a1,a2]);qf=abs(np.angle(roots[0]))*FS/(2*np.pi);qr=max(abs(roots));qt=-3/(FS*np.log10(qr))
    a0.append({'bits':bits,'frequency_hz':float(qf),'pitch_error_cents':float(1200*np.log2(qf/f)),'T60_seconds':float(qt)})

room={
 'current_chorus_raw_bytes':2*1024*4,
 'current_reverb_raw_bytes':2*2048*4,
 'ER_4096_mono_24bit_raw_bytes':4096*3,
 'FDN4_1024_24bit_raw_bytes':4*1024*3,
 'FDN8_1024_24bit_raw_bytes':8*1024*3,
 'FDN4_plus_ER_ideal_BSRAM':math.ceil((4096+4*1024)*24/BLOCK),
 'FDN8_plus_ER_ideal_BSRAM':math.ceil((4096+8*1024)*24/BLOCK),
 'HRTF_1source_2ears_128taps_MAC_per_sec':int(2*128*FS),
 'HRTF_16paths_2ears_128taps_MAC_per_sec':int(16*2*128*FS),
 'HRTF_32voices_2ears_128taps_MAC_per_sec':int(32*2*128*FS),
 'FDTD_10x5x3m_5cm_grid_nodes':round(10*5*3/.05**3),
 'FDTD_5cm_48k_node_updates_sec':round(10*5*3/.05**3*FS),
 'FDTD_two_32bit_pressure_fields_bytes':round(10*5*3/.05**3*8),
 'full_note_main_64mode_four27bit_coeff_ROM_bytes':math.ceil(88*64*4*27/8),
 'two_additional_AB_gain_mode_bits':2*5*32*16,
}
result=dict(assumptions={'fs_hz':FS,'clock_hz':CLK,'BSRAM_block_bits':BLOCK,'capacity_only_not_placed':True,'pole_study_omits_state_rounding_and_feedback_nonlinearity':True},resources=resources,tiers=tiers,coefficient_sweep=rows,A0_T60_10s_examples=a0,room=room)
(OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
