#!/usr/bin/env python3
"""PC -> 115200 8N1 MIDI channel 1; K138 reports accepted core state.
This small verification CLI does not change the teammate's GUI or protocol.
"""
import argparse,binascii,json,re,struct,time
DEFAULT_PORT='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0'

def decode_record(line):
    m=re.fullmatch(rb'(A138|C350|K138|E138) ((?:[0-9A-F]{8} ){8})([0-9A-F]{4})\r?\n',line)
    if not m:return None
    words=[int(w,16) for w in m[2].split()]
    if binascii.crc_hqx(struct.pack('<8I',*words),0xffff)!=int(m[3],16):raise ValueError('telemetry CRC mismatch')
    return m[1].decode(),words

def performance(words):
    state=words[2];bits=sum(words[4+k]<<(32*k) for k in range(4))
    return dict(sequence=words[0],applied_events=words[1],mode=['A','B','C','invalid'][(state>>3)&3],
        sound=['flute','strings','trumpet','marimba','piano','invalid','invalid','invalid'][(state>>7)&7],
        route=['stereo','left','right','mute'][(state>>5)&3],effects=state&7,active_voices=(state>>10)&63,
        gain_q15=state>>16,pc_input_errors=words[3],held_notes=[n for n in range(128) if (bits>>n)&1])

def expression(words):
    if words[7] != 0x43545231:
        raise ValueError('Unsupported E138 control schema')
    options, snap = words[1], words[3]
    signed = lambda value: value - (1 << 32) if value & 0x80000000 else value
    bend_index = (options >> 18) & 255
    return dict(sequence=words[0], vibrato=(options >> 4) & 127, glide=(options >> 11) & 127,
        bend_index=bend_index, bend=(bend_index-128)*64, pitch_q20=words[2],
        sustain=bool(options & 8), snap_request=options >> 26, snap_token=snap & 63,
        snap_done=bool(snap & 64), snap_error=bool(snap & 128), snap_count=(snap >> 8) & 255,
        snap_completed=snap >> 16, snap_left=signed(words[4]), snap_right=signed(words[5]),
        snap_sequence=words[6])


def bounded(low,high):
    def parse(s):
        value=int(s,0)
        if not low<=value<=high:raise argparse.ArgumentTypeError(f'must be {low}..{high}')
        return value
    return parse

def parse_args():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',default=DEFAULT_PORT);ap.add_argument('--dry-run',action='store_true')
    sub=ap.add_subparsers(dest='command',required=True)
    for name in ['note-on','note-off','play']:
        p=sub.add_parser(name);p.add_argument('note',type=bounded(0,127));p.add_argument('--velocity',type=bounded(1,127),default=100)
        if name=='play':p.add_argument('--seconds',type=float,default=1.0)
    p=sub.add_parser('chord');p.add_argument('notes',nargs='+',type=bounded(0,127));p.add_argument('--velocity',type=bounded(1,127),default=100);p.add_argument('--seconds',type=float,default=1.5)
    p=sub.add_parser('cc');p.add_argument('number',type=bounded(0,127));p.add_argument('value',type=bounded(0,127))
    p=sub.add_parser('program');p.add_argument('number',type=bounded(0,127))
    p=sub.add_parser('bend');p.add_argument('value',type=bounded(-8192,8191))
    sub.add_parser('panic');sub.add_parser('status')
    a=ap.parse_args()
    if hasattr(a,'seconds') and not 0<a.seconds<=60:ap.error('seconds must be >0 and <=60')
    return a

def payload(a):
    if a.command in ['note-on','play']:return bytes([0x90,a.note,a.velocity])
    if a.command=='note-off':return bytes([0x80,a.note,0])
    if a.command=='chord':return b''.join(bytes([0x90,n,a.velocity]) for n in dict.fromkeys(a.notes))
    if a.command=='cc':return bytes([0xb0,a.number,a.value])
    if a.command=='program':return bytes([0xc0,a.number])
    if a.command=='bend':
        value=a.value+8192;return bytes([0xe0,value&127,value>>7])
    if a.command=='panic':return bytes([0xb0,123,0])
    return b''

def fresh_status(port,timeout=4,after_sequence=None):
    end=time.monotonic()+timeout;cpu_sequence=None
    while time.monotonic()<end:
        decoded=decode_record(port.read_until(b'\n',size=1024))
        if decoded:
            kind,words=decoded
            if kind=='C350':
                cpu_sequence=words[0] if words[4]==0x43505531 and words[5]==0x50415353 and words[7]==0 else None
            if kind=='K138' and words[0]==cpu_sequence and (after_sequence is None or 0<((words[0]-after_sequence)&0xffffffff)<0x80000000):return performance(words)
    raise TimeoutError('No ready C350/K138 pair. The earlier A277 bitstream has no PC input; load the new performance build first.')

def main():
    a=parse_args();data=payload(a)
    if a.dry_run:
        print(data.hex(' ').upper() if data else 'read-only C350/K138 status');return
    import serial
    port=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=2)
    port.dtr=False;port.rts=False;port.port=a.port
    with port:
        # FTDI/USB hardware may still hold old records after a driver flush.
        # Drain for two real seconds before using a ready CPU/performance pair.
        port.reset_input_buffer();warmup=time.monotonic()+2
        while time.monotonic()<warmup:port.read_until(b'\n',size=1024)
        initial=fresh_status(port)
        if initial['pc_input_errors']:raise RuntimeError('PC receiver already reports input errors: '+str(initial))
        notes=[a.note] if a.command=='play' else list(dict.fromkeys(a.notes)) if a.command=='chord' else []
        try:
            if data:port.write(data);port.flush()
            if notes:
                end=time.monotonic()+a.seconds
                while time.monotonic()<end:
                    decoded=decode_record(port.read_until(b'\n',size=1024))
                    if decoded and decoded[0]=='K138':print(json.dumps(performance(decoded[1]),ensure_ascii=False))
            else:
                # Remove only the host's old receive backlog, then await fresh
                # periodic state. K138 is not a per-command acknowledgement.
                port.reset_input_buffer();print(json.dumps(fresh_status(port,after_sequence=initial['sequence']),ensure_ascii=False))
        finally:
            if notes:
                port.write(b''.join(bytes([0x80,n,0]) for n in notes));port.flush()
        if notes:
            port.reset_input_buffer();print(json.dumps(fresh_status(port,after_sequence=initial['sequence']),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (ValueError,TimeoutError,RuntimeError,OSError) as error:raise SystemExit(str(error))
