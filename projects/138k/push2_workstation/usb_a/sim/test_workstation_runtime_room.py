#!/usr/bin/env python3
"""Reproducible coefficient math and linear stability; not reverb RTL acceptance."""
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from generate_runtime_room_preset import compile_preset,header,verify_legacy_generator,Q31
from generate_room_preset import preset as legacy_preset


def linear_fdn_impulse(bank,seconds=3):
    """Float64 sample-domain FDN only; excludes early taps, slew and saturation."""
    fs=bank['sample_rate'];lengths=bank['fdn_lengths']
    rings=[[0.0]*length for length in lengths];pointers=[0]*4
    damping=[0.0]*4;alpha=bank['damping']['quantized_alpha'];energy=[]
    peak=0.0
    for frame in range(round(fs*seconds)):
        tail=[rings[lane][pointers[lane]] for lane in range(4)]
        damping=[alpha*damping[lane]+(1-alpha)*tail[lane] for lane in range(4)]
        a,b,c,d=damping
        hadamard=[(a+b+c+d)/2,(a-b+c-d)/2,(a+b-c-d)/2,(a-b-c+d)/2]
        injection=0.125 if frame==0 else 0.0
        feedback=[injection+0.875*value for value in hadamard]
        for lane in range(4):
            rings[lane][pointers[lane]]=feedback[lane]
            pointers[lane]=(pointers[lane]+1)%lengths[lane]
        left=(tail[0]+tail[1]-tail[2]-tail[3])/4
        right=(tail[0]-tail[1]+tail[2]-tail[3])/4
        peak=max(peak,abs(left),abs(right));energy.append(left*left+right*right)
    schroeder=[0.0]*len(energy);total=0.0
    for index in range(len(energy)-1,-1,-1):
        total+=energy[index];schroeder[index]=total
    points=[]
    for index in range(0,len(energy),16):
        if schroeder[index]<=0:continue
        db=10*math.log10(schroeder[index]/total)
        if -25<=db<=-5:points.append((index/fs,db))
    if len(points)<10:raise ValueError('insufficient T20 decay range')
    n=len(points);sx=sum(p[0] for p in points);sy=sum(p[1] for p in points)
    sxx=sum(p[0]*p[0] for p in points);sxy=sum(p[0]*p[1] for p in points)
    slope=(n*sxy-sx*sy)/(n*sxx-sx*sx)
    rt60=-60/slope
    width=round(fs/4)
    return dict(sample_rate=fs,seconds=seconds,peak=peak,total_energy=total,
                initial_quarter_second_energy=sum(energy[:width]),
                final_quarter_second_energy=sum(energy[-width:]),
                rt60_from_T20_seconds=rt60,T20_fit_points=n,
                model_scope='Float64 FDN tail only; not RTL or measured acousticT60; fixed-point limit cycles remain a later test.')


class RuntimeRoomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=compile_preset()
        cls.before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (
            ROOT/'tools/generate_room_preset.py',ROOT/'rtl/audio/spatial_room_preset.svh',
            ROOT/'rtl/audio/spatial_room_preset.json')}

    @classmethod
    def tearDownClass(cls):
        after={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in cls.before}
        if after!=cls.before:raise ValueError('legacy generator/preset changed during verification')

    def test_regeneration_and_legacy48_exact(self):
        self.assertEqual((ROOT/'rtl/audio/runtime_spatial_room_preset.svh').read_text(),header(self.data))
        self.assertEqual((ROOT/'rtl/audio/runtime_spatial_room_preset.json').read_text(),json.dumps(self.data,indent=2)+'\n')
        old=legacy_preset();new=self.data['banks']['48000']
        self.assertEqual(new['fdn_lengths'],old['fdn_delays'])
        for a,b in zip(new['taps'],old['taps']):
            self.assertEqual({key:a[key] for key in b},b)
        text=(ROOT/'rtl/audio/spatial_room_preset.svh').read_text()
        for index,tap in enumerate(new['taps']):
            self.assertIn(f"4'd{index}: early_delay=16'd{tap['delay']};",text)
            self.assertIn(f"4'd{index}: early_gain=16'd{tap['gain_q15']};",text)
        self.assertEqual(new['damping']['old_q31'],1<<30)
        with tempfile.TemporaryDirectory(prefix='runtime-room-drift-') as directory:
            changed=Path(directory)/'generator.py';changed.write_text('# changed source\n')
            with self.assertRaisesRegex(ValueError,'identity changed'):verify_legacy_generator(changed)

    def test_physical_delays_capacity_and_coprimality(self):
        for bank in self.data['banks'].values():
            fs=bank['sample_rate']
            for tap in bank['taps']:
                self.assertLessEqual(abs(tap['quantization_error_seconds']),0.5/fs+1e-15)
                self.assertLess(tap['delay'],self.data['storage']['early_words'])
            for value,capacity,error in zip(bank['fdn_lengths'],self.data['storage']['fdn_words'],bank['fdn_time_error_seconds']):
                self.assertLessEqual(value,capacity)
                self.assertLessEqual(abs(error),1/fs)
            for a,b in itertools.combinations(bank['fdn_lengths'],2):self.assertEqual(math.gcd(a,b),1)

    def test_damping_quantization_time_constant_and_cutoff(self):
        cutoff48=self.data['banks']['48000']['damping']['cutoff_hz']
        for bank in self.data['banks'].values():
            d=bank['damping'];self.assertEqual(d['old_q31']+d['input_q31'],Q31)
            self.assertGreater(d['old_q31'],0);self.assertGreater(d['input_q31'],0)
            self.assertLess(abs(d['coefficient_error']),0.5/Q31+1e-15)
            self.assertLess(abs(d['half_life_seconds']-1/48000),1e-12)
            self.assertLess(abs(d['cutoff_hz']/cutoff48-1),0.01)

    def test_linear_feedback_contraction(self):
        h=((1,1,1,1),(1,-1,1,-1),(1,1,-1,-1),(1,-1,-1,1))
        for a in range(4):
            for b in range(4):
                self.assertEqual(sum(h[k][a]*h[k][b] for k in range(4)),4 if a==b else 0)
        for bank in self.data['banks'].values():
            alpha=bank['damping']['quantized_alpha']
            gains=[]
            for index in range(1025):
                omega=math.pi*index/1024
                gain=(1-alpha)/complex(1-alpha*math.cos(omega),alpha*math.sin(omega))
                gains.append(abs(gain))
            self.assertLessEqual(max(gains),1+1e-12)
            self.assertLess(0.875*max(gains),1)

    def test_float64_tail_impulse_decay_comparison(self):
        result={rate:linear_fdn_impulse(bank) for rate,bank in self.data['banks'].items()}
        for row in result.values():
            self.assertTrue(math.isfinite(row['total_energy']))
            self.assertLess(row['peak'],1)
            self.assertLess(row['final_quarter_second_energy'],row['initial_quarter_second_energy']*1e-5)
            self.assertGreater(row['rt60_from_T20_seconds'],0)
        self.assertLess(abs(result['44100']['rt60_from_T20_seconds']/result['48000']['rt60_from_T20_seconds']-1),0.03)
        print('LINEAR_FDN_IMPULSE',json.dumps(result,sort_keys=True))


if __name__=='__main__':unittest.main()
