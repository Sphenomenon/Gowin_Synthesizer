"""Exact prepared/native lineage for explicit runtime delay FIFO storage."""
from pathlib import Path
import hashlib
import json

STRICT_POLICY = 'locked_native_v1'
STORAGE_POLICY = 'native_delay_fifo_block_ram_v1'
SOURCE = 'rtl/audio/workstation_runtime_stereo_effects.sv'
PROVENANCE = 'rtl/audio/workstation_runtime_stereo_effects.provenance.json'
ADAPTATION = 'rtl/audio/workstation_runtime_stereo_effects.delay_fifo_storage.json'
PROVENANCE_SHA256 = '5af689e1adc920524e83d0ae9da87382a75a6bc2868c08fc246abb47814df68c'
ADAPTATION_SHA256 = '5590b0082117f53247f5d30236d5547ac2f358ee66e7b874c3ce6199ec13fe51'
FIFO = 'rtl/music/music_async_fifo.sv'
FIFO_SHA256 = 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792'
REFERENCE = 'rtl/workstation/gw138k_push_workstation_top.v'
# The reviewed native RTC/PCM composition and explicit ROM128 selector change
# this maintained reference. Original effects provenance/adaptation bytes and
# both non-runtime FIFO selectors remain locked; no effects lineage is rebased.
REFERENCE_SHA256 = 'ba87c7be7e1379dcdcb4d157625628a254645c608b089d00ba2491a941b4a213'
PREPARED_SOURCE = 'rtl/audio/stereo_effects.sv'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def restore_native(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Remove only the separately authorized storage statements, exactly."""
    if policy not in (STRICT_POLICY, STORAGE_POLICY):
        raise ValueError('Unknown delay storage provenance policy')
    if sha(provenance) != PROVENANCE_SHA256:
        raise ValueError('Original effects provenance bytes changed')
    original = json.loads(provenance)
    current = source.decode()
    if policy == STORAGE_POLICY:
        if adaptation is None or sha(adaptation) != ADAPTATION_SHA256:
            raise ValueError('Delay storage adaptation changed or missing')
        bridge = json.loads(adaptation)
        if (bridge['schema'] != 1 or bridge['policy'] != policy or bridge['source'] != SOURCE or
                bridge['original_provenance'] != PROVENANCE or
                bridge['original_provenance_sha256'] != sha(provenance) or
                bridge['parent_source_sha256'] != original['native_sha256'] or
                bridge['current_source_sha256'] != sha(source) or len(bridge['exact_changes']) != 1):
            raise ValueError('Delay storage source identity changed')
        edit = bridge['exact_changes'][0]
        if edit['count'] != 1 or not edit['after'] or current.count(edit['after']) != 1:
            raise ValueError('Delay storage reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
        if (not edit['before'] or current.count(edit['before']) != 1 or
                current.replace(edit['before'], edit['after']) != source.decode()):
            raise ValueError('Delay storage exact round trip changed bytes')
    elif adaptation is not None:
        raise ValueError('Delay storage adaptation needs explicit policy')
    if sha(current.encode()) != original['native_sha256']:
        raise ValueError('Original native effects identity changed')
    return current


def verify(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Restore the previous native bytes, then their unchanged prepared slice."""
    current = restore_native(source, provenance, policy, adaptation)
    info = json.loads(provenance)
    for edit in reversed(info['forward_edits']):
        if not edit['after'] or current.count(edit['after']) != edit['count']:
            raise ValueError('Original effects reverse provenance anchor drift')
        current = current.replace(edit['after'], edit['before'])
    if sha(current.encode()) != info['prepared_sha256']:
        raise ValueError('Original prepared effects identity changed')
    return current, dict(policy=policy, source=SOURCE, current_source_sha256=sha(source),
        original_native_sha256=info['native_sha256'], original_provenance_sha256=sha(provenance),
        adaptation_sha256=sha(adaptation) if adaptation is not None else None,
        original_prepared_source_sha256=info['prepared_source_sha256'], exact_prepared_sha256=sha(current.encode()),
        original_provenance_unchanged=True, FIFO_source=FIFO, FIFO_sha256=FIFO_SHA256,
        RAM_STYLE='block_ram' if policy == STORAGE_POLICY else 'distributed_ram',
        storage_instances=['delay_stage.u_write_fifo', 'delay_stage.u_read_fifo'],
        large_bank_attribute_condition='WIDTH == 65 && ADDRESS_BITS >= 8',
        default_WIDTH=65, default_ADDRESS_BITS=9, default_depth_per_fifo=512,
        small_head_branch_unchanged=True, added_clock_latency=0,
        physical_ram_mapping_verified=False, physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    """Select only maintained native profiles and recheck both source chains."""
    root = Path(root)
    source, provenance, adaptation = ((root / p).read_bytes() for p in (SOURCE, PROVENANCE, ADAPTATION))
    prepared, evidence = verify(source, provenance, STORAGE_POLICY, adaptation)
    if sha((root / FIFO).read_bytes()) != FIFO_SHA256:
        raise ValueError('Delay FIFO source bytes changed')
    reference = (root / REFERENCE).read_bytes()
    if sha(reference) != REFERENCE_SHA256:
        raise ValueError('Maintained non-runtime storage policy reference changed')
    bridge = json.loads(adaptation)
    for selector in bridge['policy_reference']['selectors']:
        if reference.decode().count('defparam ' + selector + '="block_ram";') != 1:
            raise ValueError('Maintained non-runtime storage policy selector changed')
    # This is the original locked prepared composition, not an assertion that
    # accepted_full83 used block RAM. The mapping policy is a later source choice.
    info = json.loads(provenance)
    payload = (root / PREPARED_SOURCE).read_bytes()
    if sha(payload) != info['prepared_source_sha256']:
        raise ValueError('Original locked effects source changed')
    text = payload.decode()
    begin = text.index('module stereo_effects #(')
    end = text.index('endmodule', begin) + len('endmodule')
    if text[begin:end] != prepared:
        raise ValueError('Exact original prepared effects slice changed')
    evidence.update(original_locked_prepared_slice_verified=True,
        storage_policy_reference=REFERENCE, storage_policy_reference_sha256=sha(reference),
        original_prepared_source=PREPARED_SOURCE, original_prepared_identity=info['prepared_source_identity'],
        accepted_baseline_storage_selection_inherited=False)
    return evidence
