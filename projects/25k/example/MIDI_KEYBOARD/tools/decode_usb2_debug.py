#!/usr/bin/env python3
"""Decode the optional MIDI USB2 independent-clock GAO capture."""
import argparse
import csv
import json
from pathlib import Path
from xml.etree import ElementTree


GAO_ID = '1101001010111000'
PROBE_ID = '1101001010111101'
BUS = 'status_50mhz[31:0]'


def load_config(path, probe=False):
    root = ElementTree.parse(path).getroot()
    core = root.find('AoCore')
    identity = PROBE_ID if probe else GAO_ID
    width = 256 if probe else 32
    top = 'midi_usb2_probe_top' if probe else 'midi_keyboard_top'
    if (root.findtext('GAO_ID') != identity or root.findtext('Mode') != 'Standard'
            or core is None or core.get('module_name') != top
            or core.get('sample_clock') != 'clk_50mhz' or core.get('storage_depth') != '128'):
        raise ValueError('USB2 debug GAO identity, top, clock or depth does not match')
    bus = core.find('SignalList/Bus')
    if (bus is None or bus.get('name') != f'status_50mhz[{width-1}:0]' or
            [signal.text for signal in bus.findall('Signal')] !=
            [f'status_50mhz[{index}]' for index in range(width-1, -1, -1)]):
        raise ValueError('USB2 debug requires the complete ordered status stream')
    return identity


def phy_fields(payload):
    result = {'boot_stage': payload >> 24, 'phy_state': (payload >> 21) & 7,
              'device_address': (payload >> 14) & 127, 'line_state': (payload >> 6) & 3}
    for name, bit in {'boot_done': 13, 'boot_error': 12, 'protocol_reset': 11,
                      'ulpi_dir': 10, 'ulpi_nxt': 9, 'ulpi_stp': 8,
                      'utmi_rxactive': 5, 'utmi_rxerror': 4, 'utmi_txvalid': 3,
                      'utmi_txready': 2, 'drive_arm': 1, 'reset60_released': 0}.items():
        result[name] = bool(payload & (1 << bit))
    return result


def read_samples(path, bus=BUS, width=32):
    header = None
    data_seen = False
    values = []
    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        for row in csv.reader(source):
            row = [cell.strip() for cell in row]
            while row and not row[-1]:
                row.pop()
            if not row:
                continue
            if not data_seen:
                data_seen = row == ['Data:']
                continue
            if header is None:
                header = row
                if not row[0].startswith('time unit:') or len(set(row)) != len(row) or bus not in row:
                    raise ValueError('CSV lacks the USB2 debug status bus')
                continue
            if len(row) != len(header):
                raise ValueError('CSV column count changed')
            value = int(row[header.index(bus)], 16)
            if not 0 <= value < 1 << width:
                raise ValueError(f'USB2 debug value exceeds {width} bits')
            values.append(value)
    if len(values) != 128:
        raise ValueError('Expected one complete 128-sample GAO window')
    return values


