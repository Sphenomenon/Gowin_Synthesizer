"""Explicit task3 M SD contact selection; inherited board input stays frozen."""
from pathlib import Path
import copy
import hashlib
import json

POLICY = 'task3_m_actual_sd_contacts_v1'
SOURCE = 'boards/custom_138k/task3_tf_sd_contacts.json'
TOOL = 'tools/workstation_task3_tf_contacts.py'
BASE_PROFILE = 'boards/custom_138k/pinout.json'
DEPENDENCIES = (SOURCE, TOOL, BASE_PROFILE)
CONTACTS = {
    'sd_miso': ('U16.7', 'V15', 'U16.1', 'AA15', 'input'),
    'sd_mosi': ('U16.3', 'Y16', 'U16.8', 'W14', 'output'),
    'sd_sck': ('U16.5', 'W15', 'U16.7', 'V15', 'output'),
    'sd_cs_n': ('U16.2', 'AB15', 'U16.5', 'W15', 'output'),
}


def require(ok, message):
    if not ok:
        raise ValueError('task3 TF contacts: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(root, profile):
    root = Path(root)
    data = json.loads((root / SOURCE).read_text())
    require(data.get('schema') == 1 and data.get('policy') == POLICY and
            data.get('hardware_verified') is False, 'descriptor policy/scope changed')
    require(data['carrier_filename'] == profile['sources']['carrier']['filename'] and
            data['carrier_sha256'] == profile['sources']['carrier']['sha256'],
            'carrier identity differs from inherited board source')
    require(set(data['ports']) == set(CONTACTS) and profile['tf_spi'] ==
            {port: row[2] for port, row in CONTACTS.items()}, 'contact inventory drift')
    require(data.get('unused_data_nodes') == ['U16.1', 'U16.8'] and
            profile['reserved_nodes'][:2] == ['U16.2', 'U16.3'] and
            all(not p.startswith('U16.') for p in profile['reserved_nodes'][2:]),
            'SD unused contact reservation drift')
    for port, (node, ball, old_node, old_ball, direction) in CONTACTS.items():
        require(data['ports'][port] == dict(node=node, ball=ball, inherited_ball=old_ball),
                'reviewed SD contact drift: ' + port)
    return dict(policy=POLICY, descriptor=SOURCE, descriptor_sha256=sha(root / SOURCE),
        tool=TOOL, tool_sha256=sha(root / TOOL),
        parent_pinout_identity=profile['identity'],
        carrier_sha256=data['carrier_sha256'],
        contacts={port: dict(node=node, ball=ball, inherited_node=old_node,
            inherited_ball=old_ball, direction=direction)
            for port, (node, ball, old_node, old_ball, direction) in CONTACTS.items()},
        carrier_supply_network='+3V3', carrier_ground_nodes=['U16.6', 'U16.9', 'U16.10'],
        selected_unused_data_nodes=['U16.1', 'U16.8'],
        schematic_symbol_evidence=data['symbol_evidence'],
        actual_board_measured=False, bank_VCCIO_measured=False,
        TF_clock_or_timing_budget_changed=False, hardware_verified=False)


def select_profile(root, profile, netlists, policy):
    require(policy == POLICY, 'unknown selection policy')
    proof = receipt(root, profile)
    carrier = netlists['carrier']
    for port, (node, ball, old_node, old_ball, _) in CONTACTS.items():
        require(carrier.ball(node, 5) == ball and carrier.ball(old_node, 5) == old_ball,
                'actual carrier endpoint drift: ' + port)
    require(carrier.network('U16.4') == '+3V3' and
            all(carrier.network(p) == 'GND' for p in proof['carrier_ground_nodes']),
            'actual SD supply/shell wiring drift')
    selected = copy.deepcopy(profile)
    selected['tf_spi'] = {port: row[0] for port, row in CONTACTS.items()}
    selected['reserved_nodes'] = ['U16.1', 'U16.8', *profile['reserved_nodes'][2:]]
    selected['identity'] += '-task3-sd-contacts-v1'
    return selected, proof


def verify_plan(root, plan, policy):
    if policy is None:
        require('tf_contact_selection' not in plan, 'unselected correction in pinout')
        return
    require(policy == POLICY, 'unknown prepared policy')
    profile = json.loads((Path(root) / BASE_PROFILE).read_text())
    expected = receipt(root, profile)
    selected_identity = profile['identity'] + '-task3-sd-contacts-v1'
    # The native composition appends its three independently owned pad plans.
    identities = (selected_identity,
                  selected_identity + '_native_ble_v1_workstation_peripherals_v1_model_flash_v1')
    require(plan.get('tf_contact_selection') == expected and plan['identity'] in identities,
            'prepared correction receipt/identity drift')
    require(plan['source_inputs']['carrier']['sha256'] == expected['carrier_sha256'],
            'prepared carrier input drift')
    require(all(plan.get('recipe_inputs', {}).get(p) == sha(Path(root) / p) for p in DEPENDENCIES),
            'prepared contact recipe inputs changed')
    for port, (_, ball, _, _, _) in CONTACTS.items():
        require(plan['ports'].get(port) == dict(balls=[ball], origin='tf_card_spi'),
                'prepared SD contact changed: ' + port)
    require({p: ball for p, ball in plan['reserved_balls'].items() if p.startswith('U16.')} ==
            {'U16.1': 'AA15', 'U16.8': 'W14'}, 'prepared unused SD contacts changed')
    balls = [ball for entry in plan['ports'].values() for ball in entry['balls']]
    require(len(balls) == len(set(balls)), 'selected SD contacts collide with another IO')
    require(not {'AA15', 'W14'}.intersection(balls), 'unused SD data contact is driven')
