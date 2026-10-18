#!/usr/bin/env python3
"""Check the CRC-protected P138 USB-A diagnostic field decoder."""
from pathlib import Path
import binascii,importlib.util,struct,sys

if len(sys.argv)!=2:raise SystemExit('usage: test_usb_in_decode.py CONTROL.PY')
control=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('control',control)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
words=[7,0x103,11,12,13,14,0x04030201,15]
body=''.join(f'{word:08X} ' for word in words).encode()
crc=binascii.crc_hqx(struct.pack('<8I',*words),0xffff)
kind,value=module.decode(b'P138 '+body+f'{crc:04X}\r\n'.encode(),usb_a=True)
assert kind=='P138'
assert value['usb_in_errors']==1
assert value['usb_in_duplicates']==2
assert value['usb_in_naks']==3
assert value['usb_disconnects']==4
assert value['usb_in_diagnostics_available']
assert value['usb_in_diagnostics_raw']=='04030201'
assert not value['usb_in_counter_saturated']
words[6]=0x00ff0000
body=''.join(f'{word:08X} ' for word in words).encode()
crc=binascii.crc_hqx(struct.pack('<8I',*words),0xffff)
_,value=module.decode(b'P138 '+body+f'{crc:04X}\n'.encode(),usb_a=True)
assert value['usb_in_counter_saturated'] and value['usb_in_naks']==255
words[6]=0xffffffff
body=''.join(f'{word:08X} ' for word in words).encode()
crc=binascii.crc_hqx(struct.pack('<8I',*words),0xffff)
_,value=module.decode(b'P138 '+body+f'{crc:04X}\n'.encode(),usb_a=True)
assert not value['usb_in_diagnostics_available']
assert value['usb_in_errors'] is None and value['usb_in_counter_saturated'] is None
print('PASS P138 USB IN decode: errors, duplicates, NAKs, disconnects, saturation')
