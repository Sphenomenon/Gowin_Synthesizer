"""Checked verification provenance; never generates or selects production RTL."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

STRICT_POLICY = 'locked_native_v1'
OWNER8_POLICY = 'recording_owner8_v1'
SOURCE = 'rtl/workstation/workstation_hdmi_display.sv'
PROVENANCE = 'rtl/workstation/workstation_hdmi_display.provenance.json'
ADAPTATION = 'rtl/workstation/workstation_hdmi_display.recording_owner8_adaptation.json'
PROVENANCE_SHA256 = '2da2802f233a7286d7f728d48b62b4bd6327a954ab833b1784ede035e3924426'
ADAPTATION_SHA256 = '10a442a465bf51b23a332e8deb3742dc392fb347b99ffefd9ca3dd7fc0883ded'
OWNER8_SOURCES = ('rtl/memory/workstation_recording_ddr_client_queues.sv',
                  'rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reverse_edit(text, edit, label):
    if not edit['after'] or text.count(edit['after']) != 1:
        raise ValueError(label + ' reverse anchor drift')
    restored = text.replace(edit['after'], edit['before'])
    if not edit['before'] or restored.count(edit['before']) != 1:
        raise ValueError(label + ' forward anchor drift')
    if restored.replace(edit['before'], edit['after']) != text:
        raise ValueError(label + ' round trip changed bytes')
    return restored


def prepared_owner8_sources(root, project, profile):
    """Require actual compiled owner8 sources, matching the current owners."""
    root, project = Path(root), Path(project)
    entries = ET.parse(project / 'Prj1.gprj').getroot().find('FileList')
    bindings = {}
    for relative in OWNER8_SOURCES:
        rows = [entry for entry in entries if entry.get('path') == relative]
        current = sha((root / relative).read_bytes())
        if (len(rows) != 1 or rows[0].get('enable') != '1' or
                profile['enabled_inputs'].get(relative, {}).get('sha256') != current or
                sha((project / relative).read_bytes()) != current):
            raise ValueError('Prepared owner8 compilation source changed: ' + relative)
        bindings[relative] = current
    current_hdmi = sha((root / SOURCE).read_bytes())
    if (profile['staged_input_sha256'].get(SOURCE) != current_hdmi or
            sha((project / SOURCE).read_bytes()) != current_hdmi):
        raise ValueError('Prepared owner8 HDMI source changed')
    return bindings


def verify(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Return the exact pre-runtime input and evidence for an explicit chain.

    Source/manifests are bytes. The default only accepts the historical native
    checksum. The owner8 bridge must be named explicitly and reverses exactly
    the two reviewed edits before the unchanged original provenance is used.
    """
    if policy not in (STRICT_POLICY, OWNER8_POLICY):
        raise ValueError('Unknown HDMI provenance policy')
    if sha(provenance) != PROVENANCE_SHA256:
        raise ValueError('Original HDMI provenance bytes changed')
    info = json.loads(provenance)
    current = source.decode()
    evidence = dict(policy=policy, current_source_sha256=sha(source),
        original_provenance_sha256=sha(provenance), adaptation_applied=False,
        original_native_sha256=info['native_sha256'], hardware_acceptance_inherited=False)
    if policy == OWNER8_POLICY:
        if adaptation is None or sha(adaptation) != ADAPTATION_SHA256:
            raise ValueError('HDMI owner8 adaptation manifest changed or missing')
        bridge = json.loads(adaptation)
        if (bridge['policy'] != policy or bridge['source'] != SOURCE or
                bridge['original_provenance'] != PROVENANCE or
                bridge['original_provenance_sha256'] != sha(provenance) or
                bridge['parent_source_sha256'] != info['native_sha256'] or
                bridge['current_source_sha256'] != sha(source) or
                len(bridge['exact_changes']) != 2):
            raise ValueError('HDMI owner8 adaptation source identity changed')
        for edit in reversed(bridge['exact_changes']):
            current = reverse_edit(current, edit, 'HDMI owner8 adaptation')
        evidence.update(adaptation_applied=True, adaptation_sha256=sha(adaptation),
                        adaptation_reverse_edits=2, source_commit=bridge['source_commit'])
    elif adaptation is not None:
        raise ValueError('HDMI adaptation requires an explicit policy')
    if sha(current.encode()) != info['native_sha256']:
        raise ValueError('Native HDMI provenance checksum changed')
    prior_runtime = None
    for edit in reversed(info['exact_changes']):
        current = reverse_edit(current, edit, 'Original HDMI provenance')
        if sha(current.encode()) == info['pre_runtime_native_sha256']:
            prior_runtime = current
    if prior_runtime is None or sha(current.encode()) != info['parent_sha256']:
        raise ValueError('Reverse HDMI provenance did not reproduce exact inputs')
    evidence.update(original_reverse_edits=len(info['exact_changes']),
                    parent_sha256=sha(current.encode()),
                    pre_runtime_native_sha256=sha(prior_runtime.encode()),
                    reverse_exact_parent_bytes=True)
    return prior_runtime, evidence
