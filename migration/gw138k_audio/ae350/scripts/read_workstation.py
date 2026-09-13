#!/usr/bin/env python3
"""Read-only full-system A138/C350 capture, bound to a routed candidate."""
import argparse,binascii,datetime,hashlib,json,re,struct,sys,time
from pathlib import Path
import serial
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'scripts'))
from read_runtime import decode,analyze
from midi_serial import decode_record,performance,expression

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('build',type=Path)
    ap.add_argument('--seconds',type=float,default=10)
    ap.add_argument('--warmup',type=float,default=2,help='save but exclude initial USB backlog from the measurement interval')
    ap.add_argument('--audit',type=Path)
    ap.add_argument('--port',default='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0')
    args=ap.parse_args();assert 0<args.seconds<=60 and 0<=args.warmup<=10
    audit=json.loads((args.audit or args.build/'workstation_audit.json').read_text());assert audit['passed']
    fs=args.build/'Prj1/impl/pnr/Prj1.fs'
    assert hashlib.sha256(fs.read_bytes()).hexdigest()==audit['bitstream_sha256']
    out=ROOT.parent/'results'/datetime.datetime.now().strftime('ae350_workstation_uart_%Y%m%d_%H%M%S_%f');out.mkdir();print(out,flush=True)
    port=serial.Serial(port=None,baudrate=115200,timeout=.3);port.dtr=False;port.rts=False;port.port=args.port
    performance_records=[];performance_pairs=[];performance_sequence=None
    expression_records=[];expression_pairs=[];expression_sequence=None
    audio=[];cpu=[];paired=[];rejected=[];partial=0;pending_sequence=None;warmup_chunks=0
    with port,(out/'raw_uart.bin').open('wb') as raw:
        measurement_start=time.monotonic()+args.warmup
        deadline=measurement_start+args.seconds
        while time.monotonic()<deadline:
            line=port.read_until(b'\n',size=1024)
            if not line:continue
            raw.write(line)
            # Opening a serial device may expose a queued pre-download record
            # or the driver/USB backlog boundary. Preserve every byte, then
            # validate only a fresh, time-bounded continuous interval.
            if time.monotonic()<measurement_start:
                warmup_chunks+=1;continue
            if line.startswith(b'A138 '):
                try:
                    record=decode(line);audio.append(record);pending_sequence=record['sequence'];performance_sequence=record['sequence']
                    print(f"A138 seq={record['sequence']} samples={record['audio_samples']} memory={record['memory_flags']:02x} faults={record['audio_status']:08x}",flush=True)
                except ValueError as e:rejected.append(dict(line=line.hex(),error=str(e)))
            elif line.startswith(b'K138 '):
                try:
                    decoded=decode_record(line)
                    if not decoded:raise ValueError('K138 framing')
                    words=decoded[1];record=performance(words);performance_records.append(record)
                    if words[0]==performance_sequence:performance_pairs.append(record);performance_sequence=None;expression_sequence=words[0]
                    print(f"K138 seq={record['sequence']} events={record['applied_events']} voices={record['active_voices']} notes={record['held_notes']} pc_errors={record['pc_input_errors']}",flush=True)
                except ValueError as error:rejected.append(dict(line=line.hex(),error=str(error)))
            elif line.startswith(b'E138 '):
                try:
                    decoded=decode_record(line)
                    if not decoded:raise ValueError('E138 framing')
                    record=expression(decoded[1]);expression_records.append(record)
                    if record['sequence']==expression_sequence:expression_pairs.append(record);expression_sequence=None
                    print(f"E138 seq={record['sequence']} vibr={record['vibrato']} glide={record['glide']} bend={record['bend']} snap={record['snap_completed']}",flush=True)
                except ValueError as error:rejected.append(dict(line=line.hex(),error=str(error)))
            elif line.startswith(b'C350 '):
                m=re.fullmatch(rb'C350 ((?:[0-9A-F]{8} ){8})([0-9A-F]{4})\r?\n',line)
                if not m:rejected.append(dict(line=line.hex(),error='CPU framing'));continue
                words=[int(v,16) for v in m[1].split()]
                if binascii.crc_hqx(struct.pack('<8I',*words),0xffff)!=int(m[2],16):
                    rejected.append(dict(line=line.hex(),error='CPU CRC'));continue
                cpu.append(words)
                if words[0]==pending_sequence:paired.append(words);pending_sequence=None
                print(f'C350 seq={words[0]} result={words[5]:08x} heartbeat={words[6]} trap={words[7]:08x}',flush=True)
            else:partial+=1
    # Earlier standalone boot records can remain in the USB UART buffer.
    # Pair online: a CPU packet must FOLLOW the matching A138 record. An old
    # C350 packet with a coincidentally equal sequence can never be paired back.
    status=analyze(audio)
    cpu_pass=len(paired)>=3 and all(x[4]==0x43505531 and x[5]==0x50415353 and x[7]==0 and 0x80000000<=x[3]<0x80004000 for x in paired)
    cpu_pass=cpu_pass and paired[-1][6]!=paired[0][6] and all(0<((b[2]-a[2])&0xffffffff)<100000000 and ((b[0]-a[0])&0xffffffff)==1 for a,b in zip(paired,paired[1:]))
    cpu_ui=bool(audit.get('cpu_ui'))
    ui_pass=bool(paired) and all((x[1]>>16)==0x5549 and (x[1]&0x70)==0x60 for x in paired) if cpu_ui else None
    pc_midi=bool(audit.get('pc_midi'))
    pc_status_pass=len(performance_pairs)>=3 and all(x['pc_input_errors']==0 for x in performance_pairs) if pc_midi else None
    expression_pass=len(expression_pairs)>=3 and all(not x['snap_error'] for x in expression_pairs) if audit.get('expression_controls') else None
    passed=(not audit.get('expression_controls') or expression_pass) and (not pc_midi or pc_status_pass) and status['digital_runtime_pass'] and cpu_pass and not rejected and (not cpu_ui or ui_pass)
    cpu_ddr=bool(audit.get('cpu_external_ddr'))
    summary=dict(passed=passed,expression_records=expression_records,expression_pairs=expression_pairs,expression_pass=expression_pass,build=str(args.build.resolve()),bitstream_sha256=audit['bitstream_sha256'],audio=status,audio_records=audio,cpu_records=cpu,cpu_pairs=paired,cpu_pass=cpu_pass,cpu_external_ddr_tested=cpu_ddr and cpu_pass,cpu_ui_tested=cpu_ui and cpu_pass and ui_pass,performance_records=performance_records,performance_pairs=performance_pairs,pc_status_pass=pc_status_pass,rejected=rejected,partial=partial,host_writes=0,requested_seconds=args.seconds,warmup_seconds=args.warmup,warmup_chunks=warmup_chunks,port=args.port,
        limits='Firmware-specific CPU/ROM/RAM/APB/score/record/note checks and FPGA internal audio/DDR/video counters. '+('External CPU DDR checks cover only the frozen firmware test addresses and masks. ' if cpu_ddr else 'CPU external DDR is not included. ')+('UI verifies firmware page readback and four actual frame-boundary publications. ' if cpu_ui else '')+'No analog headphone, HDMI receiver, G1 hardware or physical touch acceptance.')
    (out/'capture.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('PASS full-system digital runtime' if passed else 'NOT PASSED',flush=True)
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
