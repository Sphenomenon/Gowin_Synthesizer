"""W preboard large-FIFO full comparison before the late write selector.

Exact, reversible adaptation of the retained FIFO source. No new state,
cycles, capacity or pointer/CDC change. Retire this adapter when the owning
FIFO gains a versioned native selection and its existing profiles are reviewed.
"""
from pathlib import Path
import hashlib

SOURCE = 'rtl/music/music_async_fifo.sv'
TOOL = 'tools/workstation_fifo_full_compare.py'
KEY = 'fifo_full_policy'
POLICY = 'task3_W_large_FIFO_compare_before_write_select_v1'
PARENT_SHA256 = 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792'
SELECTED_SHA256 = '2c788d1704b659fb1802e555312f9999abc398d6782e6d68661499eca2304a31'
EDITS = (
    ('        logic full_q;\n', '''        logic full_q;
        (* syn_keep=1 *) wire full_if_written=write_gray_next==
            {~read_gray_sync[POINTER_BITS-1:POINTER_BITS-2],read_gray_sync[POINTER_BITS-3:0]};
        (* syn_keep=1 *) wire full_if_held=full;
'''),
    ('''            else full_q<=(write_fire ? write_gray_next : write_gray)==
                {~read_gray_sync[POINTER_BITS-1:POINTER_BITS-2],read_gray_sync[POINTER_BITS-3:0]};
''', '''            else case(write_fire)
                1'b0:full_q<=full_if_held;
                1'b1:full_q<=full_if_written;
                default:full_q<=(write_fire ? write_gray_next : write_gray)==
                    {~read_gray_sync[POINTER_BITS-1:POINTER_BITS-2],read_gray_sync[POINTER_BITS-3:0]};
            endcase
'''),
)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def transform(text, *, inverse=False):
    expected = SELECTED_SHA256 if inverse else PARENT_SHA256
    if digest(text) != expected:
        raise ValueError('large FIFO comparison source identity drift')
    for before, after in reversed(EDITS) if inverse else EDITS:
        if inverse:
            before, after = after, before
        if text.count(before) != 1:
            raise ValueError('large FIFO comparison exact anchor drift')
        text = text.replace(before, after, 1)
    if digest(text) != (PARENT_SHA256 if inverse else SELECTED_SHA256):
        raise ValueError('large FIFO comparison output identity drift')
    return text


def configured(configuration):
    value = configuration.get(KEY)
    if value not in (None, POLICY):
        raise ValueError('unknown large FIFO comparison policy')
    if value is not None and configuration.get('demo_role') != 'W':
        raise ValueError('large FIFO comparison requires explicit W role')
    return value is not None


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    transform((Path(stage) / SOURCE).read_text(), inverse=True)
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=SELECTED_SHA256, new_state_bits=0, new_cycles=0,
                pointer_and_CDC_equations_changed=False, hardware_tested=False)


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    path.write_text(transform(path.read_text()))
    return evidence(stage, configuration)
