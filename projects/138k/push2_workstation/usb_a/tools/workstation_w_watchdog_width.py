"""Exact W saturating-counter width selection; retire into native composition.

The full-DMA twin and counter induction must cover every supported timeout.
This selection changes storage width, without changing the fault edge.
"""
from pathlib import Path
import hashlib

KEY = 'w_watchdog_width_policy'
POLICY = 'task3_W_bounded_saturating_wait_counter_v1'
SOURCE = 'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv'
TOOL = 'tools/workstation_w_watchdog_width.py'
PARENT_SHA256 = '2568a77f5436d660df01de545b2a0556e8f5a168a89f66cf7e5b1037de4ab1ec'
SELECTED_SHA256 = '02df465082c98c6cbe5738206f5cd5dee632fbd91110977bc9ebe24275218bbf'
BEFORE = '  logic [31:0] wait_cycles,peer_wait;'
AFTER = ('  localparam integer WAIT_CYCLE_BITS=$clog2(TRANSACTION_TIMEOUT_CYCLES+1);\n'
         '  logic [WAIT_CYCLE_BITS-1:0] wait_cycles;\n  logic [31:0] peer_wait;')


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('W watchdog width: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'W' and
                configuration.get('delay_watchdog_policy') ==
                'task3_delay_watchdog_lagged_counter_same_fault_edge_v1',
                'requires W lagged watchdog')
    return bool(value)


def restore(text):
    from tools.workstation_w_delay_ready import restore as restore_ready
    text = restore_ready(text)
    if AFTER not in text:
        return text
    require(digest(text) == SELECTED_SHA256 and text.count(AFTER) == 1,
            'selected identity drift')
    parent = text.replace(AFTER, BEFORE, 1)
    require(digest(parent) == PARENT_SHA256, 'parent inverse drift')
    return parent


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    text = path.read_text()
    require(digest(text) == PARENT_SHA256 and text.count(BEFORE) == 1,
            'composed parent drift')
    path.write_text(text.replace(BEFORE, AFTER, 1))
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    text = (Path(stage) / SOURCE).read_text()
    from tools.workstation_w_delay_ready import restore as restore_ready
    text = restore_ready(text)
    require(digest(text) == SELECTED_SHA256, 'width selection absent')
    restore(text)
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=SELECTED_SHA256, production_wait_bits=21,
                timeout_cycles=1048576, removed_registers=11, added_cycles=0,
                fault_edge_unchanged=True, routed_timing_verified=False,
                hardware_tested=False)
