#!/usr/bin/env python3
"""Real WAV48/44.1 decoder plus atomic TF transport/cancellation regression."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    pcm = [(0x1234, -0x2345), (-1, 1), (32767, -32768), (0x4567, -0x5678),
           (-32000, 31001), (0x7a01, -0x7b02), (-0x3210, 0x210f), (0x0f01, -0x0e02)]
    fixtures = []
    for rate, name in ((48000, 'wav48'), (44100, 'wav44')):
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(b''.join(struct.pack('<hh', *pair) for pair in pcm))
        payload = stream.getvalue()
        assert len(payload) == 76
        fixture = output / (name + '.hex')
        fixture.write_text(''.join(f'{value:02x}\n' for value in payload))
        fixtures.append(fixture)
    golden = output / 'wav_gold.hex'
    golden.write_text(''.join(f'{left & 0xffff:04x}{right & 0xffff:04x}\n' for left, right in pcm))
    fixtures.append(golden)
    sources = [ROOT / name for name in (
        'rtl/tf_audio/workstation_tf_frame_bridge.sv', 'rtl/music/music_async_fifo.sv',
        'rtl/audio/workstation_final_pcm_router.sv',
        'rtl/tf_audio/storage/tf_wav_chunk_parser.v', 'rtl/tf_audio/storage/tf_wav_pcm_decoder.v')]
    sources.append(Path(__file__).with_name('tb_workstation_tf_frame_bridge.sv'))
    inputs = sources + fixtures + [Path(__file__).resolve()]
    hashes = {str(path): digest(path) for path in inputs}
    result = dict(schema=1, passed=False,
                  source_identity='native-tf-frame-bridge-v1-' + digest(sources[0])[:16],
                  validation_stage='offline-real-decoder-and-transport-simulation',
                  hardware_tested=False, profile_changed=False, bitstream_sha256=None,
                  source_clock_hz=50000000, compute_clock_hz=76800000,
                  input_sha256=hashes, runs={},
                  limits='Real WAV decoder, maintained FIFO and actual final-router mismatch/cancel boundary; no SD/FAT/DDR migration, complete runtime/top/profile selection, physical CDC, synthesis, P&R or board acceptance')
    try:
        for name, seed in (('default', 0), ('wrap', 0xfffffffd)):
            binary = output / (name + '.vvp')
            compile_command = ['iverilog', '-g2012', '-s', 'tb_workstation_tf_frame_bridge',
                               '-Ptb_workstation_tf_frame_bridge.START_GENERATION=' + str(seed),
                               '-o', str(binary), *map(str, sources)]
            run_command = ['vvp', str(binary)]
            record = dict(seed=seed, passed=False, compile_argv=compile_command, run_argv=run_command)
            result['runs'][name] = record
            for stage, command in (('compile', compile_command), ('run', run_command)):
                process = subprocess.run(command, cwd=output, text=True, capture_output=True, timeout=60)
                log = process.stdout + process.stderr
                path = output / (name + '_' + stage + '.log')
                path.write_text(log)
                record[stage + '_log_sha256'] = digest(path)
                if process.returncode:
                    raise RuntimeError(name + '/' + stage + ' failed:\n' + log[-6000:])
            log = (output / (name + '_run.log')).read_text()
            assert 'PASS tf_frame_bridge:' in log, 'Missing verification marker'
            record['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)}
            record['passed'] = True
            print(log, end='')
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        assert result['inputs_unchanged_during_run'], 'Inputs changed during verification'
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        run(args.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='gw138k-tf-frames-') as directory:
            run(Path(directory) / 'verification')


if __name__ == '__main__':
    main()
