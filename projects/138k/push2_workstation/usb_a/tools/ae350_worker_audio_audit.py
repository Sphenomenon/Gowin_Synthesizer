"""Fail-closed composition checks for the explicit W audio-only firmware ELF."""
from pathlib import Path
import hashlib,re

def verify_composition(output,root,record):
    out,root=Path(output),Path(root)
    if not (record.get('headless_worker') and record.get('worker_demo') and record.get('runtime_owner')):
        raise ValueError('audio-only worker must be explicitly selected')
    expected={'start.S','worker_audio_main.c','ui_runtime.c','audio_clock_service.c',
              'classic_service.c','sbc_decoder_service.c','classic_security.c',
              'hci_transport.c','classic_runtime.c','pcm_media.c'}
    sources=record['compiled_sources']
    if {x for x in sources if not x.startswith('adapted/decoder/srce/')}!=expected:
        raise ValueError('audio-only worker translation unit inventory drift')
    if len(sources)!=len(set(sources)) or not any(x.startswith('adapted/decoder/srce/') for x in sources):
        raise ValueError('audio-only worker missing decoder or duplicate source')
    for name,h in record['input_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=h:
            raise ValueError('audio-only worker source changed: '+name)
    for row in record['commands']:
        if not row['name'].startswith('compile-'):continue
        flags=row['argv']
        if '-DA138_WORKER_AUDIO_ONLY' not in flags or '-DA138_CLASSIC_RUNTIME' not in flags or '-DA138_SINGLE_BLE_RECORDING' not in flags or '-DA138_BLE_BUSINESS' in flags:
            raise ValueError('audio-only worker compile flags changed')
    # No section GC is used, so absence here also verifies code was not merely
    # left unreachable behind a runtime enable. All supplied objects are linked.
    symbols=(out/'firmware.nm').read_text()
    forbidden=r'\b(?:ui_\w+|a138_ble_\w+|a138_record_\w+|a138_business_\w+|unavailable_load|unavailable_replace|unavailable_delete|ddr_checks|audio_checks|model_check|captured)\s*$'
    if re.search(forbidden,symbols,re.M):
        raise ValueError('retired UI/recording/business function or storage linked')
    if record.get('single_recording_owner') or record.get('local_recording_proxy') or record.get('graph_ui_compiled') or record.get('recording_compiled') or record.get('business_protocol_compiled'):
        raise ValueError('audio-only worker reports retired backend enabled')
    if record.get('source_text_overlay')is not False or not record.get('no_gc_sections') or not record.get('no_LTO'):
        raise ValueError('audio-only worker requires maintained sources without dead-section masking')
    return {'translation_units':len(sources),'retired_symbols_absent':True,'no_gc_or_lto':True}
