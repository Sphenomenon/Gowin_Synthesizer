"""Opt-in source-clock register for the M phone lease CDC/reset boundary.

This temporary composition adaptation must invert to the complete v16 board.
Keep it separate until the new mapped CDC and routed timing gates are reviewed;
then move the selected composition into a versioned RTL provider. No protocol,
owner state, sample schedule or timing exception is changed here.
"""
from pathlib import Path
import hashlib

POLICY = 'task3_m_phone_lease_source_register_v1'
KEY = 'm_phone_lease_source_policy'
PROFILE = 'custom138k-workstation-task3-m-paired-checkpoint-v17'
PROFILES = (PROFILE, 'custom138k-workstation-task3-m-paired-checkpoint-v18')
ROOT_VARIANT = 'task3-m-source-clock-phone-lease-root-v1'
BOARD = 'rtl/workstation/workstation_task3_m_paired_board.svh'
TOOL = 'tools/workstation_task3_m_phone_lease_source.py'
PARENT_SHA256 = '541d91d67db0944c0ac4ad0979d4e1845cc297dbcbc88a2a2868b525346c4c0a'
SELECTED_SHA256 = '2f245d0d8f9b75f282a9478be048eeb2170f7be44d440c120e88f6bea8ab965d'
STAGE = '''    // TASK3 source-clock lease register begin.
    // Endpoint command acceptance is still fenced by the raw lease. Only its
    // CDC/reset observer is delayed, by at most one50MHz clock (20ns).
    // All lease causes must persist through a source edge; the existing
    // endpoint retires the lease on that edge before permitting a new ARM.
    (* syn_preserve=1 *) reg task3_m_phone_live_source;
    always @(posedge clk_50m or negedge runtime_common_reset_n)
        if(!runtime_common_reset_n)task3_m_phone_live_source<=0;
        else task3_m_phone_live_source<=task3_m_phone_live;
    // TASK3 source-clock lease register end.
'''
ANCHOR = '    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] task3_m_owner_live_sync;\n'
EDITS = (
    (ANCHOR, ANCHOR + STAGE),
    ('task3_m_owner_live_sync[1:0],task3_m_phone_live}',
     'task3_m_owner_live_sync[1:0],task3_m_phone_live_source}'),
    ('(!TASK3_PHONE_BATCH || task3_m_phone_live)',
     '(!TASK3_PHONE_BATCH || task3_m_phone_live_source)'),
)


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('M phone lease source: ' + message)


def apply(text):
    require(digest(text) == PARENT_SHA256, 'complete parent board changed')
    for before, after in EDITS:
        require(text.count(before) == 1, 'forward anchor changed')
        text = text.replace(before, after, 1)
    require(digest(text) == SELECTED_SHA256, 'selected board changed')
    return text


def restore(text):
    for before, after in reversed(EDITS):
        require(text.count(after) == 1, 'inverse anchor changed')
        text = text.replace(after, before, 1)
    require(digest(text) == PARENT_SHA256, 'unrelated board bytes changed')
    return text


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value is not None:
        require(configuration.get('demo_role') == 'M' and
                configuration.get('phone_batch_policy') == 'full_key_atomic_owner_snapshot_command_v1' and
                configuration.get('m_phone_identity_compare_policy') == 'task3_m_phone_full96_identity_group8_v1',
                'requires explicit M batch/full96 composition')
    return value is not None


def prepare(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / BOARD
    path.write_text(apply(path.read_text()))


def selection(stage, configuration, top):
    selected = configured(configuration)
    text = (Path(stage) / BOARD).read_text()
    if not selected:
        require('task3_m_phone_live_source' not in text and
                'task3_m_phone_live_source' not in top, 'unselected source register')
        return None
    parent = restore(text)
    require(apply(parent) == text and top.count(STAGE.strip()) == 1,
            'actual preprocessed source stage changed')
    return dict(policy=POLICY, source_clock='clk_50m', source_register_bits=1,
                maximum_additional_source_cycles=1, maximum_additional_delay_ns=20,
                raw_command_acceptance_fence_preserved=True,
                observer_reset_uses_source_register=True, destination_sync_stages=3,
                source_event_contract='lease revocation persists through a source edge',
                real_owner_reset_and_retired_state_preserved=True,
                source_board_sha256=digest(text), parent_board_sha256=PARENT_SHA256,
                exact_inverse_verified=True, physical_CDC_accepted=False,
                routed_timing_verified=False, hardware_tested=False)
