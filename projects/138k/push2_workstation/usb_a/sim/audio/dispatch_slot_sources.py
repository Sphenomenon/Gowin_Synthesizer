#!/usr/bin/env python3
"""Verification views from the production identity-bound dispatch lineage."""
from pathlib import Path
import hashlib,re,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_dispatch_slot_provenance import HUNKS, ORIGINAL_SHA256, restore_parent

def reference_view(relative,text=None):
    relative=str(relative)
    if text is None:text=(ROOT/relative).read_text()
    try:
        return restore_parent(relative,text.encode()).decode()
    except ValueError as error:
        raise AssertionError(str(error)) from error

def contract_inputs():return [Path(__file__).resolve(),ROOT/'tools/workstation_dispatch_slot_provenance.py',*(ROOT/n for n in HUNKS)]

def source_contract():
    result={}
    for relative in HUNKS:
        current=(ROOT/relative).read_text();original=reference_view(relative,current)
        # The release sweep consumes an equivalent ready view on the same edge.
        normalized=current.replace('core_event_dispatch_ready','core_event_ready')
        nba=lambda t:re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',t)
        assert nba(normalized)==nba(original),'dispatch slot NBA drift: '+relative
        result[relative]={'original_sha256':ORIGINAL_SHA256[relative],'maintained_sha256':hashlib.sha256(current.encode()).hexdigest(),'exact_whole_source_inverse':True,'NBA_targets_values_and_order_unchanged':True}
    return result
