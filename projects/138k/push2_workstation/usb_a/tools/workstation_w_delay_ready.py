"""Explicit native W DMA alternative with same-edge ready/response cofactors.

Select a complete versioned implementation after the existing watchdog width
selection. Accepted DMA bytes stay unchanged. Consolidate this option into
the owning native composition only after paired functional/physical gates.
"""
from pathlib import Path
import hashlib

KEY = 'w_delay_ready_policy'
POLICY = 'task3_W_same_edge_DMA_ready_response_state_cofactors_v2'
SOURCE = 'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv'
ALTERNATE = 'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma_ready.sv'
TOOL = 'tools/workstation_w_delay_ready.py'
PARENT_SHA256 = '02df465082c98c6cbe5738206f5cd5dee632fbd91110977bc9ebe24275218bbf'
ALTERNATE_SHA256 = 'c492de733b9c60019ae03ae9cc1a8a11cb194a2b9c340c85d29831508796fb6d'
MARKER = '// Native W ready/response cofactor v2:'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('W DMA ready: ' + message)


def parent():
    # This inverse reconstructs only the already reviewed parent selection.
    # It never generates the new implementation, which is complete native RTL.
    from tools.workstation_w_watchdog_width import BEFORE, AFTER
    from tools.workstation_delay_watchdog_retime import DEFAULT, SELECTED
    root = Path(__file__).resolve().parents[1]
    text = (root/SOURCE).read_text()
    require(text.count(DEFAULT) == text.count(BEFORE) == 1, 'native parent drift')
    text = text.replace(DEFAULT, SELECTED, 1).replace(BEFORE, AFTER, 1)
    require(digest(text) == PARENT_SHA256, 'composed parent drift')
    return text


def restore(text):
    if MARKER not in text:
        return text
    require(digest(text) == ALTERNATE_SHA256, 'native alternative drift')
    return parent()


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'W' and
                configuration.get('w_watchdog_width_policy') ==
                'task3_W_bounded_saturating_wait_counter_v1' and
                configuration.get('delay_watchdog_policy') ==
                'task3_delay_watchdog_lagged_counter_same_fault_edge_v1',
                'requires the reviewed W watchdog composition')
    return bool(value)


def select(stage, configuration):
    if not configured(configuration):
        return None
    stage = Path(stage)
    require(digest((stage/SOURCE).read_text()) == PARENT_SHA256, 'input drift')
    require(digest((stage/ALTERNATE).read_text()) == ALTERNATE_SHA256,
            'alternative input drift')
    (stage/SOURCE).write_bytes((stage/ALTERNATE).read_bytes())
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    stage = Path(stage)
    text = (stage/SOURCE).read_text()
    require(digest(text) == ALTERNATE_SHA256 and
            (stage/SOURCE).read_bytes() == (stage/ALTERNATE).read_bytes(),
            'selection absent or changed')
    require(restore(text) == parent(), 'inverse mismatch')
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=ALTERNATE_SHA256,
                added_state_registers=0, added_cycles=0,
                native_acceptance_and_flush_schedule_unchanged=True,
                routed_timing_verified=False, hardware_tested=False)
