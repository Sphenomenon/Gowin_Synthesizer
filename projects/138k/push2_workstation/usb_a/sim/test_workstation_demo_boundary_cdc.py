#!/usr/bin/env python3
"""Selected actual-netlist CDC/reset mutations; no EDA or board operation."""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_pcm_cdc import Graph, TOP
from tools.workstation_demo_boundary_cdc import (POLICY, TOOL, AUDIT_SOURCES, PROPOSAL, D, E, U, F, R,
    FAULTS, audit, netlist, proposed_constraints, select_demo_boundary,
    verify_demo_boundary, validate_sdc, verify_wptr_lsb_nextq, complete_closure)

def actual_mutations(n, mapping, text):
 result_audit=audit(n,mapping=mapping)
 result=[];g=Graph(n);reg=lambda s,t,b=None:g.register(s,t,b)
 def change(name,p,key,val,param=False):
  target=n.cells[p]['parameters' if param else 'ports'];had=key in target;old=target.get(key);target[key]=val
  try:
   try:audit(n,mapping=mapping)
   except ValueError as e:result.append(dict(name=name,kind='parsed_actual_netlist_object_mutant',rejected=True,reason=str(e)))
   else:raise RuntimeError('mutant accepted '+name)
  finally:
   if had:target[key]=old
   else:del target[key]
 # Verify the exact mapped LSB function, including mutants whose complete
 # fault closure still matches a reviewed mapping or remains byte-identical.
 wptr=reg(D,'wptr',0)
 def guarded(name,p,updates,expected,param=False,preserve_fault_closure=False):
  target=n.cells[p]['parameters' if param else 'ports'];saved=copy.deepcopy(target)
  target.update(updates)
  try:
   if preserve_fault_closure:
    mutated_graph=Graph(n)
    for stem in FAULTS:
     actual=complete_closure(n,mutated_graph,[mutated_graph.register(D,stem)])
     original=result_audit['fault_source_closures'][stem]
     for field in ('ff_endpoints','primitive_endpoints','top_output_endpoints'):
      if actual[field]!=original[field]:raise RuntimeError('functional mutant altered closure '+name)
   try:audit(n,mapping=mapping)
   except ValueError as e:
    if expected not in str(e):raise RuntimeError('wrong specific function rejection '+name+': '+str(e))
    result.append(dict(name=name,kind='parsed_actual_netlist_function_mutant',rejected=True,
      reason=str(e),fault_closure_preserved=preserve_fault_closure))
   else:raise RuntimeError('function mutant accepted '+name)
  finally:target.clear();target.update(saved)
 ports=n.cells[wptr]['ports']
 guarded('wptr0 actual D/CE interchange',wptr,{'D':ports['CE'],'CE':ports['D']},'next-Q equation drift')
 guarded('wptr0 functional reset always asserted',wptr,
  {'CLEAR':n.cells[reg(D,'watchdog_fault')]['ports']['D']},'fault wptr LSB',preserve_fault_closure=True)
 guarded('wptr0 INIT changed',wptr,{'INIT':"1'b1"},'clock/INIT',param=True,preserve_fault_closure=True)
 gate=g.drivers[n.pin(wptr,'D')][0][0];literal=n.cells[gate]['parameters']['INIT']
 encoded=re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)",literal)
 if encoded is None:raise RuntimeError('actual wptr D LUT INIT encoding')
 flipped=str(int(encoded[1]))+"'h"+format(((1<<int(encoded[1]))-1)^int(encoded[2],16),'x')
 guarded('wptr0 actual D LUT complemented',gate,{'INIT':flipped},'next-Q equation drift',True,True)
 # Remove each source's effective veto in an actual LUT while retaining all
 # named ports and therefore the complete structural consumer inventories.
 todo=[n.pin(wptr,pin) for pin in ('D','CE')];seen=set();gates=[]
 while todo:
  net=todo.pop()
  if net in seen or net in g.high|g.low:continue
  seen.add(net);drivers=g.drivers[net]
  if len(drivers)!=1:raise RuntimeError('actual wptr driver ambiguity')
  cell_path,output=drivers[0]
  if cell_path in g.regs:continue
  kind=n.cells[cell_path]['kind']
  pins=['I'] if kind=='INV' else ['I'+str(i) for i in range(int(kind[3:]))]
  inputs=[n.pin(cell_path,pin) for pin in pins];todo.extend(inputs)
  if kind!='INV':gates.append((cell_path,inputs))
 for stem in FAULTS:
  source=n.pin(reg(D,stem),'Q');selected=None
  for cell_path,inputs in gates:
   if source not in inputs:continue
   params=n.cells[cell_path]['parameters'];original=params['INIT']
   encoded=re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)",original)
   if encoded is None:raise RuntimeError('actual fault veto LUT INIT encoding')
   bit=inputs.index(source);truth=int(encoded[2],16)
   cofactor=sum(((truth>>(vector&~(1<<bit)))&1)<<vector for vector in range(1<<len(inputs)))
   changed=str(int(encoded[1]))+"'h"+format(cofactor,'x')
   if changed==original:continue
   params['INIT']=changed
   try:
    try:verify_wptr_lsb_nextq(n,Graph(n))
    except ValueError as e:
     if 'next-Q equation drift' not in str(e):raise
     selected=(cell_path,changed)
   finally:params['INIT']=original
   if selected:break
  if selected is None:raise RuntimeError('no effective actual fault-veto LUT for '+stem)
  guarded('wptr0 '+stem+' effective veto removed',selected[0],{'INIT':selected[1]},
   'next-Q equation drift',True,True)
 p=reg(D,'state',1);ports=n.cells[p]['ports']
 guarded('unreviewed state1 D/CE interchange',p,{'D':ports['CE'],'CE':ports['D']},'all FF consumers drift')
 for stem in FAULTS:
  change(stem+' wrong clock',reg(D,stem),'CLK',n.cells[reg(E,'dma_fault_meta')]['ports']['CLK'])
  change(stem+' no longer sticky',reg(D,stem),'D',n.cells[reg(D,stem)]['ports']['CLEAR'])
 change('fault receiver second bypass',reg(E,'dma_fault_sync'),'D',n.cells[reg(E,'dma_fault_meta')]['ports']['D'])
 change('fault receiver second gated',reg(E,'dma_fault_sync'),'CE',n.cells[reg(E,'dma_fault_meta')]['ports']['D'])
 change('fault receiver reset mismatch',reg(E,'dma_fault_sync'),'CLEAR',n.cells[reg(E,'dma_fault_meta')]['ports']['CE'])
 change('fault receiver INIT changed',reg(E,'dma_fault_meta'),'INIT',"1'b1",True)
 change('queue source wrong clock',reg(U,'queue_release',5),'CLK',n.cells[reg(R,'release_q',0)]['ports']['CLK'])
 change('queue six-edge bypass',reg(U,'queue_release',5),'D',n.cells[reg(U,'queue_release',2)]['ports']['Q'])
 change('FIFO release first D not one',reg(R,'release_q',0),'D',n.cells[reg(R,'release_q',0)]['ports']['CLEAR'])
 change('FIFO release second bypass',reg(R,'release_q',1),'D',n.cells[reg(R,'release_q',0)]['ports']['D'])
 change('FIFO release second wrong clock',reg(R,'release_q',1),'CLK',n.cells[reg(U,'queue_release',5)]['ports']['CLK'])
 change('FIFO release second reset mismatch',reg(R,'release_q',1),'CLEAR',n.cells[reg(R,'release_q',1)]['ports']['CE'])
 change('functional pointer reset bypass',reg(F,'produce_w_bin',0),'CLEAR',n.cells[reg(R,'release_q',1)]['ports']['CLEAR'])
 # Mutate the exact three-fault OR, not only the worst source path.
 gate=g.drivers[n.pin(reg(E,'dma_fault_meta'),'D')][0][0]
 change('three-fault OR truth changed',gate,'INIT',"8'h00",True)
 for label,source,kind in [('fault first extra FF',reg(E,'dma_fault_meta'),'DFFCE'),('fault source extra memory FF',reg(D,'peer_fault'),'DFFCE'),('fault source opaque extra',reg(D,'protocol_fault'),'UNREVIEWED_RAM'),('FIFO first release extra FF',reg(R,'release_q',0),'DFFCE'),('queue sixth extra FF',reg(U,'queue_release',5),'DFFCE')]:
  scope=n.scopes[source];p=(scope+'/' if scope else '')+'bad_boundary_consumer_s0';template=copy.deepcopy(n.cells[source]);template['ports']['D']=template['ports']['Q'];template['ports']['Q']='bad_boundary_Q';template['kind']=kind
  if kind!='DFFCE':template['ports']={'IN':template['ports']['D'],'CLK':template['ports']['CLK']}
  n.cells[p]=template;n.scopes[p]=scope
  try:
   try:audit(n,mapping=mapping)
   except ValueError as e:result.append(dict(name=label,kind='parsed_actual_netlist_object_mutant',rejected=True,reason=str(e)))
   else:raise RuntimeError('extra consumer mutant accepted '+label)
  finally:del n.cells[p];del n.scopes[p]
 sdc_mutants={'missing peer source':PROPOSAL.replace(D+'/peer_fault_s*/Q',''), 'broad source':PROPOSAL.replace(D+'/watchdog_fault_s*/Q',D+'/*fault*/Q'),
  'fault later D waived':PROPOSAL.replace(E+'/dma_fault_meta_s*/D',E+'/dma_fault_sync_s*/D'),
  'functional pointer CLEAR waived':PROPOSAL.replace(R+'/release_q_1_s*/CLEAR',F+'/produce_w_bin_0_s*/CLEAR'),
  'wrong queue source':PROPOSAL.replace(U+'/queue_release_5_s*/Q',U+'/queue_release_4_s*/Q'),
  'whole clock waiver':PROPOSAL+'set_false_path -from [get_clocks {ddr_ui100}] -to [get_clocks {audio_76m8}]\n',
  'weaker later bound':PROPOSAL.replace('2.000','3.000'), 'only first CLEAR':PROPOSAL.replace(' '+R+'/release_q_1_s*/CLEAR',''),
  'extra indented functional reset waiver':PROPOSAL+'  set_false_path -to [get_pins {'+F+'/produce_w_gry_0_s*/CLEAR}]\n'}
 for name,sdc in sdc_mutants.items():
  try:validate_sdc(sdc,n,result_audit)
  except ValueError as e:result.append(dict(name=name,kind='proposed_SDC_text_mutant',rejected=True,reason=str(e)))
  else:raise RuntimeError('SDC mutant accepted '+name)
 # Full original-byte lexical mutations in each actual netlist, at the new
 # release FF module/flat instance, verify duplicate/unparsed rejection.
 p=reg(R,'release_q',0);scope=n.scopes[p];kind=n.frames[scope]['kind'];label=p[len(scope)+1:] if scope else p
 module=re.search(r'^module\s+\\?'+re.escape(kind)+r'\s*\((.*?)^endmodule\b',text,re.M|re.S)
 inst=re.search(r'^[ \t]*DFFCE\s+\\?'+re.escape(label)+r'\s*\((.*?)\);',module[1],re.M|re.S)
 start=module.start(1)+inst.start(1);end=module.start(1)+inst.end(1);body=text[start:end];port=re.search(r'\.D\s*\(\s*([^()]*?)\s*\)',body)
 for name,b in [('duplicate named D',body[:port.end()]+',.D('+port[1]+')'+body[port.end():]),('nested unparsed binding',body+',.BAD(nested(net))')]:
  altered=text[:start]+b+text[end:]
  try:netlist(altered,mapping=mapping)
  except ValueError as e:result.append(dict(name=name,kind='original_VG_or_VO_byte_mutant',rejected=True,reason=str(e),mutant_sha256=hashlib.sha256(altered.encode()).hexdigest()))
  else:raise RuntimeError('lexical mutant accepted '+name)
 return result


