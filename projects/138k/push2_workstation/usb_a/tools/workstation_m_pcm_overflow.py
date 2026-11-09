"""Native M overflow permission with exact parent selection and inverse.

Only the explicit preboard M selects this implementation. Retire this option
into the owning native PCM source after the complete paired physical gates;
the historical parent and every fallback remain unchanged until then.
"""
from pathlib import Path
import hashlib

KEY = 'm_pcm_overflow_policy'
POLICY = 'task3_M_same_edge_PCM_overflow_permission_v1'
SOURCE = 'rtl/audio/workstation_ae350_pcm_owner.sv'
ALTERNATE = 'rtl/audio/workstation_ae350_pcm_owner_overflow.sv'
TOOL = 'tools/workstation_m_pcm_overflow.py'
PARENT_SHA256 = 'aa21dfd1f4c1ca1486a22de1a0efcf26fa21b0ac77763df53e650994ce9eefcd'
ALTERNATE_SHA256 = '640eaeee7b111e1f46da9e555f6168b3362006f4b0bf4a5afa182373f1e5eab8'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('M PCM overflow: ' + message)


def restore(text):
    if 'wire overflow_count_binary=' not in text:
        return text
    require(digest(text) == ALTERNATE_SHA256, 'alternate drift')
    start = text.index('    // For a window write, errors depend only on format/key/slot permission.')
    end = text.index('    function automatic [31:0] increment', start)
    parent = text[:start] + text[end:]
    selected = '            if(overflow_count)overflows<=increment(overflows);'
    original = """            if(write_command && response_error_o && (command_address_i[11] ||
                (command_address_i==12'h040 && command_data_i==2 && owned[tail_slot])))overflows<=increment(overflows);"""
    require(parent.count(selected) == 1, 'inverse anchor drift')
    parent = parent.replace(selected, original, 1)
    require(digest(parent) == PARENT_SHA256, 'parent drift')
    return parent


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'M', 'requires explicit M')
    return bool(value)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    stage = Path(stage)
    selected = (stage/SOURCE).read_text()
    require(digest(selected) == ALTERNATE_SHA256 and
            (stage/SOURCE).read_bytes() == (stage/ALTERNATE).read_bytes(),
            'alternate missing or changed')
    require(digest(restore(selected)) == PARENT_SHA256, 'inverse drift')
    return dict(policy=POLICY, parent_sha256=PARENT_SHA256,
                selected_sha256=ALTERNATE_SHA256, added_state_bits=0,
                added_cycles=0, native_acceptance_and_audio_schedule_unchanged=True,
                routed_timing_verified=False, hardware_tested=False)


def select(stage, configuration):
    if not configured(configuration):
        return None
    stage = Path(stage)
    require(digest((stage/SOURCE).read_text()) == PARENT_SHA256, 'input drift')
    require(digest((stage/ALTERNATE).read_text()) == ALTERNATE_SHA256, 'alternate drift')
    (stage/SOURCE).write_bytes((stage/ALTERNATE).read_bytes())
    return evidence(stage, configuration)
