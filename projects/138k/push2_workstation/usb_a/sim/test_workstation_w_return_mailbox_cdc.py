#!/usr/bin/env python3
"""W return policy seals and destructive checks on explicitly supplied VG/VO."""
from pathlib import Path
import json, os, sys, tempfile, unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_w_return_mailbox_cdc import (
    TOOL, RAW_STORE_PATH, constraints, selection_metadata, verify_selection, audit)
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_performance_reset import (
    DEMO_TIMING_TOOL, select_demo_timing, verify_demo_timing)


def copy_slice(stage, original=ROOT):
    for relative in (TOOL,RAW_STORE_PATH):
        path=stage/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((ROOT/TOOL if relative==TOOL else original/relative).read_bytes())


class SourceContract(unittest.TestCase):
    def test_helper_and_selected_raw_are_sealed(self):
        with tempfile.TemporaryDirectory(prefix='w-return-contract-') as directory:
            stage=Path(directory);copy_slice(stage)
            evidence=selection_metadata(stage)
            self.assertEqual(verify_selection(stage,evidence),evidence)
            for field,value in (('generation_qualification_endpoints',300),('setup_falsepaths_added',1)):
                with self.subTest(field=field),self.assertRaises(ValueError):
                    verify_selection(stage,dict(evidence,**{field:value}))
            (stage/TOOL).write_text('changed helper\n')
            with self.assertRaises(ValueError):verify_selection(stage,evidence)

    def test_old_M_and_W_policy_do_not_import_new_helper(self):
        with tempfile.TemporaryDirectory(prefix='old-return-no-helper-') as directory:
            stage=Path(directory);path=stage/DEMO_TIMING_TOOL;path.parent.mkdir()
            path.write_bytes((ROOT/DEMO_TIMING_TOOL).read_bytes())
            old=sys.modules.get('tools.workstation_w_return_mailbox_cdc')
            sys.modules['tools.workstation_w_return_mailbox_cdc']=None
            try:
                for role in ('M','W'):
                    sdc,evidence=select_demo_timing(stage,'# unchanged upstream\n',role)
                    self.assertTrue(verify_demo_timing(stage,sdc,role,evidence)['installed_lines_verified'])
            finally:
                sys.modules['tools.workstation_w_return_mailbox_cdc']=old


class ActualMappedMailbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('GW138K_W_RETURN_MAILBOX_NETLIST')
        stage=os.environ.get('GW138K_W_RETURN_MAILBOX_STAGE')
        if not path or not stage:
            raise unittest.SkipTest('explicit actual GW138K_W_RETURN_MAILBOX_NETLIST and _STAGE required')
        cls.path=Path(path);cls.original=Path(stage)
        cls.mapping=os.environ.get('GW138K_W_RETURN_MAILBOX_MAPPING','synthesis')
        cls.text=cls.path.read_text();cls.n=protocol_netlist(cls.text,mapping=cls.mapping)
        cls.sdc=(cls.original/'constraints/custom_138k.sdc').read_text()
        cls.temp=tempfile.TemporaryDirectory(prefix='w-return-actual-stage-slice-')
        cls.stage=Path(cls.temp.name);copy_slice(cls.stage,cls.original)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_graph_and_thirteen_destructive_controls(self):
        # An overlay on this actual graph does not create a prepared v3
        # candidate and never changes the supplied original SDC.
        text=self.sdc
        for line in constraints().splitlines():text=text.replace(line+'\n','')
        result=audit(self.n,stage=self.stage,sdc=text+constraints(),mapping=self.mapping,netlist_text=self.text)
        self.assertEqual(result['actual_real_source_consumer_pairs'],9928)
        self.assertEqual(len(result['actual_generation_qualifier_endpoints']),301)
        self.assertEqual(result['primary_negative_control_count'],13)
        self.assertEqual(result['additional_sdc_negative_control_count'],6)
        self.assertEqual(len(result['negative_controls']),19)
        self.assertTrue(all(row['rejected'] for row in result['negative_controls']))
        self.assertTrue(result['complete_payload_10ns_coverage_verified'])
        self.assertFalse(result['physical_CDC_accepted'])
        self.assertFalse(result['native_response_reachability_invariant_formally_proven'])
        output=os.environ.get('GW138K_W_RETURN_MAILBOX_RESULT')
        if output:Path(output).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')

    def test_actual_graph_rejects_missing_qualification_bounds(self):
        text=self.sdc
        for line in constraints().splitlines():text=text.replace(line+'\n','')
        with self.assertRaisesRegex(ValueError,'qualification bound missing'):
            audit(self.n,stage=self.stage,sdc=text,mapping=self.mapping,netlist_text=self.text)


if __name__=='__main__':unittest.main()
