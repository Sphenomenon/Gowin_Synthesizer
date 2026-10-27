"""Capture explicitly identified DDR or workstation observers; never program them."""

from collections import Counter
from pathlib import Path
import argparse
import csv
import datetime
import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
BINARY = Path('/home/sphenicidition/.local/opt/gowin-1.9.12.03/IDE/bin/gao_sh')
RECIPE = ROOT / 'out/hdmi_usb3_diagnostic_20261025_c11025d5/jtag_capture_20261025_07/capture.gdb'
TEMPORARY = Path('/home/sphenicidition/.cache/fpga-validation/20261025')
IDENTITY_COMMAND = ['gowin-programmer-cli', '--device', 'GW5AST-138C', '--cable-index', '5',
                    '--location', '54', '--frequency', '0.9MHz', '--operation_index', '0']
OFFICIAL_CONTROLS = ('pll_lock', 'init_calib_complete', 'rstni', 'app_rd_data_valid',
                     'app_wdf_rdy', 'full', 'pll_stop_3', 'key1_F4_d')
OFFICIAL_SIGNALS = list(OFFICIAL_CONTROLS) + [f'error_int1[{bit}]' for bit in reversed(range(16))] + [
    f'led_cnt[{bit}]' for bit in reversed(range(8))]
WORKSTATION_SIGNALS = ['reset_n'] + [f'memory_flags[{bit}]' for bit in reversed(range(8))] + [
    f'video_diagnostics[{bit}]' for bit in reversed(range(8, 14))] + ['video_diagnostics[64]']
DISPLAY_COUNTER_SIGNALS = ['reset_n', 'memory_flags[0]', 'memory_flags[4]', 'video_diagnostics[9]',
                           'video_diagnostics[33]', 'video_diagnostics[32]',
                           'video_diagnostics[65]', 'video_diagnostics[64]'] + [
                               f'video_diagnostics[{bit}]' for bit in reversed(range(96, 104))]
DDR_PHY = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/'
DDR_TRAINING_SIGNALS = ['reset_n', 'memory_flags[6]', 'memory_flags[0]', 'memory_flags[3]'] + [
    'u_memory/' + name for name in ('controller_rst_n', 'controller_reset', 'pll_stop_3')] + [
    DDR_PHY + 'dll_lock', DDR_PHY + 'ddr_sync/ready'] + [
    DDR_PHY + 'u_ddr_init/init_state.' + name
    for name in ('WRITE_LEVELING', 'READ_CALIBRATION', 'EYE_SCAN')] + [
    DDR_PHY + f'u_ddr_init/read_calibration_logic_gen[{lane}].read_cal_done'
    for lane in range(4)]
READ_CAL_STATES = ('READ_CAL_WRITE_CMD', 'READ_CAL_READ_CMD', 'READ_CAL_ACTIVE_CMD',
                   'READ_CAL_PRECHARGE', 'READ_CAL_WAIT', 'READ_CAL_HOLD',
                   'READ_CAL_READ_CMD_WAIT', 'READ_CAL_WRITE_CMD_WAIT',
                   'READ_CAL_ACTIVE_CMD_WAIT', 'READ_CAL_RSEL_ADJ_WAIT',
                   'READ_CAL_PRECHARGE_WAIT', 'READ_CAL_IDLE', 'READ_CAL_RBURST_CHECK',
                   'READ_CAL_RBURST_CHECK_WAIT', 'READ_CAL_RBURST_CHECK_WAIT1',
                   'READ_CAL_RSEL_ADJ', 'READ_CAL_DONE')
DDR_LANE3_SIGNALS = DDR_TRAINING_SIGNALS[:12] + [
    DDR_PHY + 'u_ddr_init/read_cal_state.' + state for state in READ_CAL_STATES
] + DDR_TRAINING_SIGNALS[12:] + [
    DDR_PHY + f'u_ddr_init/read_calibration_logic_gen[{lane}].rburst_{edge}'
    for lane in range(4) for edge in ('pos', 'neg')] + [
    DDR_PHY + f'u_ddr_init/read_calibration_logic_gen[3].{name}[{bit}]'
    for name in ('read_i', 'ides_calib_cnt', 'cal_cnt') for bit in reversed(range(4))] + [
    DDR_PHY + name for name in (
        'u_ddr_init/readback_check_3_8', 'phy_rdbk_data_valid[3]',
        'read_calibration_logic_gen[3].read_adj', 'u_ddr_init/rburst_cnt_check[3]',
        'u_init_rmove_mod/sys_reset_ch[3]',
        'u_ddr_init/read_calibration_logic_gen[3].rburst_t_r',
        'u_ddr_init/read_calibration_logic_gen[3].rburst_neg_r',
        'rvalid_Z_2[3]', 'u_ddr_init/rburst_reg[3]', 'init_rmove_done_r', 'RBURST_2[3]')]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def timestamp():
    return datetime.datetime.now().astimezone().isoformat(timespec='microseconds')


