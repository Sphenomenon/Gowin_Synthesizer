"""Stage immutable upstream support sources, verifying their recorded SHA256."""
import hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
v=p/'vendor/ultraembedded_usb_hs'
m=json.loads((v/'UPSTREAM.json').read_text())
for name,record in m.items():
 for f,digest in record['files'].items():
  if hashlib.sha256((v/name/f).read_bytes()).hexdigest()!=digest:
   raise SystemExit('Upstream source changed: '+name+'/'+f)
g=p/'generated'
g.mkdir(exist_ok=True)
defs=(v/'cdc/usbf_defs.v').read_text()
for f in (v/'cdc').glob('*.v'):
 if f.name in ('usb_cdc_core.v','usb_desc_rom.v','usbf_defs.v'):continue
 (g/('hs_'+f.name)).write_text(f.read_text().replace('`include "usbf_defs.v"',defs))
(g/'hs_ulpi_wrapper.v').write_text((v/'ulpi/ulpi_wrapper.v').read_text())
