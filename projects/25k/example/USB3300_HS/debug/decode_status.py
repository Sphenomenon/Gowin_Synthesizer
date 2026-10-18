"""Decode USB2's 50 MHz status bus from a Gowin GAO CSV."""
import argparse
import csv
import json
from pathlib import Path


def page_fields(page, payload, image='probe'):
    if image == 'hs':
        if page == 0:
            return {'vendor_id': payload >> 16, 'product_id': payload & 0xffff}
        if page == 1:
            mode = payload >> 24
            flags = payload & 0xff
            return {'utmi_opmode': mode >> 6, 'utmi_xcvrselect': (mode >> 4) & 3,
                    'utmi_termselect': bool(mode & 8), 'utmi_linestate': (mode >> 1) & 3,
                    'chirp_active': bool(mode & 1), 'device_address': (payload >> 16) & 0x7f,
                    'usb_reset_count8': (payload >> 8) & 0xff,
                    **{name: bool(flags & (1 << bit)) for bit, name in {
                        7:'hs_seen',6:'chirp_seen',5:'utmi_rxerror_seen',4:'boot_error',
                        3:'boot_done',2:'hs_active',1:'configured',0:'overflow_seen'}.items()}}
        if page == 2:
            flags = (payload >> 16) & 0xff
            return {'boot_stage': payload >> 24, 'hs_state': flags >> 5,
                    'boot_done':bool(flags & 8), 'hs_active':bool(flags & 4),
                    'configured':bool(flags & 2), 'boot_error':bool(flags & 1),
                    'received_count16':payload & 0xffff}
        return {'echo_consumed_count16':payload >> 16,'overflow_count16':payload & 0xffff}
    if page == 0:
        if image == 'buscheck':
            return {'scratch_verified_count': (payload >> 16) & 0x1ff,
                    'scratch_mismatch_expected': (payload >> 8) & 0xff,
                    'scratch_mismatch_actual': payload & 0xff}
        if image in ('rxcmd', 'reset', 'buscheck'):
            return {'phase_last_rxcmd32': payload,
                    'phase_last_rxcmd_bytes': {
                        str(phase): (payload >> (phase * 8)) & 0xff
                        for phase in range(4)}}
        return {'vendor_id': payload >> 16, 'product_id': payload & 0xffff}
    if page == 1:
        if image == 'measure':
            return {'function_control': (payload >> 24) & 0xff,
                    'interface_control': (payload >> 16) & 0xff,
                    'otg_control': (payload >> 8) & 0xff,
                    'error_code': payload & 0xf}
        if image in ('lowpower', 'lowpower_pd'):
            return {'function_control': (payload >> 24) & 0xff,
                    'interface_control': (payload >> 16) & 0xff,
                    'otg_control': (payload >> 8) & 0xff,
                    'error_code': (payload >> 4) & 0xf}
        if image in ('termination', 'rxcmd', 'reset', 'buscheck'):
            return {'function_control': (payload >> 24) & 0xff,
                    'interface_control': (payload >> 16) & 0xff,
                    'otg_control': (payload >> 8) & 0xff,
                    'ulpi_dir': bool(payload & 4), 'ulpi_nxt': bool(payload & 2),
                    'ulpi_stp': bool(payload & 1)}
        if image in ('serial', 'activity'):
            return {'function_control_written': (payload >> 24) & 0xff,
                    'interface_control_written': (payload >> 16) & 0xff,
                    'otg_control_written': (payload >> 8) & 0xff,
                    'line_flags_byte': payload & 0xff,
                    'line_flags': {name: bool(payload & (1 << bit))
                                   for bit, name in {
                                       7: 'attach_request', 6: 'init_done', 5: 'usb_oe',
                                       4: 'dp_rx', 3: 'dn_rx', 2: 'ulpi_data2',
                                       1: 'ulpi_data1', 0: 'ulpi_data0',
                                   }.items()}}
        return {'function_control': (payload >> 24) & 0xff,
                'interface_control': (payload >> 16) & 0xff,
                'otg_control': (payload >> 8) & 0xff,
                'last_read': payload & 0xff}
    if page == 2:
        if image == 'measure':
            return {'debug_last': payload >> 24, 'line_state_last': (payload >> 24) & 3,
                    'debug_line_seen_mask': (payload >> 20) & 0xf,
                    'debug_read_count': payload & 0xfffff}
        if image in ('lowpower', 'lowpower_pd'):
            return {'direct_line_seen_masks16': payload >> 16,
                    'phase_direct_line_states_seen': {
                        str(phase): [line for line in range(4)
                                     if payload & (1 << (16 + phase * 4 + line))]
                        for phase in range(4)},
                    'phase_flags16': payload & 0xffff,
                    'phase_validations': {
                        str(phase): {name: bool(payload & (1 << (phase * 4 + bit)))
                                     for bit, name in enumerate((
                                         'sample_valid', 'clock_stop_seen',
                                         'wake_completed', 'register_readback_verified'))}
                        for phase in range(4)}}
        flags = (payload >> 16) & 0xff
        if image in ('termination', 'rxcmd', 'reset', 'buscheck'):
            return {'termination_stage': payload >> 24, 'error_code': flags >> 4,
                    'done': bool(flags & 8), 'id_ok': bool(flags & 4),
                    'error': bool(flags & 1), 'line_seen_masks16': payload & 0xffff,
                    'phase_line_states_seen': {
                        str(phase): [line for line in range(4)
                                     if payload & (1 << (phase * 4 + line))]
                        for phase in range(4)}}
        if image in ('serial', 'activity'):
            return {'initialization_stage': payload >> 24, 'snapshot_flags_byte': flags,
                    'pre_serial_phy_status_packed_low4': flags >> 4,
                    'pre_serial_phy_line_state': (flags >> 4) & 3,
                    'pre_serial_session_valid': bool(flags & 0x40),
                    'pre_serial_session_end': bool(flags & 0x80),
                    'init_done': bool(flags & 8), 'usb_reset_released': bool(flags & 4),
                    'received_seen': bool(flags & 2), 'error_or_overflow': bool(flags & 1),
                    'received_count16': payload & 0xffff}
        return {'probe_stage': payload >> 24, 'snapshot_flags_byte': flags,
                'probe_done': bool(flags & 8), 'id_ok': bool(flags & 4),
                'scratch_ok': bool(flags & 2), 'error': bool(flags & 1),
                'rxcmd_count16': payload & 0xffff}
    if image == 'measure':
        return {'reserved': payload}
    if image in ('lowpower', 'lowpower_pd'):
        return {'phase_sample_counts32': payload,
                'phase_sample_counts': {
                    str(phase): (payload >> (phase * 8)) & 0xff
                    for phase in range(4)}}
    if image in ('rxcmd', 'reset', 'buscheck'):
        return {'rxcmd_seen_masks16': payload >> 16,
                'phase_rxcmd_line_states_seen': {
                    str(phase): [line for line in range(4)
                                 if payload & (1 << (16 + phase * 4 + line))]
                    for phase in range(4)},
                'rxcmd_count_saturated8': (payload >> 8) & 0xff,
                'rxdata_count_saturated8': payload & 0xff}
    if image == 'termination':
        return {'phase_last_status16': payload >> 16,
                'phase_last_status': {
                    str(phase): {'line_state': (payload >> (16 + phase * 4)) & 3,
                                 'session_valid': bool(payload & (1 << (18 + phase * 4))),
                                 'session_end': bool(payload & (1 << (19 + phase * 4)))}
                    for phase in range(4)},
                'rxcmd_count_saturated8': (payload >> 8) & 0xff,
                'rxdata_count_saturated8': payload & 0xff}
    if image == 'activity':
        event_flags = (payload >> 8) & 0xff
        seen_mask = payload & 0xff
        return {'raw_transition_count16': payload >> 16,
                'activity_event_flags_byte': event_flags,
                'serial_tx_seen': bool(event_flags & 4),
                'serial_usb_reset_asserted_seen': bool(event_flags & 2),
                'serial_usb_reset_released_seen': bool(event_flags & 1),
                'raw_data_seen_mask8': seen_mask,
                'raw_data_values_seen': [f'{value:03b}' for value in range(8)
                                         if seen_mask & (1 << value)]}
    if image == 'serial':
        return {'echo_queued_count16': payload >> 16, 'overflow_count16': payload & 0xffff}
    return {'rxdata_count16': payload >> 16,
            'ulpi_data': (payload >> 8) & 0xff,
            'ulpi_dir': bool(payload & 4), 'ulpi_nxt': bool(payload & 2),
            'ulpi_stp': bool(payload & 1)}


