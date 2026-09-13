#!/usr/bin/env python3
"""Exercise the actual C parser with captured Push descriptors and malformed input."""
import ctypes as C
import hashlib, json, random, subprocess, sys
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
subprocess.run(["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror", "-O2",
                str(BASE/"firmware/midi_descriptor.c"), "-o", str(out/"parser.so")], check=True)
class Endpoint(C.Structure):
    _fields_ = [("configuration", C.c_uint8), ("interface", C.c_uint8),
                ("alternate", C.c_uint8), ("endpoint", C.c_uint8), ("max_packet", C.c_uint16)]
lib = C.CDLL(str(out/"parser.so"))
lib.midi_find_input.argtypes = [C.c_void_p, C.c_uint, C.POINTER(Endpoint)]
lib.midi_find_input.restype = C.c_int
def parse(data):
    e = Endpoint(); ret = lib.midi_find_input(C.create_string_buffer(bytes(data)), len(data), C.byref(e))
    return ret, {name: getattr(e, name) for name, _ in e._fields_}
capture = ROOT/"migration/midi_device_reference/ableton_push2_20260911_005756/usb_read_20260911_010608_120416/configuration.bin"
d = capture.read_bytes()
ret, ep = parse(d)
assert ret == 1 and ep == dict(configuration=1, interface=2, alternate=0, endpoint=0x82, max_packet=512), (ret,ep)
count = 1
for n in range(len(d)):
    assert parse(d[:n])[0] == -1, n
    count += 1
empty = bytes.fromhex("09 02 09 00 00 01 00 80 32")
assert parse(empty)[0] == 0
count += 1
p = 0
while p < len(d):
    for bad in [0,1,255]:
        x=bytearray(d); x[p] = bad
        assert parse(x)[0] == -1, (p,bad)
        count += 1
    p += d[p]
# Reject wrong class/protocol/alternate and malformed endpoint sizes.
p=0
while p < len(d):
    if d[p+1] == 4 and d[p+2] == 2:
        for offset,value in [(3,1),(5,255),(6,1),(7,2)]:
            x=bytearray(d);x[p+offset]=value
            assert parse(x)[0] == 0
            count += 1
    if d[p+1] == 5 and d[p+2] == 0x82:
        for size in [0,513,1024,0xffff]:
            x=bytearray(d);x[p+4:p+6]=size.to_bytes(2,"little")
            assert parse(x)[0] == -1
            count += 1
    p += d[p]
# Arbitrary bytes must terminate; each item has an independently bounded length.
rng=random.Random(569)
for _ in range(10000):
    x=bytearray(rng.randbytes(rng.randrange(9,4097)))
    x[:4]=bytes([9,2])+len(x).to_bytes(2,"little");x[5]=1
    assert parse(x)[0] in (-1,0,1)
    count += 1
class Profile(C.Structure):
    _fields_ = [("display_out",C.c_uint8),("midi_out",C.c_uint8),("display_mps",C.c_uint16),("midi_mps",C.c_uint16)]
lib.push_find_outputs.argtypes=[C.c_void_p,C.c_uint,C.POINTER(Profile)]
lib.push_find_outputs.restype=C.c_int
def outputs(data):
    e=Profile(); ret=lib.push_find_outputs(C.create_string_buffer(bytes(data)),len(data),C.byref(e))
    return ret,{name:getattr(e,name) for name,_ in e._fields_}
assert outputs(d)==(1,dict(display_out=1,midi_out=2,display_mps=512,midi_mps=512))
count+=1
for n in range(len(d)):
    assert outputs(d[:n])[0]==-1
    count+=1
p=0
while p<len(d):
    if d[p+1]==5 and d[p+2] in (1,2):
        for offset,value in [(2,0x81),(3,3),(4,0),(5,1)]:
            x=bytearray(d);x[p+offset]=value
            if x==d: continue
            assert outputs(x)[0]!=1,(p,offset,value)
            count+=1
    p+=d[p]
for _ in range(10000):
    x=bytearray(rng.randbytes(rng.randrange(9,4097)))
    x[:4]=bytes([9,2])+len(x).to_bytes(2,"little");x[5]=1
    assert outputs(x)[0] in (-1,0,1)
    count+=1
result=dict(passed=count, captured_endpoint=ep, descriptor_sha256=hashlib.sha256(d).hexdigest(), hardware=False)
(out/"parser_test.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
