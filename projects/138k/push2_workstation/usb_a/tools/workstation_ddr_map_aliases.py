"""Opt-in equal DDR include aliases; preserve historical profiles and allocations."""
from pathlib import Path
from tools.workstation_recording_policy import address_map_inputs, digest, macros

POLICY = 'native_ddr_authority_equal_include_aliases_v1'
KEY = 'ddr_map_alias_policy'
TOOL = 'tools/workstation_ddr_map_aliases.py'
SOURCE = 'rtl/ddr_address_map.vh'
ALIAS = 'src/memory/ddr_address_map.vh'
DEPENDENCIES = (TOOL, SOURCE, 'tools/workstation_recording_policy.py')


def configured(configuration):
    value = configuration.get(KEY)
    if value is not None and value != POLICY:
        raise ValueError('unknown DDR include alias policy')
    return value == POLICY


def install(root, stage):
    original, selected = address_map_inputs(root)
    stage = Path(stage)
    if (stage / ALIAS).read_bytes() != original:
        raise ValueError('DDR include alias parent changed')
    if (stage / SOURCE).read_bytes() != selected:
        raise ValueError('DDR include alias authority changed')
    (stage / ALIAS).write_bytes(selected)
    result = dict(policy=POLICY, source=SOURCE, alias=ALIAS,
                  parent_sha256=digest(original), selected_sha256=digest(selected),
                  preserved_parent_macros=len(macros(original)),
                  existing_allocations_preserved=True, equal_include_bytes=True)
    verify_staged(stage, result, authority_sha256=digest(selected))
    return result


def verify_staged(stage, evidence, *, authority_sha256):
    if not isinstance(evidence, dict):
        raise ValueError('DDR include alias evidence missing')
    expected = dict(policy=POLICY, source=SOURCE, alias=ALIAS,
                    parent_sha256=evidence.get('parent_sha256'),
                    selected_sha256=authority_sha256,
                    preserved_parent_macros=evidence.get('preserved_parent_macros'),
                    existing_allocations_preserved=True, equal_include_bytes=True)
    if (evidence != expected or not isinstance(evidence['parent_sha256'], str) or
            len(evidence['parent_sha256']) != 64 or
            type(evidence['preserved_parent_macros']) is not int or
            evidence['preserved_parent_macros'] < 1):
        raise ValueError('DDR include alias evidence changed')
    for relative in (SOURCE, ALIAS):
        if digest((Path(stage) / relative).read_bytes()) != authority_sha256:
            raise ValueError('DDR include alias bytes changed: ' + relative)


def verify(root, stage, evidence):
    original, selected = address_map_inputs(root)
    verify_staged(stage, evidence, authority_sha256=digest(selected))
    if (evidence['parent_sha256'] != digest(original) or
            evidence['preserved_parent_macros'] != len(macros(original))):
        raise ValueError('DDR include alias original allocations changed')