def snapshot(value, image='probe'):
    payload = value >> 32
    page = (value >> 1) & 3
    if image == 'measure':
        flags = {name: bool(value & (1 << bit)) for bit, name in {
            6: 'measurement_ready', 5: 'id_ok', 4: 'error',
            3: 'clock_alive', 0: 'heartbeat50_fast'}.items()}
        fields = page_fields(page, payload, image)
        fields.update({'measurement_stage': (value >> 8) & 0xff,
                       'ready': flags['measurement_ready'], 'id_ok': flags['id_ok'],
                       'error': flags['error'], 'clock_alive': flags['clock_alive']})
        return {'raw_hex': f'{value:016X}', 'page': page,
                'payload_hex': f'{payload:08X}', 'payload': fields,
                'measurement_stage': (value >> 8) & 0xff, 'flags': flags}
    if image in ('lowpower', 'lowpower_pd'):
        flags = {name: bool(value & (1 << bit)) for bit, name in {
            7: 'clock_stop_seen', 6: 'diagnostic_done', 5: 'id_ok',
            4: 'error', 3: 'clock_alive', 0: 'heartbeat50_fast',
        }.items()}
        fields = page_fields(page, payload, image)
        fields.update({'diagnostic_stage': (value >> 8) & 0xff,
                       'done': flags['diagnostic_done'], 'id_ok': flags['id_ok'],
                       'error': flags['error'], 'clock_stop_seen': flags['clock_stop_seen'],
                       'clock_alive': flags['clock_alive']})
        return {'raw_hex': f'{value:016X}', 'page': page,
                'payload_hex': f'{payload:08X}', 'payload': fields,
                'diagnostic_stage': (value >> 8) & 0xff, 'flags': flags}
    names = ({7: 'probe_done', 6: 'id_ok', 5: 'scratch_ok', 4: 'error'}
             if image == 'probe' else
             {7: 'termination_done', 6: 'id_ok', 5: 'reserved', 4: 'error'}
             if image in ('termination', 'rxcmd', 'reset', 'buscheck') else
             {7: 'init_done', 6: 'usb_reset_released', 5: 'received_seen', 4: 'error_or_overflow'})
    if image == 'hs':
        names = {7:'boot_done',6:'hs_active',5:'configured',4:'boot_error'}
    names.update({
        3: 'clock_alive', 0: 'heartbeat50_fast',
    })
    flags = {name: bool(value & (1 << bit)) for bit, name in names.items()}
    return {'raw_hex': f'{value:016X}', 'page': page,
            'payload_hex': f'{payload:08X}', 'payload': page_fields(page, payload, image),
            'phy_clock_count_10ms': (value >> 12) & 0xfffff,
            'probe_stage_low4' if image == 'probe' else 'init_stage_low4': (value >> 8) & 0xf,
            'flags': flags}


