"""Explicit W transmit preference register; payload admission remains immediate.

The native option defaults off. Retire this exact staging adapter when parent
compositions pass the parameter explicitly. Historical endpoint hashes remain
unchanged and are recovered only by the checked inverse adaptation.
"""
from pathlib import Path
import hashlib
import json

SOURCE = 'rtl/workstation/workstation_task3_w_bus_endpoint.sv'
TOOL = 'tools/workstation_w_tx_class.py'
MANIFEST = 'rtl/workstation/workstation_w_tx_class_v1.adaptation.json'
MANIFEST_SHA256 = '51c2ef8c98baf59d26eb4f042a5584515c826ef4cff1392920fb8409c9707b0d'
PARENT_SHA256 = '7ff04e6154167bad39b1cc1551d79c3bcf37b141b36ac4902ba0b93e59044e17'
NATIVE_SHA256 = '660c699bf113af96d857c0f0d024b349c84c95d6707c27ed40569e54d7ce530f'
KEY = 'w_tx_class_policy'
POLICY = 'task3_W_registered_normal_tx_preference_v1'
DEFAULT = "parameter bit REGISTER_TX_CLASS=1'b0"
SELECTED = "parameter bit REGISTER_TX_CLASS=1'b1"


def digest(payload):
    return hashlib.sha256(payload.encode() if isinstance(payload, str) else payload).hexdigest()


def native(payload):
    text = payload.decode() if isinstance(payload, bytes) else payload
    if text.count(SELECTED) == 1:
        text = text.replace(SELECTED, DEFAULT, 1)
    if digest(text) != NATIVE_SHA256:
        raise ValueError('W TX class native source drift')
    return text.encode() if isinstance(payload, bytes) else text


def normalize(payload):
    if b'REGISTER_TX_CLASS' not in (payload.encode() if isinstance(payload, str) else payload):
        return payload
    text = native(payload)
    text = text.decode() if isinstance(text, bytes) else text
    raw = (Path(__file__).resolve().parents[1] / MANIFEST).read_bytes()
    if digest(raw) != MANIFEST_SHA256:
        raise ValueError('W TX class adaptation manifest drift')
    adaptation = json.loads(raw)
    if (adaptation['source'], adaptation['parent_sha256'], adaptation['native_sha256']) != (
            SOURCE, PARENT_SHA256, NATIVE_SHA256):
        raise ValueError('W TX class adaptation identity drift')
    for before, after in reversed(adaptation['edits']):
        if text.count(after) != 1:
            raise ValueError('W TX class inverse anchor drift')
        text = text.replace(after, before, 1)
    if digest(text) != PARENT_SHA256:
        raise ValueError('W TX class parent identity drift')
    return text.encode() if isinstance(payload, bytes) else text


def configured(configuration):
    value = configuration.get(KEY)
    if value not in (None, POLICY):
        raise ValueError('unknown W TX class policy')
    if value is not None and configuration.get('demo_role') != 'W':
        raise ValueError('W TX class role mismatch')
    return value is not None


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    payload = (Path(stage) / SOURCE).read_bytes()
    if payload.count(SELECTED.encode()) != 1:
        raise ValueError('W TX class register selection absent')
    normalize(payload)
    return dict(policy=POLICY, native_sha256=NATIVE_SHA256,
                selected_sha256=digest(payload), adaptation_sha256=MANIFEST_SHA256,
                preference_register_bits=3, payload_reserved=False,
                current_valid_and_live_required=True, sample_schedule_changed=False,
                hardware_tested=False)


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    payload = path.read_bytes()
    if digest(payload) != NATIVE_SHA256 or payload.count(DEFAULT.encode()) != 1:
        raise ValueError('W TX class selection source drift')
    normalize(payload)
    path.write_bytes(payload.replace(DEFAULT.encode(), SELECTED.encode(), 1))
    return evidence(stage, configuration)


def audit_active(n, g, stage, configuration, key_comparisons):
    """Bind the new mapping's actual batch guard without generated logic cuts.

    Reuse the checked GW5A interpreter and bounded SAT miter. All 420 relevant
    named state bits are arbitrary; the full live and comparison cones expand.
    """
    evidence(stage, configuration)
    from tools.workstation_task3_w_consumer_nextq import Circuit, Expressions, sat_compare
    scope = 'u_task3_bus_endpoint'
    batch = scope + '/g_phone_batch.batch_w'
    endpoint = lambda name: n.canonical(scope, name)
    q = lambda stem: n.pin(g.register(batch, stem), 'Q')
    e = Expressions()
    c = Circuit(n, e)
    positive = [n.canonical('', name) for name in (
        'reset_n', 'command_reset_n', 'clock_command_reset_n', 'hci_pcm_session_ready')]
    positive += [endpoint('live')]
    positive += [endpoint('media_cap_ready'), endpoint('phone_proxy_armed'), q('context_valid')]
    negative = [endpoint(name) for name in ('media_cap_fault', 'phone_window_fault', 'phone_proxy_fault')]
    negative += [q('fault_o'), *key_comparisons]
    expected = 1
    for net in positive:
        expected = e.choose(c.net(net), expected, 0)
    for net in negative:
        expected = e.choose(c.net(net), 0, expected)
    from tools.workstation_fifo_full_compare import configured as fifo_configured
    from tools.workstation_w_generation_successor import configured as successor_configured
    # Each actual mapping is independently proved over the complete420-state
    # function; generated names alone never establish the active predicate.
    active_name = ('n10383_29' if successor_configured(configuration) else
                   'n10383_7' if fifo_configured(configuration) else 'n12043_16')
    actual_net = endpoint(active_name)
    proof = sat_compare(e, c.net(actual_net), expected, label=POLICY + '-actual-active')
    from tools.workstation_w_context_compare import prove_zero_veto
    return actual_net, dict(contract='registered TX class actual full-state batch qualification',
        policy=POLICY, actual_qualification_net=actual_net, positive_inputs=positive,
        negative_inputs=negative, no_generated_logic_cuts=True,
        all_named_state_arbitrary=True, proof=proof,
        actual_root_zero_veto=prove_zero_veto(n,g,n.canonical('','reset_n'),endpoint('live')),
        full_endpoint_state_machine_proven=False, routed_timing_verified=False)

