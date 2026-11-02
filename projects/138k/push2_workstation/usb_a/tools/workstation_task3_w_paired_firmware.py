"""One reviewed temporary source adaptation for the explicit paired W ELF.

The original media C bytes/review remain unchanged. REC_START may request a
source before it exists; the real paired RTL gate acquires it before the same
physical engine checks source_ready. No source-good status is forged.
Exit: replace this single guarded dispatch decision with a versioned native
firmware role parameter after the paired board/hardware gates close.
"""
from pathlib import Path
import hashlib

POLICY = 'task3_w_paired_media_single_recording_60s_v1'
TOOL = 'tools/workstation_task3_w_paired_firmware.py'
SOURCE = 'firmware/ae350/ble_business_owner.c'
PARENT_SHA256 = 'e7d4b9dc032d2a4e494baf90364c13230f3550627d8658751c1ecd910ef15122'
SELECTED_SHA256 = 'c8fe79dd01ea477d39ecd9ea2fa631501030e25eed1c5d75786e749fdf7bad19'
PARENT = '        if(!(o->facts.state&(1u<<10)) || state!=0) {reject(o,BAD_STATE);return;}'
SELECTED = '        if(state!=0) {reject(o,BAD_STATE);return;}'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def adapt(text):
    if digest(text) != PARENT_SHA256 or text.count(PARENT) != 1:
        raise ValueError('paired REC_START original source identity/anchor drift')
    selected = text.replace(PARENT, SELECTED, 1)
    if digest(selected) != SELECTED_SHA256 or selected.count(SELECTED) != 1:
        raise ValueError('paired REC_START selected source identity/anchor drift')
    if selected.replace(SELECTED, PARENT, 1) != text:
        raise ValueError('paired REC_START exact inverse drift')
    return selected


def apply(root, output):
    root, output = Path(root), Path(output)
    source = root / SOURCE
    selected = adapt(source.read_text())
    (output / Path(SOURCE).name).write_text(selected)
    return dict(policy=POLICY, source=SOURCE, parent_sha256=PARENT_SHA256,
                selected_sha256=SELECTED_SHA256, unique_anchor=True,
                exact_inverse=True, forged_source_good=False,
                physical_engine_source_check_retained=True,
                bounded_RTL_source_gate_required=True)


def verify(root, output, evidence):
    root, output = Path(root), Path(output)
    selected = (output / Path(SOURCE).name).read_text()
    expected = dict(policy=POLICY, source=SOURCE, parent_sha256=PARENT_SHA256,
                    selected_sha256=SELECTED_SHA256, unique_anchor=True,
                    exact_inverse=True, forged_source_good=False,
                    physical_engine_source_check_retained=True,
                    bounded_RTL_source_gate_required=True)
    if evidence != expected or selected != adapt((root / SOURCE).read_text()):
        raise ValueError('paired REC_START actual compiled-source adaptation drift')
    return expected