def aggregate_pages(samples):
    runs = []
    for sample in samples:
        status = sample['status']
        if (not runs or runs[-1]['page'] != status['page']
                or runs[-1]['payload_hex'] != status['payload_hex']):
            runs.append({'page': status['page'], 'payload_hex': status['payload_hex'],
                         'payload': status['payload'], 'first_sample': sample['sample'],
                         'last_sample': sample['sample'], 'sample_count': 1})
        else:
            runs[-1]['last_sample'] = sample['sample']
            runs[-1]['sample_count'] += 1
    cycles = []
    for index in range(len(runs) - 3):
        group = runs[index:index + 4]
        if ([run['page'] for run in group] == [0, 1, 2, 3]
                and all(run['sample_count'] == 8 for run in group)):
            fields = {}
            for run in group:
                fields.update(run['payload'])
            cycles.append({'first_sample': group[0]['first_sample'],
                           'last_sample': group[-1]['last_sample'],
                           'page_payloads_hex': {str(run['page']): run['payload_hex']
                                                 for run in group},
                           'fields': fields})
    return runs, cycles


def decode(path, image='probe'):
    if image not in ('probe', 'serial', 'activity', 'termination', 'rxcmd', 'reset', 'buscheck', 'lowpower', 'lowpower_pd', 'measure', 'hs'):
        raise ValueError('image must be probe, serial, activity, termination, rxcmd, reset, buscheck, lowpower, lowpower_pd or measure or hs')
    data_seen = False
    header = None
    samples = []
    with path.open(encoding='utf-8-sig', newline='') as source:
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
                if (not row[0].startswith('time unit:') or len(set(row)) != len(row)
                        or 'status_50mhz[63:0]' not in row):
                    raise ValueError('CSV does not contain the USB2 50 MHz GAO bus')
                continue
            if len(row) != len(header):
                raise ValueError('CSV column count changed')
            value = int(row[header.index('status_50mhz[63:0]')], 16)
            if not 0 <= value < 1 << 64:
                raise ValueError('status exceeds 64 bits')
            samples.append({'sample': len(samples), 'export_time_label': row[0],
                            'status': snapshot(value, image)})
    if not samples:
        raise ValueError('no USB GAO samples found')
    page_runs, page_cycles = aggregate_pages(samples)
    heartbeats = [sample['status']['flags']['heartbeat50_fast'] for sample in samples]
    result = {'source': str(path.resolve()), 'image': image, 'sample_count': len(samples),
            'sample_clock_hz': 50000000,
            'heartbeat50_alternates_each_sample':
                all(a != b for a, b in zip(heartbeats, heartbeats[1:]))
                if len(heartbeats) > 1 else None,
            'page_runs': page_runs, 'complete_page_cycles': page_cycles,
            'image_note': ('Four phases use USB3300 Table 6-6 low-power direct DATA[1:0] '
                           'LineState outputs: dual pulldown, FS pullup, LS pullup, dual pulldown. '
                           + ('FS uses OTG04 (DP pullup plus DM pulldown) per Table 6-8; '
                              'LS uses OTG00. ' if image == 'lowpower_pd' else
                              'FS and LS use OTG00. ') +
                           'The independent 50 MHz domain verifies CLKOUT stopped and DIR high, '
                           'then samples synchronized DATA[1:0] after settling. Each phase has '
                           'sixteen samples; masks include all states observed, not a pass/fail '
                           'judgment of the expected line value. Validation flags separately '
                           'record sampling, stop, wake and register-readback completion. '
                           'FC/IF/OTG are last-read shadow values, not instantaneous sleep reads. '
                           'STP wakes the PHY after each phase and final FC41/IF00/OTG06 is '
                           'detached. All payload and metadata snapshots are committed in '
                           'the 50 MHz domain, so capture continues while CLKOUT is absent. '
                           'This image runs no USB device protocol and does not prove enumeration.'
                           if image in ('lowpower', 'lowpower_pd') else
                           'Control values are the initialization sequence\'s successfully written '
                           'shadow values, not PHY register readbacks. Serial flags describe '
                           'initialization/USB reset/reception/error, not PHY probe ID/scratch tests. '
                           'The pre-serial packed PHY status is {SessionEnd, SessionValid, '
                           'LineState[1:0]}, not the raw Debug register. After a 100 us settling '
                           'delay following Function Control 0x45 readback, synchronous ULPI '
                           'reads capture Debug 0x15 LineState[1:0] and then Interrupt Status '
                           '0x13 SessionEnd/SessionValid before entering serial mode. These '
                           'sequential snapshots alone do not identify a connection fault.'
                           + (' Activity page 3 records DATA[2:0] transitions and values seen '
                              'only after init_done, plus TX and decoded USB reset history; '
                              'it does not count packets or prove physical host reset signaling.'
                              if image == 'activity' else '')
                           if image in ('serial', 'activity') else
                           'Four phases stay in synchronous ULPI: both pull-downs, FS pull-up, '
                           'LS pull-up, both pull-downs. Each phase samples Debug15 and '
                           'Status13 sixteen times. The short build uses a 10 ms settling '
                           'wait and 1 ms sample gaps; the extended build uses 100 ms and '
                           '10 ms. Use the capture manifest to identify the build. The final '
                           'state is detached. No EP0 or device protocol runs in this image; '
                           'host enumeration is not expected. Raw RxCmd/RxData summaries '
                           'saturate at 255 and are not packet counts.'
                           if image == 'termination' else
                           'After ID validation, the buscheck image writes and immediately '
                           'reads Scratch16 with each byte 00..FF; page 0 reports verified '
                           'count (256 means all passed) and the first mismatch expected/actual '
                           'bytes (zero initially). It then runs the original 55/AA tests, '
                           'IF08 check, FC61 reset with 1 ms fixed wait and FC41 readback, '
                           'and the four long-window termination phases. Page 2 is the '
                           'post-settle Debug15 mask and page 3 is the RxCmd mask plus '
                           'capture-time global RxCmd/RxData totals. Phase RxCmd histories '
                           'include intermediate configuration/detach and have no timestamps. '
                           'A zero phase mask means no event, not SE0. Register responses '
                           'and turnaround cycles are excluded. Global counters may increase '
                           'after DONE; phase histories freeze. No USB device protocol runs; '
                           'the final state is detached. This validates digital register '
                           'transport, not analog signal quality or device enumeration.'
                           if image == 'buscheck' else
                           ('The reset image writes FC61, waits 60000 PHY clocks (1 ms), '
                           'then reads FC once and requires Reset=0 and FC41 before the phases. '
                           if image == 'reset' else '') +
                           'Same four synchronous ULPI termination phases as the extended '
                           'termination image (100 ms settle, 10 ms gaps). Page 0 holds the '
                           'last unsolicited RxCmd byte per phase; page 3 holds per-phase '
                           'RxCmd LineState seen masks. A zero mask means no observed event, '
                           'not SE0. Register responses and turnaround cycles are excluded. '
                           'Phase histories include configuration writes, intermediate detach, '
                           'settle and sample gaps; they are not restricted to the settled '
                           'Debug15 sample window. Last bytes have no timestamp or freshness '
                           'marker. Only phase-scoped events enter these histories; the global '
                           'RxCmd/RxData summaries include other eligible cycles and are not '
                           'packet counts. Global totals may keep increasing after DONE, '
                           'while phase histories stop updating. Debug15 samples remain '
                           'on page 2. No USB device '
                           'protocol runs, and the final state is detached.'
                           if image in ('rxcmd', 'reset', 'buscheck') else
                           'Probe flags describe PHY ID/scratch tests; these are not CDC reception flags.'),
            'note': ('Lowpower uses a distinct 50 MHz-only status layout. The low 32 bits contain '
                    'stage[15:8] and flags[7:3], not a measured PHY frequency. Each page lasts '
                    'eight samples; all four payloads and metadata commit together before page 0. '
                    'A zero direct mask means no samples, not SE0. CSV has no GAO identity; '
                    'match it to the capture manifest. Time labels do not establish USB bit timing.'
                    if image in ('lowpower', 'lowpower_pd') else
                    'CSV time labels are retained as exported; they do not establish USB bit timing. '
                    'CSV contains no GAO ID; select the image layout matching the capture record. '
                    'Each complete 0,1,2,3 cycle contains eight samples per page and is coherent '
                    'because the observer commits its 128-bit mailbox only before page 0. '
                    'There is no snapshot sequence or freshness flag: a capture need not contain '
                    'a newly acknowledged snapshot, and repeated page cycles may show the same '
                    'previous snapshot. Before any 60 MHz acknowledgement, payload pages are zero. '
                    'The clock count is a separate 10 ms measurement; zero persists after a full '
                    'stopped-clock window. This is not a complete ULPI or USB protocol trace.'),
            'samples': samples}
    if image == 'hs':
        result['image_note'] = (
            'High Speed CDC image: boot validates USB3300 ID, Scratch55/AA and '
            'FC41/IF00/OTG00 readbacks before handing the synchronous ULPI bus to '
            'the UTMI-to-ULPI wrapper. Runtime mode fields are UTMI controls, not '
            'PHY register readbacks. hs_active and configured describe current '
            'core state; hs_seen, chirp_seen and utmi_rxerror_seen latch history. '
            'device_address is the requested address; the SIE commits it only '
            'after the status ACK. RX and echo-consumed counters expose their '
            'low 16 bits; USB reset clears the queue but retains cumulative '
            'counts. Echo consumption is not proof of host reception; correlate '
            'with the host loopback report. READY means PHY clock alive; DONE '
            'means boot_done, hs_active, configured and no boot_error.')
    if image == 'measure':
        result['image_note'] = (
            'Voltage-measurement image: FC45/IF00/OTG04 remains active, DP pullup plus '
            'DM pulldown. Debug15 is polled continuously. READY means ID/Scratch/configuration '
            'and at least one Debug read succeeded, not enumeration or normal LineState. '
            'FC/IF/OTG are last-read values. This image never suspends CLKOUT.')
        result['note'] = (
            'Measure uses independent 50MHz snapshots; low32 contains stage and flags, '
            'not PHY frequency. Match CSV to the D2AF capture manifest. Time labels do '
            'not establish USB bit timing.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', choices=('hs',), default='hs',
                        help='Payload layout to decode (default: hs); CSV alone has no GAO ID')
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        text = json.dumps(decode(args.csv, args.image), indent=2) + '\n'
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
