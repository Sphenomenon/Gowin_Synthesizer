"""Actual startup, upper-ROM protocol calls and ILM SBC reference samples."""
from pathlib import Path
import base64
import hashlib
import json
import struct

from ae350_split_rv32 import SplitCpu
from ae350_rv32_startup import ROM, ILM, DLM
from tools.ae350_local_memory import symbol_values


def read_bytes(cpu, address, count):
    return bytes(cpu.read(address+i, 1) for i in range(count))


def write_bytes(cpu, address, data):
    for i, value in enumerate(data):
        cpu.write(address+i, value, 1)


def run_model_checks(output, root):
    out, root = Path(output), Path(root)
    s = symbol_values((out/'firmware.nm').read_text())
    image = (out/'firmware.bin').read_bytes().ljust(131072, b'\0')
    cpu = SplitCpu(image, s)
    assert cpu.run() == 'services_main'
    assert cpu.fenced and cpu.executed_ilm and not cpu.csrs[0x7ca] and not cpu.csrs[0x304]
    assert bytes(cpu.ilm[:s['__ilm_end']-ILM]) == image[s['__ilm_load_start']-ROM:s['__data_load_start']-ROM]
    assert read_bytes(cpu, s['__data_start'], s['__data_end']-s['__data_start']) == image[s['__data_load_start']-ROM:s['__data_image_end']-ROM]
    assert read_bytes(cpu, s['__bss_start'], s['__bss_end']-s['__bss_start']) == bytes(s['__bss_end']-s['__bss_start'])
    startup_steps = cpu.steps
    calls = []
    def call(name, *args):
        result = cpu.call(name, *args)
        calls.append(dict(function=name, **result))
        return result['result']
    call('a138_classic_init', s['budget_classic'])
    assert call('a138_classic_begin', s['budget_classic'], 1, 9, 0x23, 276) == 0
    packet = struct.pack('<HHHH', 0x2023, 12, 8, 1) + bytes([2,50,4,0,1,0,0x41,0])
    write_bytes(cpu, s['budget_packet'], packet)
    assert call('a138_classic_acl', s['budget_classic'], 1, 9, s['budget_packet'], len(packet)) == 0
    assert call('a138_classic_tx_peek', s['budget_classic'], s['budget_tx']) == 0
    tx = s['budget_tx']
    assert (cpu.read(tx), cpu.read(tx+4)) == (1, 9)
    token, count = cpu.read(tx+8), cpu.read(tx+12, 2)
    response = read_bytes(cpu, tx+14, count)
    assert count == 32 and response[:8] == struct.pack('<HHHH', 0x2023, 28, 24, 1)
    assert response[8:16] == bytes([3,50,8,0,0x40,0,0x41,0])
    assert call('a138_classic_tx_result', s['budget_classic'], 1, 9, token, 0) == 0
    assert call('a138_classic_tx_result', s['budget_classic'], 1, 9, token, 0) == 2
    assert any(t['region'] == 'ROM_COLD' for t in cpu.region_transitions)
    # Actual cold memset calls enter ILM and return to upper ROM. Check the
    # observed region sequence, not only linked addresses or source intent.
    regions = [t['region'] for t in cpu.region_transitions]
    assert any(regions[i:i+3] == ['ROM_COLD','ILM','ROM_COLD'] for i in range(len(regions)-2))
    vectors = []
    cases = json.loads((root/'sim/fixtures/ae350_sbc_reference.json').read_text())['cases']
    for epoch, case in enumerate(cases, 1):
        blob = base64.b64decode(case['sbc_base64'])
        reference = base64.b64decode(case['reference_pcm_le_base64'])
        header = blob[1]
        rate = [16000,32000,44100,48000][header >> 6]
        mode, subbands = header >> 2 & 3, 8 if header & 1 else 4
        blocks, allocation, bitpool = 4*((header >> 4 & 3)+1), header >> 1 & 1, blob[2]
        channels = 2 if mode else 1
        bits = blocks*channels*bitpool if mode < 2 else blocks*bitpool + (subbands if mode == 3 else 0)
        frame_bytes = 4 + subbands*channels//2 + (bits+7)//8
        samples = blocks*subbands*channels
        fmt = struct.pack('<I6B2x', rate, mode, subbands, blocks, allocation, bitpool, bitpool)
        call('a138_sbc_init', s['budget_decoder'])
        write_bytes(cpu, s['budget_packet'], fmt)
        assert call('a138_sbc_begin', s['budget_decoder'], epoch, s['budget_packet']) == 0
        start, errors, pcm = cpu.steps, [], bytearray()
        # Two frames exercise real filter history, every existing reference
        # mode/subband/bitpool vector, including joint stereo and tiny pools.
        for index in range(2):
            frame = blob[index*frame_bytes:(index+1)*frame_bytes]
            assert len(frame) == frame_bytes and frame[0] == 0x9c
            write_bytes(cpu, s['budget_packet'], frame)
            assert call('a138_sbc_decode', s['budget_decoder'], epoch, s['budget_packet'],
                frame_bytes, s['budget_pcm'], 256, s['budget_pcm']+512) == 0
            result = s['budget_pcm']+512
            assert (cpu.read(result), cpu.read(result+4), cpu.read(result+8,2),
                cpu.read(result+10,2), cpu.read(result+12,1), cpu.read(result+13,1)) == (
                    epoch, rate, blocks*subbands, samples, channels, 1)
            raw = read_bytes(cpu, s['budget_pcm'], samples*2)
            expected = reference[index*samples*2:(index+1)*samples*2]
            actual_samples = struct.unpack('<'+'h'*samples, raw)
            ref_samples = struct.unpack('<'+'h'*samples, expected)
            errors.extend(abs(a-b) for a,b in zip(actual_samples, ref_samples))
            pcm.extend(raw)
        assert max(errors) <= 6
        vectors.append(dict(name=case['name'], rate_hz=rate, mode=mode, subbands=subbands,
            frames=2, scalar_samples=2*samples, maximum_lsb_error=max(errors),
            instructions=cpu.steps-start, pcm_sha256=hashlib.sha256(pcm).hexdigest()))
    receipt = dict(schema=1, passed=True, startup_instructions=startup_steps,
        actual_cold_protocol_response_hex=response.hex(), calls=calls,
        upper_rom_fetches=cpu.upper_rom_fetches, region_transitions=cpu.region_transitions,
        rv32m_instructions=cpu.m_instructions, vectors=vectors,
        scalar_samples=sum(v['scalar_samples'] for v in vectors),
        maximum_lsb_error=max(v['maximum_lsb_error'] for v in vectors),
        observed_stack_bytes=s['__stack_top']-cpu.min_sp, cache_enabled=False,
        actual_cpu_cycles_measured=False, hardware_acceptance=False,
        runtime_transport_closed=False)
    (out/'startup_model_verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
