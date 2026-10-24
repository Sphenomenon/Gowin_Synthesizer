#!/usr/bin/env python3
"""Decode actual sampled RGB565 outputs; check every pixel and sync pulse."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import tempfile
import zlib

PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / 'reports'
NAMES = ['color-bars', 'rgb-ramps', 'gray-ramp', 'gray-16', 'near-black',
         'near-white', 'white', 'black', 'gray-50', 'checkerboard',
         'walking-bit', 'border-cross']


def expected(pattern, x, y, width, height):
    if pattern == 0:
        return [0xffff, 0xffe0, 0x07ff, 0x07e0, 0xf81f, 0xf800, 0x001f, 0][x*8//width]
    if pattern == 1:
        value = x*255//(width-1)
        row = y*3//height
        return (value >> (2 if row == 1 else 3)) << [11, 5, 0][row]
    if pattern in (2, 3, 4, 5):
        value = {2: x*255//(width-1), 3: x*16//width*17,
                 4: x*8//width*8, 5: 199+x*8//width*8}[pattern]
        return (value//8)*2048+(value//4)*32+value//8
    if pattern in (6, 7, 8):
        return [0xffff, 0, 0x8410][pattern-6]
    if pattern == 9:
        return 0xffff if (x//16+y//16) % 2 else 0
    if pattern == 10:
        return 2**(x*16//width)
    if x in (0, width-1) or y in (0, height-1):
        return 0xffff
    return 0x07e0 if x == width//2 or y == height//2 else 0


def png(path, width, height, pixels):
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    raw = b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))+
                     chunk(b'IDAT', zlib.compress(raw))+chunk(b'IEND', b''))


def main():
    REPORTS.mkdir(exist_ok=True)
    summary = {'passed': False, 'hardware_verified': False, 'target': 'Alientek ATK4384 800x480 RGB',
               'pixel_clock_hz': 31500000, 'scan_total': [976, 528], 'cases': []}
    # A failed or interrupted rerun must not leave an older successful report current.
    (REPORTS/'simulation.json').write_text(json.dumps(summary, indent=2)+'\n')
    with tempfile.TemporaryDirectory(prefix='lcd-sim-') as temp:
        temp = Path(temp)
        for name, fixed, hs, vs, bl, width, height, frames in [
            ('full-resolution-auto', -1, 0, 0, 1, 800, 480, 13),
            ('fixed-inverted-polarity', 6, 1, 1, 0, 48, 24, 4)]:
            exe, capture = temp/(name+'.vvp'), temp/(name+'.rgb565')
            command = ['iverilog', '-g2012', '-Wall', '-s', 'tb_lcd_scan', '-o', str(exe)]
            params = dict(FIXED=fixed, HS=hs, VS=vs, BL=bl, W=width, H=height, FRAMES=frames)
            command += [f'-Ptb_lcd_scan.{key}={value}' for key, value in params.items()]
            command += [str(PROJECT/'rtl/lcd_scan.v'), str(PROJECT/'tests/tb_lcd_scan.v')]
            subprocess.run(command, check=True, capture_output=True, text=True)
            run = subprocess.run(['vvp', str(exe), '+output='+str(capture)], check=True,
                                 capture_output=True, text=True, timeout=100)
            raw = capture.read_bytes()
            assert len(raw) == width*height*frames*2, 'Capture length mismatch'
            values = struct.unpack('>'+str(width*height*frames)+'H', raw)
            for frame in range(frames):
                pattern = frame % 12 if fixed < 0 else fixed
                image = bytearray()
                for y in range(height):
                    for x in range(width):
                        value = values[(frame*height+y)*width+x]
                        wanted = expected(pattern, x, y, width, height)
                        assert value == wanted, (name, frame, x, y, hex(value), hex(wanted))
                        r, g, b = value >> 11, (value >> 5) & 63, value & 31
                        image.extend((r*255//31, g*255//63, b*255//31))
                if fixed < 0 and frame < 12:
                    png(REPORTS/(f'{frame:02d}-'+NAMES[pattern]+'.png'), width, height, image)
            summary['cases'].append({'name': name, 'frames': frames,
                                     'pixels_checked': len(values), 'passed': True,
                                     'simulator': run.stdout.strip()})
            print(run.stdout.strip(), flush=True)
        exe = temp/'top.vvp'
        subprocess.run(['iverilog', '-g2012', '-Wall', '-s', 'tb_lcd_top', '-o', str(exe),
                        str(PROJECT/'rtl/lcd_rgb_top.v'), str(PROJECT/'rtl/lcd_scan.v'),
                        str(PROJECT/'tests/tb_lcd_top.v')], check=True, capture_output=True, text=True)
        run = subprocess.run(['vvp', str(exe)], check=True, capture_output=True, text=True, timeout=100)
        summary['cases'].append({'name': 'top-integration-with-behavioral-pll', 'passed': True,
                                 'simulator': run.stdout.strip()})
        print(run.stdout.strip(), flush=True)
    summary['source_hashes'] = {str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ('rtl', 'tests') for p in sorted((PROJECT/folder).glob('*')) if p.is_file()}
    summary['passed'] = True
    (REPORTS/'simulation.json').write_text(json.dumps(summary, indent=2)+'\n')
    print('PASS every captured pixel; 12 patterns, wraparound, reset, polarity and fixed mode.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stdout or '')
        print(error.stderr or '')
        raise SystemExit(error.returncode)
