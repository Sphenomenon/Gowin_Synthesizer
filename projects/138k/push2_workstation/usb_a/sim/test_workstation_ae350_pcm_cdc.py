#!/usr/bin/env python3
"""Strict boundary-gate negatives; synthetic VG cases are never actual VG proof."""
from pathlib import Path
import shutil
import tempfile
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_ae350_pcm_cdc import (
 A,PcmNetlist,Graph,source_contract,validate_candidate_sdc,cdc_bundle,audit_apb,exact_closure)

def truth(width,fn):
 return f"{1<<width}'h"+format(sum(int(bool(fn([(i>>b)&1 for b in range(width)])))<<i for i in range(1<<width)),'x')

def apb_fixture():
 """Independent scalar model of the reviewed equations, not Gowin output."""
 widths=dict(request_held=49,request_local=49,response_held=33,response_local=33,p_release=3,a_release=3,state=2,
  request_toggle=None,acknowledge_toggle=None,req_meta=None,req_sync=None,req_settled=None,request_decoded=None,
  ack_meta=None,ack_sync=None,ack_settled=None)
 compute={'request_local','response_held','a_release','acknowledge_toggle','req_meta','req_sync','req_settled','request_decoded'}
 lines=['module apb ( pclk, audio_clk, raw_clear, launch, accept, command_valid );',
  'input pclk;','input audio_clk;','input raw_clear;','input launch;','input accept;','output command_valid;']
 def q(name,bit=None):return name+(''if bit is None else '_'+str(bit))+'_q'
 def lut(name,inputs,fn):
  lines.append(f"LUT{len(inputs)} {name}_lut (\n .F({name}), "+', '.join(f'.I{i}({v})'for i,v in enumerate(inputs))+'\n);')
  lines.append(f'defparam {name}_lut.INIT = '+truth(len(inputs),fn)+';')
  return name
 pclear=lut('pclear',[q('p_release',2)],lambda v:not v[0]);aclear=lut('aclear',[q('a_release',2)],lambda v:not v[0])
 request_ce=lut('request_ce',[q('req_sync'),q('req_settled')],lambda v:v[0]!=v[1])
 response_ce=lut('response_ce',[q('state',0),q('state',1),q('ack_settled'),q('request_toggle')],lambda v:v[0]and not v[1]and v[2]==v[3])
 toggled=lut('toggled',[q('request_toggle')],lambda v:not v[0])
 lut('command_valid',[q('a_release',2),q('request_decoded'),q('req_settled'),q('acknowledge_toggle')],lambda v:v[0]and v[1]and(v[2]!=v[3]))
 for name,width in widths.items():
  for bit in range(width)if width else [None]:
   stem=name+(''if bit is None else '_'+str(bit));clock='audio_clk'if name in compute else 'pclk'
   d="1'b0";ce="1'b1";clear=aclear if name in compute else pclear
   if name.endswith('_release'):d=q(name,bit-1)if bit else "1'b1";clear='raw_clear'
   elif name=='request_local':d=q('request_held',bit);ce=request_ce
   elif name=='response_local':d=q('response_held',bit);ce=response_ce
   elif name in ['request_held','request_toggle']:ce='launch';d=toggled if name=='request_toggle'else "1'b0"
   elif name in ['response_held','acknowledge_toggle']:ce='accept';d=q('req_settled')if name=='acknowledge_toggle'else "1'b0"
   elif name in ['req_meta','req_sync','req_settled','ack_meta','ack_sync','ack_settled']:
    d=q(dict(req_meta='request_toggle',req_sync='req_meta',req_settled='req_sync',ack_meta='acknowledge_toggle',ack_sync='ack_meta',ack_settled='ack_sync')[name])
   lines.append(f'DFFCE {stem}_s0 (\n .Q({q(name,bit)}), .D({d}), .CE({ce}), .CLEAR({clear}), .CLK({clock})\n);')
 lines+=['endmodule','module top ( pclk, audio_clk );','input pclk;','input audio_clk;',
  'apb \\u_managed/pcm_apb/commands (\n .pclk(pclk), .audio_clk(audio_clk), .raw_clear(reset), .launch(launch), .accept(accept), .command_valid(cv)\n);','endmodule']
 return '\n'.join(lines)+'\n'