class Selection(unittest.TestCase):
    def test_exact_four_scope_limited_commands(self):
        lines = proposed_constraints().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(sum(line.startswith("set_false_path ") for line in lines), 2)
        self.assertEqual(sum(line.startswith("set_max_delay 2.000 ") for line in lines), 2)
        self.assertNotIn("midi_bytes", proposed_constraints())
        self.assertNotIn("get_clocks", proposed_constraints())
        self.assertNotIn("produce_w_bin", proposed_constraints())

    def test_missing_metadata_needs_no_new_file_and_no_new_line(self):
        absent = Path("/nonexistent/sealed-legacy-project")
        self.assertEqual(verify_demo_boundary(absent, "# original\n", "M", None)["mode"],
                         "sealed_legacy_without_demo_boundary_additions")
        for line in proposed_constraints().splitlines():
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, "lack explicit selection"):
                verify_demo_boundary(absent, line + "\n", "M", None)

    def test_selected_source_and_metadata_fail_on_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            source = stage / TOOL
            source.parent.mkdir(parents=True)
            source.write_bytes((ROOT / TOOL).read_bytes())
            for role in ("M", "W"):
                selected, evidence = select_demo_boundary(stage, "# original\n", role)
                self.assertEqual(evidence["policy"], POLICY)
                self.assertTrue(verify_demo_boundary(stage, selected, role, evidence)["installed_lines_verified"])
                for key, value in (("role", "W" if role == "M" else "M"), ("policy", "forged"),
                                   ("source", "another.py"), ("added_lines", [])):
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        verify_demo_boundary(stage, selected, role, dict(evidence, **{key: value}))
                for line in proposed_constraints().splitlines():
                    with self.subTest(missing=line), self.assertRaisesRegex(ValueError, "absent or duplicated"):
                        verify_demo_boundary(stage, selected.replace(line + "\n", "", 1), role, evidence)
                    with self.subTest(duplicate=line), self.assertRaisesRegex(ValueError, "absent or duplicated"):
                        verify_demo_boundary(stage, selected + line + "\n", role, evidence)
                with self.assertRaisesRegex(ValueError, "already installed"):
                    select_demo_boundary(stage, selected, role)
            source.write_text("changed")
            with self.assertRaisesRegex(ValueError, "source identity changed"):
                verify_demo_boundary(stage, selected, role, evidence)


class ActualBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("GW138K_DEMO_BOUNDARY_NETLIST")
        if not path:
            raise unittest.SkipTest("explicit real GW138K_DEMO_BOUNDARY_NETLIST required")
        cls.path = Path(path)
        cls.mapping = os.environ.get("GW138K_DEMO_BOUNDARY_MAPPING", "synthesis")
        cls.original = cls.path.read_bytes()
        cls.text = cls.original.decode()
        cls.n = netlist(cls.text, mapping=cls.mapping)
        cls.rows = []
        cls.expected_role = os.environ.get("GW138K_DEMO_BOUNDARY_ROLE")
        cls.baseline = None
        cls.source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in AUDIT_SOURCES}

    @classmethod
    def tearDownClass(cls):
        if cls.path.read_bytes() != cls.original:
            raise AssertionError("original candidate netlist bytes changed")
        if cls.source_hashes != {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in AUDIT_SOURCES}:
            raise AssertionError("auditor inputs changed during actual-netlist test")
        output = os.environ.get("GW138K_DEMO_BOUNDARY_EVIDENCE")
        if output:
            Path(output).write_text(json.dumps(dict(mapping=cls.mapping,
                netlist=str(cls.path), netlist_sha256=hashlib.sha256(cls.original).hexdigest(),
                audit_sources_sha256=cls.source_hashes, baseline=cls.baseline,
                mutations=cls.rows, all_rejected=all(row["rejected"] for row in cls.rows),
                original_netlist_unchanged=True, physical_cdc_accepted=False), indent=2) + "\n")

    def test_actual_fault_and_fifo_source_and_all_consumer_inventories(self):
        result = audit(self.n, mapping=self.mapping)
        candidate = os.environ.get("GW138K_DEMO_BOUNDARY_SDC")
        sdc = Path(candidate).read_text() if candidate else ""
        if not any(line in sdc.splitlines() for line in proposed_constraints().splitlines()):
            sdc += "\n" + proposed_constraints()
        checked = validate_sdc(sdc, self.n, result)
        self.assertEqual(len(result["source_fault_registers"]), 3)
        self.assertEqual(len(result["fifo_write_pointers"]), 13)
        self.assertTrue(checked["functional_recovery_removal_exceptions_absent"])
        self.assertTrue(checked["whole_boundary_clock_exceptions_absent"])
        if self.expected_role is not None:
            self.assertEqual(result["inventory_role"], self.expected_role)
        self.__class__.baseline = dict(passed=True, inventory_role=result["inventory_role"],
            fault_ff_consumers=len(result["fault_source_closures"]["watchdog_fault"]["ff_endpoints"]),
            fault_ram_consumers=len(result["fault_source_closures"]["watchdog_fault"]["primitive_endpoints"]),
            queue_ff_consumers=len(result["queue_source_closure"]["ff_endpoints"]),
            queue_ram_consumers=len(result["queue_source_closure"]["primitive_endpoints"]))

    def test_actual_clock_CE_reset_sticky_bypass_and_extra_consumers(self):
        self.rows.extend(actual_mutations(self.n, self.mapping, self.text))

    def test_complete_queue_role_binding_independent_of_DMA_mapping(self):
        result = audit(self.n, mapping=self.mapping)
        selected = self.expected_role or result["inventory_role"]
        checked = audit(self.n, mapping=self.mapping, expected_role=selected)
        self.assertEqual(checked["inventory_role"], selected)
        self.assertIn(checked["fault_inventory_endpoints"], (663, 664))
        wrong = "M" if selected == "W" else "W"
        with self.assertRaisesRegex(ValueError, "complete queue inventory does not match selected DEMO role"):
            audit(self.n, mapping=self.mapping, expected_role=wrong)
        self.rows.append(dict(case="opposite selected DEMO role", selected=wrong,
            actual_queue_role=selected, fault_inventory_endpoints=checked["fault_inventory_endpoints"],
            rejected=True))

    def test_extra_top_output_and_weaker_additional_bound_rejected(self):
        g = Graph(self.n)
        for scope, stem in ((D, "peer_fault"), (E, "dma_fault_meta")):
            source = g.register(scope, stem)
            self.n.directions[TOP]["bad_export"] = "output"
            self.n.buffers[TOP]["bad_export"] = self.n.pin(source, "Q")
            try:
                with self.assertRaisesRegex(ValueError, "top output consumer"):
                    audit(self.n, mapping=self.mapping)
            finally:
                del self.n.directions[TOP]["bad_export"]
                del self.n.buffers[TOP]["bad_export"]
            self.rows.append(dict(case="extra exported consumer " + scope, rejected=True))
        result = audit(self.n, mapping=self.mapping)
        for prefix in ("", " ", "\t"):
            for extra in (
                f"set_false_path -to [get_pins {{{E}/dma_fault_sync_s*/D}}]",
                f"set_false_path -to [get_pins {{{F}/produce_w_bin_0_s*/CLEAR}}]",
                f"set_max_delay 100.000 -from [get_pins {{{E}/dma_fault_meta_s*/Q}}] -to [get_pins {{{E}/dma_fault_sync_s*/D}}]",
                "set_max_delay 100.000 -to [get_clocks {audio_76m8}]",
                "set_max_delay 100.000 -from [get_clocks {audio_76m8}]",
                f"set_min_delay -100.000 -to [get_pins {{{F}/produce_w_bin_0_s*/CLEAR}}]",
                f"set_multicycle_path 100 -to [get_pins {{{E}/dma_fault_sync_s*/D}}]",
                "set_clock_groups -asynchronous -group [get_clocks {*}] -group [get_clocks {other}]",
            ):
                with self.subTest(extra=extra, prefix=prefix), self.assertRaises(ValueError):
                    validate_sdc(proposed_constraints() + prefix + extra + "\n", self.n, result)
                self.rows.append(dict(case="additional protected timing override", prefix=prefix, rejected=True))


if __name__ == "__main__":
    unittest.main()