def identity(destination, expected):
    result = subprocess.run(IDENTITY_COMMAND, capture_output=True, text=True, timeout=30)
    text = result.stdout + result.stderr
    destination.write_text(text)
    match = re.search(r'User Code is:\s*(0x[0-9a-f]+)', text, re.I)
    if result.returncode or 'Finished.' not in text or not match or int(match[1], 16) != int(expected, 16):
        raise ValueError('unexpected board identity: ' + text)
    if not re.search(r'ID Code is:\s*0x0001081B', text, re.I):
        raise ValueError('unexpected FPGA device')


def snapshot(sample, schema=None):
    if schema in ('workstation-ddr-training-16-v1', 'workstation-ddr-lane3-64-v1'):
        signals = DDR_LANE3_SIGNALS if schema == 'workstation-ddr-lane3-64-v1' else DDR_TRAINING_SIGNALS
        return dict(reset_released=bool(sample['reset_n']),
                    ddr_pll_locked=bool(sample['memory_flags[6]']),
                    ddr_calibrated=bool(sample['memory_flags[0]']),
                    front_valid=bool(sample['memory_flags[3]']),
                    raw_controls={name: sample[name] for name in signals[4:]},
                    coherent_cross_domain_snapshot=False)
    if schema == 'workstation-display-counters-16-v1':
        return dict(reset_released=bool(sample['reset_n']),
                    ddr_calibrated=bool(sample['memory_flags[0]']),
                    fetch_arbiter_or_shared_load_fault=bool(sample['memory_flags[4]']),
                    video_locked=bool(sample['video_diagnostics[9]']),
                    vblank_low2=sum(sample[f'video_diagnostics[{bit + 32}]'] << bit for bit in range(2)),
                    rendered_frames_low2=sum(sample[f'video_diagnostics[{bit + 64}]'] << bit for bit in range(2)),
                    underruns_low8=sum(sample[f'video_diagnostics[{bit + 96}]'] << bit for bit in range(8)),
                    truncated_counters_wrap=True, coherent_cross_domain_snapshot=False)
    if schema == 'workstation-memory-video-16-v1':
        memory = sum(sample[f'memory_flags[{bit}]'] << bit for bit in range(8))
        video = sum(sample[f'video_diagnostics[{bit + 8}]'] << bit for bit in range(6))
        memory_names = ('ddr_calibrated', 'bist_done', 'bist_failed', 'front_valid',
                        'fetch_arbiter_or_shared_load_fault', 'underrun_seen',
                        'ddr_pll_locked', 'video_pll_locked')
        video_names = ('hpd', 'video_locked', 'pixel_reset_released', 'scanout_reset_released',
                       'serializer_reset_asserted', 'measurement_valid')
        return dict(reset_released=bool(sample['reset_n']), memory_flags_hex=f'0x{memory:02X}',
                    memory_flags={name: bool(memory & (1 << bit)) for bit, name in enumerate(memory_names)},
                    video_flags_hex=f'0x{video:02X}',
                    video_flags={name: bool(video & (1 << bit)) for bit, name in enumerate(video_names)},
                    rendered_frame_bit0=sample['video_diagnostics[64]'])
    if schema == 'official-ddr-reference-32-v1':
        return dict(raw_controls={name: bool(sample[name]) for name in OFFICIAL_CONTROLS},
                    raw_error_word=sum(sample[f'error_int1[{bit}]'] << bit for bit in range(16)),
                    raw_read_count_low8=sum(sample[f'led_cnt[{bit}]'] << bit for bit in range(8)),
                    coherent_cross_domain_snapshot=False)
    flags = sum(sample[f'status_sync[{bit}]'] << bit for bit in range(8))
    names = ('reset_released', 'pll_locked', 'calibrated', 'ui_reset_released',
             'bist_done', 'bist_failed', 'app_ready', 'app_write_ready')
    controls = ('controller_rst_n', 'controller_reset', 'qualified_lock', 'pll_stop_3')
    result = dict(status_hex=f'0x{flags:02X}',
                  flags={name: bool(flags & (1 << bit)) for bit, name in enumerate(names)},
                  raw_controls={name: sample['u_memory/' + name] for name in controls
                                if 'u_memory/' + name in sample})
    if all(f'ui_gray_sync[{bit}]' in sample for bit in range(8)):
        gray = sum(sample[f'ui_gray_sync[{bit}]'] << bit for bit in range(8))
        result['ui_gray_hex'] = f'0x{gray:02X}'
    result['training_signals'] = {name: value for name, value in sample.items()
                                  if name.startswith('u_memory/u_ddr3/')}
    return result