class BoundaryGate(unittest.TestCase):
 def test_reviewed_source_and_candidate_constraints(self):
  d=source_contract(ROOT);self.assertFalse(d['physical_CDC_accepted'])
  s=cdc_bundle()['sdc'];r=validate_candidate_sdc(s);self.assertFalse(r['actual_endpoint_resolution_verified'])
  mutations=[s.replace('10.000','11.000',1),s+s.splitlines()[0]+'\n']
  mutations += [s+line+'\n'for line in [
   'set_false_path -to [get_pins {u_managed/pcm_apb/commands/request_local*/D}]',
   'set_false_path -to [get_pins {*}]',
   'set_false_path -through [get_pins {u_managed/*}]',
   'set_false_path -to [get_regs {*}]',
   'set_max_delay 100.000 -from [get_regs {u_*}] -to [get_regs {u_managed/*}]',
   'set_min_delay 0.000 -to [get_pins {*/PRESET}]',
   'set_false_path -to [get_pins {*/CLEAR}]',
   'set_false_path -from [get_clocks {audio_76m8}]',
   'set_clock_groups -asynchronous -group {audio_76m8} -group {cpu_ram50}',
   'set_multicycle_path 4 -to [get_regs {*}]',
   'set_false_path -to [get_pins *]',
   'set_false_path']]
  for bad in mutations:
   with self.subTest(bad=bad[-100:]),self.assertRaises(ValueError):validate_candidate_sdc(bad)
  from tools.workstation_runtime_clock_audit import MODE_EXCLUSIONS
  validate_candidate_sdc(s+'\n'.join(MODE_EXCLUSIONS)+'\n')

 def test_source_manifest_and_identity_drift_rejected(self):
  reviewed=source_contract(ROOT)
  with tempfile.TemporaryDirectory()as directory:
   copy=Path(directory)
   for name in ['tools/workstation_ae350_pcm_cdc_policy.json',*reviewed['source_sha256']]:
    dest=copy/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
   source_contract(copy)
   target=copy/'rtl/audio/workstation_ae350_pcm_session.sv';original=target.read_bytes()
   target.write_bytes(original+b'\n// drift\n')
   with self.assertRaisesRegex(ValueError,'reviewed source changed'):source_contract(copy)
   target.write_bytes(original)
   policy=copy/'tools/workstation_ae350_pcm_cdc_policy.json';policy.write_bytes(policy.read_bytes()+b'\n')
   with self.assertRaisesRegex(ValueError,'reviewed policy bytes changed'):source_contract(copy)
 def test_synthetic_apb_equations_and_all_bits(self):
  n=PcmNetlist(apb_fixture(),'top');r=audit_apb(n,Graph(n),dict(apb='pclk',compute='audio_clk'))
  self.assertEqual([x['width']for x in r['payload_groups']],[49,33]);self.assertEqual(r['register_count'],181)
  self.assertFalse(r['physical_payload_flight_verified'])
 def test_synthetic_apb_mutants_fail_closed(self):
  for kind in ['payload-swap','extra-consumer','multi-driver','sync-bypass','local-reset-bypass','capture-enable','missing-bit','extra-register','foreign-clock-consumer','unsupported-consumer']:
   n=PcmNetlist(apb_fixture(),'top');path=A+'/request_local_0_s0'
   if kind=='payload-swap':n.cells[path]['ports']['D']='request_held_1_q'
   elif kind=='sync-bypass':n.cells[A+'/req_sync_s0']['ports']['D']='request_toggle_q'
   elif kind=='local-reset-bypass':n.cells[path]['ports']['CLEAR']="1'b0"
   elif kind=='capture-enable':n.cells[path]['ports']['CE']="1'b1"
   elif kind=='missing-bit':del n.cells[path]
   else:
    p='probe_s0'if kind in ('extra-consumer','foreign-clock-consumer','unsupported-consumer')else A+'/probe_s0'
    n.cells[p]=dict(kind='DFFCE',ports=dict(Q='probe',D='request_held_0_q'if kind in ('extra-consumer','foreign-clock-consumer')else "1'b0",CE="1'b1",CLEAR="1'b0",CLK='audio_clk'),parameters={})
    n.scopes[p]=A
    if kind=='multi-driver':n.cells[p]['ports']['Q']='request_held_0_q'
    if kind=='foreign-clock-consumer':n.cells[p]['ports']['CLK']='unrelated_clock'
    if kind=='unsupported-consumer':n.cells[p]=dict(kind='UNKNOWN_CELL',ports=dict(I='request_held_0_q',O='probe'),parameters={})
   with self.subTest(kind=kind),self.assertRaises(ValueError):audit_apb(n,Graph(n),dict(apb='pclk',compute='audio_clk'))

if __name__=='__main__':unittest.main()