def decode_samples(values):
    words = []
    for value in values:
        words.append({'sample': len(words), 'raw_hex': f'{value:08X}',
                          'page': (value >> 6) & 3, 'payload': value >> 8,
                          'cohort': (value >> 1) & 1, 'flags': (value >> 2) & 15,
                          'heartbeat': value & 1})
    if len(words) != 128:
        raise ValueError('Expected one complete 128-sample GAO window')
    runs = []
    for sample in words:
        key = tuple(sample[name] for name in ('page', 'payload', 'cohort', 'flags'))
        if not runs or runs[-1]['key'] != key:
            runs.append({'page': sample['page'], 'payload': sample['payload'], 'count': 1,
                         'sample': sample['sample'], 'status': sample, 'key': key})
        else:
            runs[-1]['count'] += 1
    cycles = []
    for index in range(len(runs) - 3):
        group = runs[index:index + 4]
        if ([run['page'] for run in group] == [0, 1, 2, 3] and all(run['count'] == 8 for run in group)
                and len({(run['status']['cohort'], run['status']['flags']) for run in group}) == 1
                and group[3]['payload'] == 0x55aa33):
            values = phy_fields(group[0]['payload'] | ((group[1]['payload'] >> 16) << 24))
            values['source_status32'] = group[0]['payload'] | ((group[1]['payload'] >> 16) << 24)
            flags = group[0]['status']['flags']
            ticks = group[2]['payload'] & 255
            values.update({'online': bool(flags & 8), 'hs_active': bool(flags & 4),
                           'control_online': bool(flags & 2), 'source_clock_alive': bool(flags & 1),
                           'phy_clock_ticks_per_ms': ticks, 'phy_clock_quantized_hz': ticks * 256000,
                           'midi_tx_accepted_words16': group[1]['payload'] & 65535,
                           'midi_rx_accepted_words16': group[2]['payload'] >> 8})
            cycles.append({'first_sample': group[0]['sample'], 'fields': values})
    return {'schema': 'midi-usb2-debug32-v2', 'sample_count': len(words),
            'samples': words, 'complete_page_cycles': cycles,
            'latest': cycles[-1]['fields'] if cycles else None}


def decode(path, probe=False):
    if not probe:
        return decode_samples(read_samples(path))
    samples = read_samples(path, 'status_50mhz[255:0]', 256)
    lanes = [decode_samples([(value >> (32*index)) & 0xffffffff for value in samples]) for index in range(8)]
    usb, events = lanes[:2]
    latest = None
    if all(lane['latest'] is not None for lane in lanes):
        history = events['latest']['source_status32']
        latest = dict(usb['latest'], states_seen=[index for index in range(8) if history & (1 << (24+index))],
                      lines_seen=[index for index in range(4) if history & (1 << (20+index))],
                      rxerror_seen=bool(history & (1 << 19)), txvalid_seen=bool(history & (1 << 18)),
                      rxactive_seen=bool(history & (1 << 17)), txready_seen=bool(history & (1 << 16)),
                      received_utmi_bytes_saturated8=(history >> 8) & 255, last_rxcmd=history & 255)
        raw_se0, utmi_se0, rxcmd, phy_rx, utmi_rx, link_nxt = [lane['latest']['source_status32'] for lane in lanes[2:]]
        metadata = link_nxt >> 24
        latest.update(raw_se0_max_cycles24=raw_se0 & 0xffffff, raw_se0_runs8=raw_se0 >> 24,
                      utmi_se0_max_cycles24=utmi_se0 & 0xffffff, utmi_se0_runs8=utmi_se0 >> 24,
                      raw_rxcmd_count24=rxcmd & 0xffffff, raw_phy_rx_bytes24=phy_rx & 0xffffff,
                      utmi_rx_bytes24=utmi_rx & 0xffffff, link_nxt_cycles24=link_nxt & 0xffffff,
                      last_phy_rx_byte=phy_rx >> 24, last_utmi_rx_byte=utmi_rx >> 24,
                      raw_line_state=metadata >> 6, monitored_utmi_line_state=(metadata >> 4) & 3,
                      raw_line_valid=bool(metadata & 8), raw_se0_armed=bool(metadata & 4),
                      utmi_se0_armed=bool(metadata & 2), protocol_active=bool(metadata & 1),
                      raw_se0_max_us_nominal60mhz=(raw_se0 & 0xffffff)/60,
                      utmi_se0_max_us_nominal60mhz=(utmi_se0 & 0xffffff)/60,
                      statistics_snapshot_atomic_across_lanes=False)
    return {'schema': 'midi-usb2-probe256-v2', 'sample_count': len(samples),
            'usb': usb, 'events': events, 'statistics': lanes[2:], 'latest': latest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    print(json.dumps(decode(args.csv, probe=args.probe), indent=2))


if __name__ == '__main__':
    main()
