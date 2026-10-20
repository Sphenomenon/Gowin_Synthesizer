"""Apply bounded existing bus timing transforms to full83; no Flash boot changes."""
from pathlib import Path
import hashlib
from cnn_ddr_pipeline_patch import (patch_hdmi, patch_top, retime_tf_write_buffer,
    retime_tf_capture_limit, power_two_tf_ring, parallel_tf_byte_counters,
    retime_tf_read_total, fast_tf_read_availability, retime_tf_buffer_enable)

INPUTS = {
    'src/storage/tf_audio_ddr_dma.v': 'ac90bd9a06eea44162727169de24e887196b5746fbc29467e299caf9a66aa911',
    'src/memory/tf_audio_ddr_command_buffer.sv': 'c4b4a3e2ad17a50e2a59091d9f93f7c368c33c89956cd4d048734a3ef1f1f552',
    'src/video/hdmi_display.v': '7421e472c9289b1cca0eefe1c428bc03d7f6ea1081e7f8f86a785d6d7ac42dcc',
}
HELPER_SHA256 = '47b2086f90abab0b4ec6e058b2f294fde71ae1cfa09a460c629fac0da8bbd400'
MODULES = {
    'basic_pitch_ddr_arbiter_pipeline.sv': '7c390c18f9fa0477f4007c1f1f41bf9cee57e68730a1fc927e40a6f71eb0d69d',
    'basic_pitch_ddr_client_queues.sv': 'b3530585a536417e5dbf046658c8a6db834ba18052c670ba3163bd7d25a00a7c',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_dma(text):
    return fast_tf_read_availability(retime_tf_read_total(parallel_tf_byte_counters(
        power_two_tf_ring(retime_tf_capture_limit(retime_tf_write_buffer(text))))))


def apply(root, stage, top):
    if sha(root / 'tools/cnn_ddr_pipeline_patch.py') != HELPER_SHA256:
        raise ValueError('bounded timing transform helper drift')
    for name, digest in INPUTS.items():
        if sha(stage / name) != digest:
            raise ValueError('bus timing baseline drift: ' + name)
    for name, digest in MODULES.items():
        if sha(root / 'rtl/timing' / name) != digest or sha(stage / 'rtl/timing' / name) != digest:
            raise ValueError('bus timing module drift: ' + name)
    changes = {
        'src/storage/tf_audio_ddr_dma.v': expected_dma,
        'src/memory/tf_audio_ddr_command_buffer.sv': retime_tf_buffer_enable,
        'src/video/hdmi_display.v': lambda text: patch_hdmi(text, buffered_clients=True),
    }
    for name, transform in changes.items():
        path = stage / name
        path.write_text(transform(path.read_text()))
    top = patch_top(top)
    return top, dict(schema_version=1, original_sha256=INPUTS,
        helper_sha256=HELPER_SHA256, module_sha256=MODULES,
        transformed_sha256={name: sha(stage / name) for name in changes},
        scope='same eight DDR clients, addresses, commands and return ownership; local request slots and registered return',
        flash_boot=False, new_ddr_clients=0, added_bsram=0)