def capture(output, sequence):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    width = len(manifest['signals'])
    schema = manifest.get('signal_schema')
    if schema == 'workstation-display-counters-16-v1':
        if manifest.get('full_workstation') is not True or manifest['signals'] != DISPLAY_COUNTER_SIGNALS:
            raise ValueError('unexpected full-workstation counter observer layout')
    elif schema == 'workstation-memory-video-16-v1':
        if manifest.get('full_workstation') is not True or manifest['signals'] != WORKSTATION_SIGNALS:
            raise ValueError('unexpected full-workstation observer layout')
    elif schema == 'workstation-ddr-training-16-v1':
        if manifest.get('full_workstation') is not True or manifest['signals'] != DDR_TRAINING_SIGNALS:
            raise ValueError('unexpected full-workstation training observer layout')
    elif schema == 'workstation-ddr-lane3-64-v1':
        if manifest.get('full_workstation') is not True or manifest['signals'] != DDR_LANE3_SIGNALS:
            raise ValueError('unexpected full-workstation lane3 observer layout')
    elif manifest.get('full_workstation') is not False or width not in (20, 32):
        raise ValueError('expected an explicit 20-bit or 32-bit isolated DDR observer')
    elif schema == 'official-ddr-reference-32-v1':
        if manifest['signals'] != OFFICIAL_SIGNALS:
            raise ValueError('unexpected official DDR reference layout')
    else:
        if manifest['signals'][:8] != [f'status_sync[{bit}]' for bit in reversed(range(8))]:
            raise ValueError('unexpected DDR status layout')
        if width == 32 and schema != 'ddr-training-32-v1':
            raise ValueError('unexpected DDR training schema')
    gao_file = manifest.get('gao_file', 'diagnostic.gao')
    if gao_file not in ('diagnostic.gao', 'workstation.gao'):
        raise ValueError('unexpected GAO configuration filename')
    configuration = output / gao_file
    if digest(configuration) != manifest['input_sha256'][gao_file]:
        raise ValueError('GAO configuration changed')
    if digest(BINARY) != '4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b':
        raise ValueError('GAO host binary changed')
    if digest(RECIPE) != '901f1c40d4679c54e1246226c33c2d33850c2a55bbebed496ed9c69f4b87de66':
        raise ValueError('WINUSB runtime recipe changed')
    helper = ROOT / 'out/hdmi_usb3_diagnostic_20261025_c11025d5/jtag_trace_20261025_03/trace_packets.py'
    if digest(helper) != '646aebe9283abbc72a8b2cbc15668897335f9b6512f284ae4666ffcdb644c93e':
        raise ValueError('WINUSB packet helper changed')
    destination = output / f'jtag_capture_20261026_{sequence:02d}'
    destination.mkdir()
    socket = TEMPORARY / 'gao1'
    if socket.exists():
        details = socket.lstat()
        listeners = subprocess.run(['ss', '-xlpn'], capture_output=True, text=True, check=True).stdout
        if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.getuid() or str(socket) in listeners:
            raise ValueError('GAO socket is foreign or still active')
        socket.unlink()
    identity(destination / 'identity_before.log', manifest['user_code'])
    command = ['gdb', '-nx', '-q', '-batch', '-x', str(RECIPE), '--args', str(BINARY),
               '-local', '-gao', str(configuration), '-out', str(destination / 'capture'),
               '-cable', 'FT2CH', '-location', '54']
    environment = os.environ.copy()
    environment.update(QT_QPA_PLATFORM='offscreen', QT_OPENGL='software',
                       LD_LIBRARY_PATH=str(BINARY.parents[1] / 'lib'),
                       LD_PRELOAD='/usr/lib64/libstdc++.so.6:/usr/lib64/libz.so.1:/usr/lib64/libfreetype.so.6',
                       TMPDIR=str(TEMPORARY))
    attempt = dict(started_at=timestamp(), command=command, observer_identity=manifest['user_code'],
                   capture_script_sha256=digest(__file__), gao_sh_sha256=digest(BINARY),
                   recipe_sha256=digest(RECIPE), gao_configuration_sha256=digest(configuration),
                   sram_programmed=False, flash_accessed=False)
    with (destination / 'gdb.log').open('xb') as log:
        process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            returncode = process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            text = (destination / 'gdb.log').read_text(errors='replace')
            match = re.search(r'INFERIOR_PID (\d+)', text)
            if match:
                inferior = int(match[1])
                try:
                    if b'gao_sh' in Path(f'/proc/{inferior}/cmdline').read_bytes():
                        if os.getpgid(inferior) == inferior:
                            os.killpg(inferior, signal.SIGTERM)
                        else:
                            os.kill(inferior, signal.SIGTERM)
                except (FileNotFoundError, ProcessLookupError):
                    pass
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            attempt.update(finished_at=timestamp(), timed_out=True, returncode=process.returncode)
            (destination / 'attempt.json').write_text(json.dumps(attempt, indent=2) + '\n')
            raise
    attempt.update(finished_at=timestamp(), timed_out=False, returncode=returncode)
    (destination / 'attempt.json').write_text(json.dumps(attempt, indent=2) + '\n')
    packets = [json.loads(line[7:]) for line in (destination / 'gdb.log').read_text().splitlines()
               if line.startswith('PACKET ')]
    (destination / 'packets.json').write_text(json.dumps(packets, indent=2) + '\n')

    def value(packet, key):
        return packet.get('fields', {}).get(key, {}).get('value')

    opens = [packet for packet in packets if packet['direction'] == 'receive' and value(packet, 'CMD') == 'OPEN']
    reads = [packet for packet in packets if packet['direction'] == 'receive' and value(packet, 'OPRATE') == 'READ_RAM']
    assert returncode == 0 and len(opens) == 1 and value(opens[0], 'RES') == 0
    assert value(opens[0], 'cable_index') == 2 and value(opens[0], 'cable_location') == 54
    assert reads and all(value(packet, 'RES') == 0 and packet['fields'].get('DATA', {}).get('hex') for packet in reads)
    assert {value(packet, 'SECTION_COUNT') for packet in reads} == {len(reads)}
    files = list(destination.glob('capture_core*_window*.csv'))
    assert len(files) == 1
    rows = list(csv.reader(files[0].read_text().splitlines(), skipinitialspace=True))
    header_index = next(index for index, row in enumerate(rows) if row and row[0].startswith('time unit:'))

    def trim(row):
        values = [entry.strip() for entry in row]
        if values[-1] == '':
            values.pop()
        return values

    assert trim(rows[header_index])[1:] == manifest['signals']
    samples = []
    for row in rows[header_index + 1:]:
        if not row:
            continue
        values = trim(row)
        assert len(values) == width + 1 and int(values[0]) == len(samples)
        assert all(entry in ('0', '1') for entry in values[1:])
        samples.append(dict(zip(manifest['signals'], map(int, values[1:]))))
    assert len(samples) == 1024
    identity(destination / 'identity_after.log', manifest['user_code'])
    result = dict(attempt, csv_sha256=digest(files[0]), samples=len(samples),
                  first=snapshot(samples[0], schema), last=snapshot(samples[-1], schema),
                  signals={name: dict(values=dict(Counter(str(sample[name]) for sample in samples)),
                                      transitions=sum(previous[name] != current[name]
                                                      for previous, current in zip(samples, samples[1:])))
                           for name in manifest['signals']},
                  gao_open_and_ram_read_confirmed=True, independent_identity_after=manifest['user_code'],
                  root_cause_confirmed=False)
    (destination / 'status_summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(directory=str(destination), first=result['first'], last=result['last'],
                         ui_gray_transitions=sum(result['signals'].get(f'ui_gray_sync[{bit}]', {})
                                                 .get('transitions', 0)
                                                 for bit in range(8))), indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--count', type=int, default=1)
    args = parser.parse_args()
    if args.sequence < 1 or not 1 <= args.count <= 3:
        parser.error('positive sequence and count 1..3 required')
    with Path('/tmp/gw138k_20261025.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for sequence in range(args.sequence, args.sequence + args.count):
            capture(args.candidate, sequence)
            time.sleep(0.43)
