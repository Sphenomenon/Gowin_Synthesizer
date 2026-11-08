"""Select W diagnostic fault cofactors; preserve exact historical inverses.

The probes are never acceptance or response authorities. Their equality with
the real observations when transport_fault=0 is a compositional obligation.
"""
from pathlib import Path
import hashlib
import json

KEY = 'native_fault_cofactor_policy'
POLICY = 'task3_W_native_fault_diagnostic_cofactor_v1'
SOURCE = 'rtl/memory/workstation_ble_raw_ddr_store.sv'
MANIFEST = 'rtl/memory/workstation_native_fault_cofactor_v1.adaptation.json'
TOOL = 'tools/workstation_native_fault_cofactor.py'
MANIFEST_SHA256 = '6364b49195640070e6fd732c2a522307f88cdb21287fb6acb21ab81bf102d053'
DEFAULT = 'parameter bit NATIVE_FAULT_COFACTOR_ENABLE=0'
SELECTED = 'parameter bit NATIVE_FAULT_COFACTOR_ENABLE=1'
OLDER = ('PIPELINED_COMPLETION_ENABLE', 'TERMINAL_COFACTOR_ENABLE',
         'TUPLE_COFACTOR_ENABLE', 'PACK_COFACTOR_ENABLE')


def digest(raw):
    return hashlib.sha256(raw.encode() if isinstance(raw, str) else raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('native fault cofactor: ' + message)


def manifest():
    raw = (Path(__file__).resolve().parents[1] / MANIFEST).read_bytes()
    require(digest(raw) == MANIFEST_SHA256, 'manifest drift')
    data = json.loads(raw)
    require(data['policy'] == POLICY and data['schema'] == 1, 'manifest policy drift')
    return data


def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED) == 1 and DEFAULT not in text, 'duplicate selection')
        text = text.replace(SELECTED, DEFAULT, 1)
    return text


def restore(source, text):
    """Exact inverse, normalizing independent raw selections for lineage only."""
    row = manifest()['sources'][source]
    if source == SOURCE:
        text = unselect(text)
        for stem in OLDER:
            selected, default = 'parameter bit ' + stem + '=1', 'parameter bit ' + stem + '=0'
            require(text.count(selected) + text.count(default) == 1, 'older selection drift')
            text = text.replace(selected, default, 1)
    if digest(text) == row['parent_sha256']:
        return text
    require(digest(text) == row['native_sha256'], 'source drift: ' + source)
    for edit in reversed(row['edits']):
        require(text.count(edit['after']) == edit['count'], 'inverse anchor drift: ' + source)
        text = text.replace(edit['after'], edit['before'])
    require(digest(text) == row['parent_sha256'], 'parent drift: ' + source)
    return text


def restore_raw(text):
    if 'NATIVE_FAULT_COFACTOR_ENABLE' not in text:
        return text
    return restore(SOURCE, text)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'W' and
                configuration.get('raw_pack_policy') == 'task3_W_raw_pack_fetch_final_fault_selector_v1' and
                configuration.get('raw_terminal_tuple_policy') == 'task3_W_raw_terminal_tuple_final_fault_selector_v1' and
                configuration.get('raw_terminal_policy') == 'task3_W_raw_terminal_fault_final_selector_v1' and
                configuration.get('raw_completion_policy') == 'task3_W_raw_completion_publication_one_memory_edge_v1',
                'requires explicit W pack/publication policies')
    return bool(value)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    hashes = {}
    for source, row in manifest()['sources'].items():
        text = (Path(stage) / source).read_text()
        restore(source, text)
        if source == SOURCE:
            require(text.count(SELECTED) == 1 and DEFAULT not in text, 'selection missing')
        else:
            require(digest(text) == row['native_sha256'], 'native diagnostic wiring missing: ' + source)
        hashes[source] = digest(text)
    return dict(policy=POLICY, source_sha256=hashes, manifest_sha256=MANIFEST_SHA256,
                added_state_bits=0, diagnostic_probes_only=True,
                immediate_transport_fault_preserved=True, procedural_unknown_fallback=True,
                timing_exception_added=False, routed_timing_verified=False, hardware_tested=False)


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    text = path.read_text()
    restore(SOURCE, text)
    require(text.count(DEFAULT) == 1 and SELECTED not in text, 'default missing')
    path.write_text(text.replace(DEFAULT, SELECTED, 1))
    return evidence(stage, configuration)
