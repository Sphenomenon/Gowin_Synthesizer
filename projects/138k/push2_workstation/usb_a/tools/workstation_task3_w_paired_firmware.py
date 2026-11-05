"""One reviewed temporary source adaptation for the explicit paired W ELF.

The frozen media review remains unchanged. REC_START may request a
source before it exists; the real paired RTL gate acquires it before the same
physical engine checks source_ready. No source-good status is forged.
Exit: replace this single guarded dispatch decision with a versioned native
firmware role parameter after the paired board/hardware gates close.
"""
from pathlib import Path
import hashlib
import json
import re
from tools.workstation_recording_format_provenance import parent_source

POLICY = 'task3_w_paired_media_single_recording_60s_v1'
BATCH_POLICY = 'task3_w_paired_phone_batch_single_recording_60s_v1'
BATCH_REVIEW = 'tools/workstation_task3_w_phone_batch_firmware_review.json'
PARENT_REVIEW = 'tools/workstation_task3_w_media_firmware_review.json'
PARENT_REVIEW_SHA256 = '270cb779c8b2eba7f7fa2655f611e784052c7269fbbd0d9eb9e9c4c31e8d34da'
TOOL = 'tools/workstation_task3_w_paired_firmware.py'
SOURCE = 'firmware/ae350/ble_business_owner.c'
PARENT_SHA256 = 'e7d4b9dc032d2a4e494baf90364c13230f3550627d8658751c1ecd910ef15122'
SELECTED_SHA256 = 'c8fe79dd01ea477d39ecd9ea2fa631501030e25eed1c5d75786e749fdf7bad19'
PARENT = '        if(!(o->facts.state&(1u<<10)) || state!=0) {reject(o,BAD_STATE);return;}'
SELECTED = '        if(state!=0) {reject(o,BAD_STATE);return;}'


def disabled_phone_batch_source(payload):
    """Exact disabled-guard lineage for the new review, never old admission.

    No compiler input is replaced. Only the reviewed A138_TASK3_PHONE_BATCH
    conditional is evaluated; all other bytes/directives remain unchanged.
    The independent new review pins the complete current and parent hashes.
    """
    lines = payload.decode().splitlines(keepends=True)
    result = []
    active = False
    depth = 0
    retain = False
    for line in lines:
        directive = re.match(r'^\s*#\s*(if|ifdef|ifndef|else|elif|endif)\b(.*)', line)
        if not active:
            if line == '#ifdef A138_TASK3_PHONE_BATCH\n':
                active, depth, retain = True, 1, False
            else:
                result.append(line)
        else:
            kind = directive[1] if directive else None
            if kind in ('if', 'ifdef', 'ifndef'):
                depth += 1
            elif kind == 'endif':
                depth -= 1
                if not depth:
                    active = False
                    continue
            elif kind in ('else', 'elif') and depth == 1:
                if kind != 'else':
                    raise ValueError('batch lineage does not accept elif')
                retain = not retain
                continue
            if retain:
                result.append(line)
    if active:
        raise ValueError('unterminated batch lineage conditional')
    return ''.join(result).encode()


def verify_phone_batch_sources(root, expected):
    """Independent actual batch source review; old review stays immutable."""
    root = Path(root)
    parent_payload = (root / PARENT_REVIEW).read_bytes()
    if digest(parent_payload) != PARENT_REVIEW_SHA256:
        raise ValueError('batch inherited media review identity drift')
    parent = json.loads(parent_payload)
    reviewed = json.loads((root / BATCH_REVIEW).read_text())
    if (reviewed.get('policy') != BATCH_POLICY or
            reviewed.get('parent_review_sha256') != PARENT_REVIEW_SHA256 or
            set(reviewed.get('input_sha256', {})) != set(expected) or
            set(parent['input_sha256']) != set(expected)):
        raise ValueError('batch source review policy/inventory drift')
    lineage = {}
    guarded = {'classic_runtime.c': 1, 'pcm_media.c': 3, 'pcm_media.h': 2}
    for rel, wanted in reviewed['input_sha256'].items():
        payload = (root / rel).read_bytes()
        # Compare the independently locked format parent for provenance only;
        # the actual current C/header bytes are copied into the new ELF build.
        payload, _ = parent_source(root, Path(rel).name, payload)
        if digest(payload) != wanted:
            raise ValueError('batch reviewed source drift: ' + rel)
        if Path(rel).name in guarded:
            if payload.count(b'#ifdef A138_TASK3_PHONE_BATCH\n') != guarded[Path(rel).name]:
                raise ValueError('batch guarded source inventory drift: ' + rel)
            inherited = disabled_phone_batch_source(payload)
            if digest(inherited) != parent['input_sha256'][rel]:
                raise ValueError('batch disabled-guard parent identity drift: ' + rel)
            lineage[rel] = dict(actual_sha256=wanted, parent_sha256=digest(inherited),
                exact_disabled_guard_parent=True, actual_source_compiled=True)
        elif wanted != parent['input_sha256'][rel]:
            raise ValueError('batch unrelated media source drift: ' + rel)
    return reviewed, lineage


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def _selection(text, root):
    parent, lineage = parent_source(root, Path(SOURCE).name, text.encode())
    if digest(parent) != PARENT_SHA256 or text.count(PARENT) != 1:
        raise ValueError('paired REC_START original source identity/anchor drift')
    selected = text.replace(PARENT, SELECTED, 1)
    if digest(parent.decode().replace(PARENT, SELECTED, 1)) != SELECTED_SHA256 or selected.count(SELECTED) != 1:
        raise ValueError('paired REC_START selected source identity/anchor drift')
    if selected.replace(SELECTED, PARENT, 1) != text:
        raise ValueError('paired REC_START exact inverse drift')
    evidence = dict(policy=POLICY, source=SOURCE, parent_sha256=digest(text),
                    selected_sha256=digest(selected), unique_anchor=True,
                    exact_inverse=True, forged_source_good=False,
                    physical_engine_source_check_retained=True,
                    bounded_RTL_source_gate_required=True)
    if lineage is not None:
        evidence['recording_format_lineage'] = lineage
    return selected, evidence


def adapt(text, root=None):
    return _selection(text, Path(root) if root is not None else Path(__file__).resolve().parents[1])[0]


def apply(root, output):
    root, output = Path(root), Path(output)
    source = root / SOURCE
    selected, evidence = _selection(source.read_text(), root)
    (output / Path(SOURCE).name).write_text(selected)
    return evidence


def verify(root, output, evidence):
    root, output = Path(root), Path(output)
    selected = (output / Path(SOURCE).name).read_text()
    expected_source, expected = _selection((root / SOURCE).read_text(), root)
    if evidence != expected or selected != expected_source:
        raise ValueError('paired REC_START actual compiled-source adaptation drift')
    return expected
