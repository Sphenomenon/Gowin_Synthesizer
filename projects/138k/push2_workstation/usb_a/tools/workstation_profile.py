"""Lock one explicit native workstation source policy without promoting it.

The profile is an implementation checkpoint, not a hardware capability claim.
It reuses the existing native preparation and records its complete staged
closure. Accepted, pinned and resource-only entry points never select it.
"""

from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ElementTree

from tools.workstation_baselines import load_baseline
from tools.workstation_usb_fifo_reset import POLICY as DEMO_USB_FIFO_RESET_POLICY


NAME = 'custom138k-workstation-v1'
CONFIG = 'boards/custom_138k/workstation_profile_v1.json'
ARTIFACT = 'workstation_profile.json'
AE350_POLICY = 'maintained_ae350_v1'
AE350_DIRECTORY = 'ae350_firmware'
REVISION = 5
RUNTIME_CONFIGURATION = dict(hdmi_mode='1080p60', high_speed_allowed=True,
    tf_audio_kind='wav', implemented_sample_rates_hz=[48000, 44100],
    ae350_firmware_policy=AE350_POLICY, scan_window_policy='native_admission_v1',
    audio_policy='native_dual_rate_runtime_v1', reserve_zero_epoch=True,
    display_metadata_minor=1,
    media_preparation_policy='seal_record_stop_score_tf_ble_v1')


NO_CNN_NAME = 'custom138k-workstation-no-cnn-v1'
NO_CNN_CONFIG = 'boards/custom_138k/workstation_profile_no_cnn_v1.json'
RUNTIME_PROVIDER = 'rtl/workstation/workstation_profile_runtime.sv'
from tools.workstation_recognition_policy import PROVIDER as NO_CNN_PROVIDER
from tools.workstation_recording_policy import NAME as R00_NAME, CONFIG as R00_CONFIG, PROVIDER as R00_PROVIDER, POLICY as R00_POLICY
R00_NO_LOCAL_PANEL_NAME = 'custom138k-workstation-r00-no-local-panel-v1'
R00_NO_LOCAL_PANEL_CONFIG = 'boards/custom_138k/workstation_profile_r00_no_local_panel_v1.json'
R00_NO_LOCAL_PANEL_PROVIDER = 'rtl/workstation/workstation_profile_r00_no_local_panel.sv'
CPU_BUSINESS_NAME='custom138k-workstation-ae350-business-v1'
CPU_BUSINESS_CONFIG='boards/custom_138k/workstation_profile_ae350_business_v1.json'
HCI_OWNER_NAME='custom138k-workstation-hci-owner-v1'
HCI_OWNER_CONFIG='boards/custom_138k/workstation_profile_hci_owner_v1.json'
CLASSIC_RUNTIME_NAME='custom138k-workstation-classic-runtime-v1'
CLASSIC_RUNTIME_CONFIG='boards/custom_138k/workstation_profile_classic_runtime_v1.json'
CLASSIC_ROM96_NAME='custom138k-workstation-classic-runtime-rom96-v1'
CLASSIC_ROM96_CONFIG='boards/custom_138k/workstation_profile_classic_runtime_rom96_v1.json'
CPU_BUSINESS_CONFIGURATION=dict(RUNTIME_CONFIGURATION,recognition_policy='disabled_cnn_and_follow_v1',
    recording_policy=R00_POLICY,local_panel_policy='disabled_local_lcd_touch_v1',
    ble_recording_storage_policy='native_raw_ddr_ae350_business_v2',business_owner_policy='ae350_ble_business_owner_v2',
    ae350_core_clock_policy='pll_r0_clkout1_v1',
    ae350_rtc_policy='reference50_fractional32768_bound1524_v1',
    ae350_memory_profile='ilm64k_dlm64k',ae350_boot_rom_bytes=65536)
LOCAL_BOOT64_NAME = 'custom138k-workstation-r00-no-local-panel-ilm64k-boot64k-v1'
LOCAL_BOOT64_CONFIG = 'boards/custom_138k/workstation_profile_r00_no_local_panel_ilm64k_boot64k_v1.json'
M_DEMO_NAME='custom138k-workstation-m-demo-v1'
W_DEMO_NAME='custom138k-workstation-w-demo-v1'
TASK3_M_TF_NAME='custom138k-workstation-task3-m-local-tf-v1'
TASK3_M_DIRECT_NAME='custom138k-workstation-task3-m-direct-tf-v1'
TASK3_W_MEDIA_NAME='custom138k-workstation-task3-w-media-v1'
TASK3_W_SIGNAL_NAME='custom138k-workstation-task3-w-media-signal-bsram-v1'
TASK3_W_CQT_NAME='custom138k-workstation-task3-w-media-cqt-bsram-v1'
TASK3_M_PAIRED_NAME='custom138k-workstation-task3-m-paired-v1'
TASK3_W_PAIRED_NAME='custom138k-workstation-task3-w-paired-v1'
PROFILE_REGISTRY = {
    TASK3_W_MEDIA_NAME:dict(config='boards/custom_138k/workstation_profile_task3_w_media_v1.json',revision=1,
        configuration=dict(CPU_BUSINESS_CONFIGURATION,hci_transport_policy='native_shared_hci_owner_v1',
            ae350_firmware_policy='task3_w_headless_media_single_recording_60s_v1',ae350_boot_rom_bytes=131072,
            hdmi_mode='disabled_worker_media',display_policy='disabled_worker_media_v1',
            scan_window_policy='disabled_worker_media_v1',
            recording_policy='task3_w_single_C_BLE_recording_60s_v1',
            ble_recording_storage_policy='task3_w_single_C_BLE_raw_ddr_60s_v1',
            business_owner_policy='ae350_single_C_BLE_recording_owner_v1',
            media_preparation_policy='single_C_BLE_seal_recording_v1',
            recognition_policy='task3_w_bounded_CNN_task_v1',
            ae350_pcm_policy='ae350_decoded_pcm_source_v1',demo_role='W',
            usb_fifo_reset_policy=DEMO_USB_FIFO_RESET_POLICY,synth_policy='disabled_d_pcm_only_v1',
            tf_policy='disabled_worker_media_v1',recording_owner_policy='single_C_BLE_ddr_60s_v1',
            usb_adapter_policy='worker_25k_v1',interboard_transport_policy='LCD_unverified_down_v1'),
        provider='rtl/workstation/workstation_profile_task3_w_media.sv',recognition_enabled=False,
        recording_enabled=True,local_panel_enabled=False,ble_recording_storage_enabled=True,
        business_owner_enabled=True,hci_shared_owner_enabled=True,classic_runtime_enabled=True,
        demo_role='W',worker_media=True,integration_identity='custom138k-native-task3-w-media-revision1'),
    TASK3_M_DIRECT_NAME:dict(config='boards/custom_138k/workstation_profile_task3_m_direct_tf_v1.json', revision=1,
        configuration=dict(RUNTIME_CONFIGURATION, recognition_policy='disabled_cnn_and_follow_v1',
            local_panel_policy='disabled_local_lcd_touch_v1',demo_role='M',
            usb_fifo_reset_policy=DEMO_USB_FIFO_RESET_POLICY,
            tf_policy='task3_m_native_direct_tf_v1',
            tf_storage_policy='direct_sd_crc16_validated_fat_cache_v1',tf_sdc_revision=3,
            bluetooth_policy='retired_for_independent_m_demo_v1',recording_policy='disabled_m_demo_v1'),
        provider='rtl/workstation/workstation_profile_task3_m_direct_tf.sv',recognition_enabled=False,
        local_panel_enabled=False,demo_role='M',tf_menu_enabled=True,tf_direct_enabled=True,
        integration_identity='custom138k-native-task3-m-direct-tf-revision1'),
    TASK3_M_TF_NAME:dict(config='boards/custom_138k/workstation_profile_task3_m_local_tf_v1.json', revision=1,
        configuration=dict(RUNTIME_CONFIGURATION, recognition_policy='disabled_cnn_and_follow_v1',
            local_panel_policy='disabled_local_lcd_touch_v1',demo_role='M',
            usb_fifo_reset_policy=DEMO_USB_FIFO_RESET_POLICY,
            tf_policy='local_tf_ddr_with_independent_menu_v1',
            bluetooth_policy='retired_for_independent_m_demo_v1',recording_policy='disabled_m_demo_v1'),
        provider='rtl/workstation/workstation_profile_task3_m_local_tf.sv',recognition_enabled=False,
        local_panel_enabled=False,demo_role='M',tf_menu_enabled=True,
        integration_identity='custom138k-native-task3-m-local-tf-revision1'),
    M_DEMO_NAME:dict(config='boards/custom_138k/workstation_profile_m_demo_v1.json', revision=1,
        configuration=dict(RUNTIME_CONFIGURATION, recognition_policy='disabled_cnn_and_follow_v1',
            local_panel_policy='disabled_local_lcd_touch_v1',demo_role='M',
            usb_fifo_reset_policy=DEMO_USB_FIFO_RESET_POLICY,
            tf_policy='disabled_first_m_core_demo_v1',
            bluetooth_policy='retired_for_independent_m_demo_v1',recording_policy='disabled_m_demo_v1'),
        provider='rtl/workstation/workstation_profile_m_demo.sv',recognition_enabled=False,
        local_panel_enabled=False,demo_role='M',
        integration_identity='custom138k-native-m-demo-base-revision1'),
    W_DEMO_NAME:dict(config='boards/custom_138k/workstation_profile_w_demo_v1.json',revision=2,
        configuration=dict(CPU_BUSINESS_CONFIGURATION,hci_transport_policy='native_shared_hci_owner_v1',
            ae350_firmware_policy='ae350_worker_audio_only_classic_runtime_v1',ae350_boot_rom_bytes=131072,
            hdmi_mode='disabled_worker_audio_only',display_policy='disabled_worker_audio_only_v1',
            scan_window_policy='disabled_worker_audio_only_v1',
            recording_policy='disabled_worker_audio_only_v1',
            ble_recording_storage_policy='disabled_worker_audio_only_v1',
            business_owner_policy='native_hci_only_no_recording_v1',
            media_preparation_policy='runtime_only_no_recording_or_display_v1',
            ae350_pcm_policy='ae350_decoded_pcm_source_v1',demo_role='W',
            usb_fifo_reset_policy=DEMO_USB_FIFO_RESET_POLICY,
            synth_policy='disabled_d_pcm_only_v1',tf_policy='disabled_worker_demo_v1',
            recording_owner_policy='disabled_worker_audio_only_v1',usb_adapter_policy='worker_25k_v1'),
        provider='rtl/workstation/workstation_profile_w_demo.sv',recognition_enabled=False,
        recording_enabled=False,local_panel_enabled=False,ble_recording_storage_enabled=False,
        business_owner_enabled=True,hci_shared_owner_enabled=True,classic_runtime_enabled=True,demo_role='W',
        worker_audio_only=True,integration_identity='custom138k-native-w-audio-only-revision2'),
    CLASSIC_ROM96_NAME:dict(config=CLASSIC_ROM96_CONFIG,revision=1,
        configuration=dict(CPU_BUSINESS_CONFIGURATION,hci_transport_policy='native_shared_hci_owner_v1',
            ae350_firmware_policy='ae350_classic_runtime_rom96_failclosed_v1',ae350_boot_rom_bytes=98304,
            ae350_pcm_policy='ae350_decoded_pcm_source_v1'),
        provider='rtl/workstation/workstation_profile_classic_runtime_rom96_v1.sv',recognition_enabled=False,
        recording_enabled=True,local_panel_enabled=False,ble_recording_storage_enabled=True,
        business_owner_enabled=True,hci_shared_owner_enabled=True,classic_runtime_enabled=True,
        integration_identity='custom138k-native-classic-runtime-rom96-revision1'),
    CLASSIC_RUNTIME_NAME:dict(config=CLASSIC_RUNTIME_CONFIG,revision=1,
        configuration=dict(CPU_BUSINESS_CONFIGURATION,hci_transport_policy='native_shared_hci_owner_v1',
            ae350_firmware_policy='ae350_classic_runtime_failclosed_v1',ae350_boot_rom_bytes=131072,
            ae350_pcm_policy='ae350_decoded_pcm_source_v1'),
        provider='rtl/workstation/workstation_profile_classic_runtime_v1.sv',recognition_enabled=False,
        recording_enabled=True,local_panel_enabled=False,ble_recording_storage_enabled=True,
        business_owner_enabled=True,hci_shared_owner_enabled=True,classic_runtime_enabled=True,
        integration_identity='custom138k-native-classic-runtime-revision1'),
    HCI_OWNER_NAME:dict(config=HCI_OWNER_CONFIG,revision=1,
        configuration=dict(CPU_BUSINESS_CONFIGURATION,hci_transport_policy='native_shared_hci_owner_v1'),
        provider='rtl/workstation/workstation_profile_hci_owner_v1.sv',recognition_enabled=False,
        recording_enabled=True,local_panel_enabled=False,ble_recording_storage_enabled=True,
        business_owner_enabled=True,hci_shared_owner_enabled=True,
        integration_identity='custom138k-native-hci-shared-owner-revision1'),
    CPU_BUSINESS_NAME:dict(config=CPU_BUSINESS_CONFIG,revision=4,configuration=CPU_BUSINESS_CONFIGURATION,
        provider='rtl/workstation/workstation_profile_ae350_business_v1.sv',recognition_enabled=False,
        recording_enabled=True,local_panel_enabled=False,ble_recording_storage_enabled=True,
        business_owner_enabled=True,
        integration_identity='custom138k-native-ae350-business-revision4'),
    LOCAL_BOOT64_NAME: dict(config=LOCAL_BOOT64_CONFIG, revision=1,
        configuration=dict(RUNTIME_CONFIGURATION, recognition_policy='disabled_cnn_and_follow_v1',
            recording_policy=R00_POLICY, local_panel_policy='disabled_local_lcd_touch_v1',
            ble_recording_storage_policy='native_raw_ddr_v1',
            ae350_memory_profile='ilm64k_dlm64k', ae350_boot_rom_bytes=65536),
        provider=R00_NO_LOCAL_PANEL_PROVIDER, recognition_enabled=False, recording_enabled=True,
        local_panel_enabled=False, ble_recording_storage_enabled=True,
        integration_identity='custom138k-native-dual-rate-r00-no-local-panel-ilm64k-boot64k-revision1'),
    R00_NO_LOCAL_PANEL_NAME: dict(config=R00_NO_LOCAL_PANEL_CONFIG, revision=2,
        configuration=dict(RUNTIME_CONFIGURATION, recognition_policy='disabled_cnn_and_follow_v1',
            recording_policy=R00_POLICY, local_panel_policy='disabled_local_lcd_touch_v1',
            ble_recording_storage_policy='native_raw_ddr_v1'),
        provider=R00_NO_LOCAL_PANEL_PROVIDER, recognition_enabled=False, recording_enabled=True,
        local_panel_enabled=False, ble_recording_storage_enabled=True,
        integration_identity='custom138k-native-dual-rate-r00-no-local-panel-revision2'),
    R00_NAME: dict(config=R00_CONFIG, revision=1,
        configuration=dict(RUNTIME_CONFIGURATION,recognition_policy='disabled_cnn_and_follow_v1',recording_policy=R00_POLICY),
        provider=R00_PROVIDER,recognition_enabled=False,recording_enabled=True,
        integration_identity='custom138k-native-dual-rate-r00-revision1'),
    NAME: dict(config=CONFIG, revision=REVISION, configuration=RUNTIME_CONFIGURATION,
               provider=RUNTIME_PROVIDER, recognition_enabled=True,
               integration_identity='custom138k-native-dual-rate-runtime-revision5'),
    NO_CNN_NAME: dict(config=NO_CNN_CONFIG, revision=1,
        configuration=dict(RUNTIME_CONFIGURATION, recognition_policy='disabled_cnn_and_follow_v1'),
        provider=NO_CNN_PROVIDER, recognition_enabled=False,
        integration_identity='custom138k-native-dual-rate-no-cnn-revision1'),
}

for _name,_config,_provider,_policy,_identity in (
    (TASK3_W_SIGNAL_NAME,'boards/custom_138k/workstation_profile_task3_w_media_signal_bsram_v1.json',
     'rtl/workstation/workstation_profile_task3_w_media_signal_bsram.sv',
     'task3_w_signal_bsram_v1','custom138k-native-task3-w-media-signal-bsram-revision1'),
    (TASK3_W_CQT_NAME,'boards/custom_138k/workstation_profile_task3_w_media_cqt_bsram_v1.json',
     'rtl/workstation/workstation_profile_task3_w_media_cqt_bsram.sv',
     'task3_w_signal_cqt_bsram_v1','custom138k-native-task3-w-media-cqt-bsram-revision1')):
    _parent=PROFILE_REGISTRY[TASK3_W_MEDIA_NAME]
    PROFILE_REGISTRY[_name]=dict(_parent,config=_config,provider=_provider,
        configuration=dict(_parent['configuration'],cnn_memory_policy=_policy),
        integration_identity=_identity)

# Explicit new pair policies keep every independent M/W lock and provider.
_paired_configuration=dict(
    interboard_transport_policy='task3_lcd_reqack_crc_session_budget_gated_v1',
    interboard_media_policy='task3_pcm_block6_credit8_capability_v1',
    paired_config_policy='task3_f808_nonzero_nonce_v1',
    interboard_business_default_enabled=False,
    interboard_physical_acceptance_required=True)
_parent=PROFILE_REGISTRY[TASK3_M_DIRECT_NAME]
PROFILE_REGISTRY[TASK3_M_PAIRED_NAME]=dict(_parent,
    config='boards/custom_138k/workstation_profile_task3_m_paired_v1.json',
    provider='rtl/workstation/workstation_profile_task3_m_paired.sv',
    configuration=dict(_parent['configuration'],**_paired_configuration,
        recognition_policy='task3_m_remote_CNN_follow_v1',
        ae350_pcm_policy='task3_m_remote_commands_existing_PCM1_v1',
        bluetooth_policy='task3_W_HCI_decode_M_PCM1_v1',
        recording_policy='task3_M_final_physical_tap_to_W_single_object_v1'),
    paired_board=True,paired_role='M',paired_worker=False,
    integration_identity='custom138k-native-task3-m-paired-revision1')
_parent=PROFILE_REGISTRY[TASK3_W_CQT_NAME]
PROFILE_REGISTRY[TASK3_W_PAIRED_NAME]=dict(_parent,
    config='boards/custom_138k/workstation_profile_task3_w_paired_v1.json',
    provider='rtl/workstation/workstation_profile_task3_w_paired.sv',
    configuration=dict(_parent['configuration'],**_paired_configuration,
        ae350_firmware_policy='task3_w_paired_media_single_recording_60s_v1',
        recognition_policy='task3_w_paired_native_CNN_stream_v1',
        recording_policy='task3_w_paired_single_C_BLE_recording_60s_v1',
        ble_recording_storage_policy='task3_w_paired_single_C_BLE_raw_ddr_60s_v1',
        ae350_pcm_policy='task3_W_HCI_decode_M_PCM1_v1'),
    paired_board=True,paired_role='W',paired_worker=True,
    integration_identity='custom138k-native-task3-w-paired-revision1')


# PR #2 CPU capacity optimization is opt-in and independently sealed. The W
# v8 candidate and every prior M/worker profile retain their original inputs.
TASK3_M_CPU48_NAME='custom138k-workstation-task3-m-paired-cpu48-v1'
_parent=PROFILE_REGISTRY[TASK3_M_PAIRED_NAME]
PROFILE_REGISTRY[TASK3_M_CPU48_NAME]=dict(_parent,
    config='boards/custom_138k/workstation_profile_task3_m_paired_cpu48_v1.json',
    configuration=dict(_parent['configuration'],usb2_cpu_ram_bytes=49152),
    integration_identity='custom138k-native-task3-m-paired-cpu48-revision1')


def specification(name):
    if name not in PROFILE_REGISTRY:
        raise ValueError('unknown workstation profile: '+str(name))
    return PROFILE_REGISTRY[name]


def prepared_specification(prepared):
    """Select a sealed revision without promoting it to today's build policy."""
    spec = specification(prepared.get('profile'))
    if prepared.get('profile') == W_DEMO_NAME and prepared.get('revision') == 1:
        # Revision 1 had a real display and one BLE recording owner. Its
        # immutable candidates continue to be audited against that contract.
        spec = dict(spec, revision=1, worker_audio_only=False,
            integration_identity='custom138k-native-w-demo-d-only-revision1',
            configuration=dict(CPU_BUSINESS_CONFIGURATION,
                hci_transport_policy='native_shared_hci_owner_v1',
                ae350_firmware_policy='ae350_worker_session_classic_runtime_v1',
                ae350_boot_rom_bytes=131072, ae350_pcm_policy='ae350_decoded_pcm_source_v1',
                demo_role='W', usb_fifo_reset_policy=DEMO_USB_FIFO_RESET_POLICY,
                synth_policy='disabled_d_pcm_only_v1', tf_policy='disabled_worker_demo_v1',
                recording_owner_policy='single_ble_ddr_object_v1', usb_adapter_policy='worker_25k_v1'))
    legacy = dict(spec['configuration'])
    legacy.pop('usb_fifo_reset_policy', None)
    accepted_configurations=(spec['configuration'],)if spec.get('paired_board',False)else(spec['configuration'],legacy)
    if (prepared.get('revision') != spec['revision'] or prepared.get('profile_source') != spec['config'] or
            prepared.get('configuration') not in accepted_configurations):
        raise ValueError('prepared workstation revision/configuration identity changed')
    return spec


def recognition_metadata(profile):
    spec = specification(profile['name'])
    enabled = spec['recognition_enabled']
    metadata = dict(policy='enabled_cnn_and_follow_v1' if enabled else 'disabled_cnn_and_follow_v1',
        music_analysis_enabled=enabled, cnn_score_follow_enabled=enabled,
        model_ready_not_forged=True, local_score_cue_preserved=True,
        recognition_menu_available=enabled, ddr_nn_allocation_retained=True)
    if spec.get('worker_media',False):
        metadata.update(policy='task3_w_bounded_CNN_task_v1',task_CNN_enabled=True,
            music_analysis_enabled=False,cnn_score_follow_enabled=False,
            legacy_TF_follow_retired=True,task_results_available_through='0xf8070000',
            Push_guidance_transport_connected=False)
    if spec.get('tf_menu_enabled', False):
        metadata.update(tf_menu_enabled=True, recognition_menu_available=False,
                        tf_song_menu_available=True)
    if spec.get('paired_role')=='M':
        metadata.update(policy='task3_m_remote_CNN_follow_v1',
            local_CNN_enabled=False,remote_analysis_enabled=True,
            local_score_cue_preserved=False,local_score_service_enabled=False,
            cnn_score_follow_enabled=True,recognition_menu_available=True,
            Push_guidance_transport_connected=True,
            final_score_requires_actual_file_terminal=True,
            physical_LCD_hardware_verified=False)
    elif spec.get('paired_role')=='W':
        metadata.update(policy='task3_w_paired_native_CNN_stream_v1',
            local_score_cue_preserved=False,local_score_service_enabled=False,
            task_results_available_through='paired_ordered_result_lane',
            Push_guidance_transport_connected=True,
            physical_LCD_hardware_verified=False)
    return metadata


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked_path(base, relative):
    path = (base / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(base) or not path.is_file():
        raise ValueError('workstation profile missing or escaping input: ' + relative)
    return path


def load(root, name, *, allow_high_speed=True, hdmi_mode='1080p60'):
    root = Path(root).resolve()
    repository = root.parents[3]
    spec = specification(name)
    config = checked_path(root, spec['config'])
    profile = json.loads(config.read_text())
    if (profile.get('schema') != 1 or profile.get('name') != name or
            type(profile.get('revision')) is not int or profile['revision'] != spec['revision']):
        raise ValueError('workstation profile identity changed')
    if (profile.get('configuration') != spec['configuration'] or
            hdmi_mode not in (('1080p60','disabled_worker_media') if spec.get('worker_media',False) else ('1080p60','disabled_worker_audio_only') if spec.get('worker_audio_only',False) else ('1080p60',)) or allow_high_speed is not True):
        raise ValueError('workstation profile configuration mismatch')
    if not profile.get('source_sha256') or not profile.get('features') or not profile.get('references'):
        raise ValueError('incomplete workstation profile')
    for relative, expected in profile['source_sha256'].items():
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('invalid workstation source hash: ' + relative)
        if sha(checked_path(repository, relative)) != expected:
            raise ValueError('workstation profile source drift: ' + relative)
    for directory, expected in profile['source_sets'].items():
        directory_path = (repository / directory).resolve()
        if not directory_path.is_relative_to(repository) or not directory_path.is_dir():
            raise ValueError('workstation profile missing or escaping directory: ' + directory)
        selected = sorted(path.relative_to(repository).as_posix()
                          for path in directory_path.rglob('*') if path.is_file())
        if selected != expected or not set(expected).issubset(profile['source_sha256']):
            raise ValueError('workstation profile source inventory drift: ' + directory)
    baseline = load_baseline(root, profile['parent_baseline']['name'])
    if baseline.evidence() != profile['parent_baseline']:
        raise ValueError('workstation profile parent baseline changed')
    for reference in profile['references'].values():
        for relative, expected in reference['source_sha256'].items():
            if relative not in profile['source_sha256']:
                raise ValueError('workstation reference source is not locked: ' + relative)
            if len(expected) != 64:
                raise ValueError('invalid workstation reference hash: ' + relative)
    return profile


def prepare_ae350(root, output, stage, riscv_prefix=None, *, recording_api=False,
                  memory_profile='pl16k_8k', boot_rom_bytes=16384, business_owner=False,classic_runtime=False,worker_demo=False,headless_worker=False,media_worker=False,paired_worker=False):
    """Install maintained AE350 ROM only for the explicitly selected profile."""
    from tools.stage_ae350_firmware import stage_ae350_firmware
    root, output, stage = map(lambda path: Path(path).resolve(), (root, output, stage))
    baseline = load_baseline(root, 'resource_rework_route0')
    rom_path = 'firmware/boot.mem'
    historical = hashlib.sha256(baseline.read_bytes(rom_path)).hexdigest()
    if sha(stage / rom_path) != historical:
        raise ValueError('AE350 profile installation requires the unchanged parent ROM')
    evidence = output / AE350_DIRECTORY
    policy=AE350_POLICY
    if classic_runtime:
        if media_worker and (not recording_api or not business_owner or headless_worker or not worker_demo or memory_profile!='ilm64k_dlm64k' or boot_rom_bytes!=131072):
            raise ValueError('W-media requires explicit full shared-HCI/single-recording/local64/ROM128')
        if not media_worker and (not recording_api and not headless_worker) or not business_owner or memory_profile!='ilm64k_dlm64k'or boot_rom_bytes not in (98304,131072) or (headless_worker and (recording_api or not worker_demo)):
            raise ValueError('Classic runtime requires explicit local64/ROM96-or-ROM128/business composition')
        from tools.workstation_classic_runtime import build as build_runtime
        build=build_runtime(root,evidence,riscv_prefix,physical_rom_bytes=boot_rom_bytes,worker_demo=worker_demo,headless_worker=headless_worker,media_worker=media_worker,**({'paired_worker':True}if paired_worker else{}));policy=build['runtime_policy']
    else:
        build = stage_ae350_firmware(root, evidence, riscv_prefix, recording_api=recording_api,
            memory_profile=memory_profile, boot_rom_bytes=boot_rom_bytes, business_owner=business_owner)
    if sha(evidence / 'boot.mem') != build['rom_sha256']:
        raise ValueError('AE350 generated ROM changed before installation')
    shutil.copyfile(evidence / 'boot.mem', stage / rom_path)
    if sha(stage / rom_path) != build['rom_sha256']:
        raise ValueError('AE350 installed ROM identity differs from the build')
    return dict(policy=policy, project_rom_installed=True, evidence_directory=AE350_DIRECTORY,
                installed_rom=dict(path=rom_path, sha256=build['rom_sha256'],
                                   parent_baseline_sha256=historical),
                build=build, artifacts_sha256={path.relative_to(evidence).as_posix(): sha(path)
                                               for path in sorted(evidence.rglob('*')) if path.is_file()})


def _ae350_evidence(root, output, metadata, profile):
    selected = metadata.get('ae350_firmware', {})
    if (selected.get('policy') != profile['configuration']['ae350_firmware_policy'] or
            selected.get('project_rom_installed') is not True or
            selected.get('evidence_directory') != AE350_DIRECTORY):
        raise ValueError('workstation profile AE350 firmware policy changed')
    evidence = output / AE350_DIRECTORY
    actual = {source.relative_to(evidence).as_posix() for source in evidence.rglob('*') if source.is_file()}
    if actual != set(selected['artifacts_sha256']):
        raise ValueError('workstation profile AE350 evidence inventory changed')
    for relative, expected in selected['artifacts_sha256'].items():
        if sha(checked_path(evidence, relative)) != expected:
            raise ValueError('workstation profile AE350 evidence changed: ' + relative)
    build = selected['build']
    from tools.workstation_ae350_memory import verify_prepared
    verify_prepared(output / 'workstation/Prj1', build, profile['configuration'], sha)
    from tools.stage_ae350_firmware import selected_sources
    recording_api = specification(profile['name']).get('recording_enabled', False)
    business_owner=specification(profile['name']).get('business_owner_enabled',False)
    classic_runtime=specification(profile['name']).get('classic_runtime_enabled',False)
    if (build.get('recording_api_enabled') is not recording_api or
            build.get('business_owner_enabled',False) is not business_owner or
            (not classic_runtime and build.get('compiled_sources') != list(selected_sources(recording_api,business_owner)))):
        raise ValueError('workstation profile AE350 recording API selection changed')
    if classic_runtime:
        from tools.workstation_classic_runtime import verify_build
        verify_build(root,evidence,build,physical_rom_bytes=profile['configuration']['ae350_boot_rom_bytes'],
            **({'paired_worker':True}if specification(profile['name']).get('paired_worker',False)else{}))
    elif business_owner:
        proof='tools/ae350_ble_business_indirect_review.json'
        if (build.get('indirect_call_review',{}).get('source')!=proof or
            build['indirect_call_review'].get('sha256')!=sha(root/proof) or
            sha(evidence/'indirect_call_review.json')!=sha(root/proof) or
            'a138_ble_business_firmware_pump' not in build.get('call_chain_stack',{}).get('reachable_functions',[])):
            raise ValueError('workstation profile omitted actual C business/callback closure')
    if json.loads((evidence / 'build_metadata.json').read_text()) != build:
        raise ValueError('workstation profile AE350 build metadata changed')
    prefix = root.relative_to(root.parents[3]).as_posix() + '/'
    for relative, expected in build['input_sha256'].items():
        if profile['source_sha256'].get(prefix + relative) != expected:
            raise ValueError('workstation profile omitted or changed AE350 input: ' + relative)
    rom = selected['installed_rom']
    if (rom.get('path') != 'firmware/boot.mem' or rom.get('sha256') != build['rom_sha256'] or
            sha(checked_path(output / 'workstation/Prj1', rom['path'])) != rom['sha256'] or
            sha(evidence / 'boot.mem') != rom['sha256']):
        raise ValueError('workstation profile AE350 installed ROM changed')
    baseline = load_baseline(root, profile['parent_baseline']['name'])
    if rom['parent_baseline_sha256'] != hashlib.sha256(baseline.read_bytes(rom['path'])).hexdigest():
        raise ValueError('workstation profile AE350 historical ROM identity changed')
    return selected


def _artifact(root, output, metadata, profile):
    repository = root.parents[3]
    spec = specification(profile['name'])
    stage = output / 'workstation/Prj1'
    if spec.get('demo_role') is not None:
        from tools.workstation_usb_fifo_reset import verify_demo_selection
        verify_demo_selection(stage, profile['configuration'], metadata.get('demo_usb_fifo_write_reset'),
            metadata['enabled_inputs'], expected_configuration=spec['configuration'])
    from tools.workstation_ae350_clock_placement import verify_prepared as verify_ae350_clock
    ae350_clock_placement = verify_ae350_clock(root, stage, metadata.get('ae350_core_clock_placement'))
    from tools.workstation_ae350_rtc import verify_prepared as verify_ae350_rtc
    ae350_rtc = verify_ae350_rtc(root, stage, metadata.get('ae350_rtc'))
    if metadata.get('identity') != spec['integration_identity']:
        raise ValueError('workstation profile integration identity changed')
    providers = {row['provider'] for row in PROFILE_REGISTRY.values()}
    if [path for path in metadata['enabled_inputs'] if path in providers] != [spec['provider']]:
        raise ValueError('workstation profile selected compilation provider changed')
    if sha(output / 'parent_prepare_metadata.json') != metadata['parent_prepare_metadata_sha256']:
        raise ValueError('workstation profile parent metadata changed')
    parent = json.loads((output / 'parent_prepare_metadata.json').read_text())
    overlays = json.loads((output / 'workstation/resource_rework_overlays.json').read_text())
    # Recompute the runtime-only BLE adaptation from its source authority.
    # Metadata cannot promote an omitted live path or erase its replacement.
    from tools.workstation_bluetooth import SDC as bluetooth_sdc
    from tools.workstation_runtime_profile import bluetooth_constraints
    from tools.workstation_runtime_cdc import prepared_ble_reset_policy
    bluetooth = bluetooth_constraints(bluetooth_sdc,
        raw_common_reset=prepared_ble_reset_policy(stage)['raw_common_reset'])
    if metadata.get('runtime_audio', {}).get('bluetooth_cdc_adaptation') != bluetooth['evidence']:
        raise ValueError('workstation profile runtime BLE constraint policy changed')
    installed_sdc = (stage / 'constraints/custom_138k.sdc').read_text()
    paired_role=spec.get('paired_role')
    if paired_role is not None:
        from tools.workstation_task3_paired_board import verify_selection as verify_pair,restore_constraints as restore_pair_constraints
        verify_pair(root,stage,metadata.get('task3_paired',{}),paired_role)
        from tools.workstation_task3_paired_board import verify_constraints as verify_pair_constraints
        verify_pair_constraints(root,stage,metadata)
        installed_sdc=restore_pair_constraints(root,installed_sdc,metadata.get('task3_paired_sdc',{}))
    elif 'task3_paired' in metadata:
        raise ValueError('unselected profile cannot claim paired board wiring')
    if spec.get('tf_direct_enabled', False):
        from tools.workstation_task3_tf_direct import restore_constraints
        from tools.workstation_task3_tf_storage_selection import prepared_selection
        if metadata.get('task3_tf_direct_storage')!=prepared_selection(root,stage,profile['configuration']):
            raise ValueError('DIRECT TF actual CRC/cache source selection changed')
        if metadata.get('task3_tf_direct_cdc',{}).get('constraint_revision')!=profile['configuration']['tf_sdc_revision']:
            raise ValueError('DIRECT TF explicit SDC revision changed')
        installed_sdc = restore_constraints(root, installed_sdc, metadata.get('task3_tf_direct_cdc', {}))
    elif 'task3_tf_direct_cdc' in metadata or 'task3_tf_direct_storage' in metadata:
        raise ValueError('unselected profile cannot claim direct TF constraints')
    media_worker=spec.get('worker_media',False)
    if media_worker:
        if paired_role=='W':
            from tools.workstation_task3_w_paired_profile import restore_constraints
        else:
            from tools.workstation_task3_w_media_profile import restore_constraints
        installed_sdc=restore_constraints(installed_sdc,metadata['worker_media']['constraints'])
    audio_only=spec.get('worker_audio_only',False)
    if audio_only:
        from tools.workstation_worker_audio_only import restore_constraints
        installed_sdc=restore_constraints(installed_sdc,metadata['worker_audio_only']['constraints'])
    # Check the original complete bundles as well as the exact role-specific
    # retirement. Mixed queries retain every surviving endpoint in the output.
    if spec.get('demo_role') is not None:
        from tools.workstation_demo_policy import verify_constraints as verify_demo_constraints
        original_sdc = verify_demo_constraints(installed_sdc,
            metadata.get('demo_constraint_retirement'), spec['demo_role'],
            tf_playback_enabled=spec.get('tf_menu_enabled', False))
    else:
        original_sdc = installed_sdc
    staged_sdc = original_sdc.splitlines()
    if profile['name']==CPU_BUSINESS_NAME:
        from tools.workstation_cpu_business import verify_telemetry_reset_constraints
        verify_telemetry_reset_constraints((stage / 'constraints/custom_138k.sdc').read_text(),
                                          metadata.get('business_cpu_telemetry_reset_cdc'))
    local_panel_enabled = spec.get('local_panel_enabled', True)
    if metadata.get('peripherals', {}).get('local_panel_enabled', True) is not local_panel_enabled:
        raise ValueError('workstation profile local panel selection changed')
    if not local_panel_enabled:
        from tools.workstation_board_peripherals import local_panel_bundle
        from tools.workstation_custom_clocks import clock_bundle
        panel = local_panel_bundle(False)
        if metadata.get('local_panel') != panel:
            raise ValueError('workstation profile local panel retirement changed')
        if paired_role is not None:
            from tools.workstation_task3_paired_board import LCD_BEHAVIOR
            expected_lcd_behavior=LCD_BEHAVIOR
        else:expected_lcd_behavior=panel['output_behavior']
        if metadata.get('lcd_behavior') != expected_lcd_behavior:
            raise ValueError('workstation profile retired LCD output behavior changed')
        if (any('u_lcd' in line or 'lcd_pixel31m5' in line for line in staged_sdc) or
                'rtl/display_data/workstation_lcd.sv' in metadata['enabled_inputs'] or
                not installed_sdc.startswith(
                    clock_bundle(root, local_panel_enabled=False)['sdc'])):
            raise ValueError('workstation profile retired LCD source or clock remains')
    if (any(row['constraint'] in staged_sdc for row in bluetooth['evidence']['omitted']) or
            any(staged_sdc.count(line) != 1 for line in bluetooth['sdc'].splitlines()) or
            staged_sdc.count(bluetooth['evidence']['replacement']['constraint']) != 1):
        raise ValueError('workstation profile runtime BLE constraint installation changed')
    from tools.workstation_runtime_pcm_cdc import runtime_pcm_cdc_bundle
    pcm = runtime_pcm_cdc_bundle(root)
    if metadata.get('runtime_audio', {}).get('runtime_pcm_cdc') != {
            key: value for key, value in pcm.items() if key != 'sdc'}:
        raise ValueError('workstation profile runtime PCM constraint policy changed')
    if any(staged_sdc.count(line) != 1 for line in pcm['sdc'].splitlines()):
        raise ValueError('workstation profile runtime PCM constraint installation changed')
    from tools.workstation_delay_storage_provenance import source_bundle as delay_storage_source_bundle
    if metadata.get('runtime_audio', {}).get('delay_fifo_storage') != delay_storage_source_bundle(root):
        raise ValueError('workstation profile runtime delay FIFO storage policy changed')
    from tools.workstation_usb2_owner_reset import validate_installation as verify_usb2_owner_reset
    verify_usb2_owner_reset(root, metadata.get('runtime_audio', {}).get('usb2_owner_reset'),
                           (stage / 'constraints/custom_138k.sdc').read_text())
    from tools.workstation_recognition_policy import verify_adaptation
    recognition = dict(metadata.get('recognition', {}))
    constraint_evidence = recognition.pop('constraints', None)
    if recognition != recognition_metadata(profile):
        raise ValueError('workstation recognition capability selection changed')
    verify_adaptation(original_sdc,
                      constraint_evidence or {}, spec['recognition_enabled'],
                      tf_menu_enabled=spec.get('tf_menu_enabled', False))
    if metadata.get('runtime_audio', {}).get('top_provider') != spec['provider']:
        raise ValueError('workstation recognition compilation provider changed')
    from tools.workstation_runtime_counter import selection_evidence
    if selection_evidence(stage, metadata)['selection'] != 'compiled_native_balanced':
        raise ValueError('workstation runtime counter source selection changed')
    bindings = {}
    from tools.workstation_custom_board import source_snapshot
    if source_snapshot(root, metadata['source_snapshot_extra_inputs']) != metadata['source_snapshot_sha256']:
        raise ValueError('workstation profile complete source snapshot drift')
    expected_scan_window = dict(policy='native_admission_v1', enabled=True,
            provider='rtl/workstation/workstation_profile_hdmi.sv',
            compilation_provider=spec['provider'],
            provider_selection='included_with_runtime_macro',
            implementation='rtl/workstation/workstation_hdmi_display.sv',
            admission='rtl/display_data/workstation_ddr_scan_window.sv',
            provenance_sha256=sha(stage / 'rtl/workstation/workstation_hdmi_display.provenance.json'),
            physical_deadlines_verified=False, d01_complete=False, d04_complete=False)
    if audio_only:expected_scan_window=dict(policy='disabled_worker_audio_only_v1',enabled=False)
    if media_worker:expected_scan_window=dict(policy='disabled_worker_media_v1',enabled=False)
    if metadata.get('scan_window') != expected_scan_window:
        raise ValueError('workstation profile scan window source policy changed')

    def bind(destination, source):
        if source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted selected source: ' + source)
        previous = bindings.get(destination)
        if previous is not None and previous != source:
            raise ValueError('workstation profile ambiguous source: ' + destination)
        bindings[destination] = source

    prefix = root.relative_to(repository).as_posix() + '/'
    ble_raw_selected = spec.get('ble_recording_storage_enabled', False)
    business_selected=spec.get('business_owner_enabled',False)
    ble_raw_adaptation = None
    if ble_raw_selected:
        from tools.workstation_ble_recording_policy import metadata as ble_recording_metadata
        from tools.workstation_bluetooth_ddr import verify_prepared as verify_ble_raw
        if business_selected:
            from tools.workstation_cpu_business import metadata as ble_recording_metadata,verify_prepared as verify_ble_raw
        if media_worker:
            if paired_role=='W':
                from tools.workstation_task3_w_paired_profile import raw_metadata
            else:
                from tools.workstation_task3_w_media_profile import raw_metadata
            ble_recording_metadata=lambda:raw_metadata(root)
        selected = dict(metadata.get('ble_recording_storage', {}))
        ble_raw_adaptation = selected.pop('adaptation', None)
        if selected != ble_recording_metadata():
            raise ValueError('BLE raw DDR storage selection changed')
        if business_selected:
            verify_ble_raw(root,stage,ble_raw_adaptation,shared_hci=spec.get('hci_shared_owner_enabled',False))
        else:verify_ble_raw(root, stage, ble_raw_adaptation)
    elif 'ble_recording_storage' in metadata:
        raise ValueError('unselected profile cannot claim raw BLE DDR storage')
    if audio_only:
        from tools.workstation_cpu_business import verify_prepared as verify_hci_audio
        ble_raw_adaptation=metadata['worker_audio_only']['hci']
        verify_hci_audio(root,stage,ble_raw_adaptation,shared_hci=True,audio_only=True)
    if spec.get('recording_enabled',False):
        from tools.workstation_recording_policy import metadata as recording_metadata, verify_address_map, MAP_SOURCE, MAP_DESTINATION
        selected=dict(metadata.get('recording',{}));address_map=selected.pop('address_map',None)
        if media_worker:
            if paired_role=='W':
                from tools.workstation_task3_w_paired_profile import recording_metadata as media_recording_metadata
            else:
                from tools.workstation_task3_w_media_profile import recording_metadata as media_recording_metadata
            expected_recording=media_recording_metadata(root)
        else:expected_recording=recording_metadata(ble_raw_ddr=ble_raw_selected)
        if selected!=expected_recording:raise ValueError('recording source/capacity selection changed')
        verify_address_map(root,stage,address_map)
        bind(MAP_DESTINATION,prefix+MAP_SOURCE)
    elif 'recording' in metadata:
        raise ValueError('unselected profile cannot claim recording owner8')
    for source, expected in profile['source_sha256'].items():
        relative = source[len(prefix):] if source.startswith(prefix) else None
        if (relative in metadata['source_snapshot_sha256'] and
                metadata['source_snapshot_sha256'][relative] != expected):
            raise ValueError('workstation profile source snapshot drift: ' + source)
    for source, record in overlays.items():
        bind(record['destination'], prefix + source)
    for source, record in parent['composition']['sources'].items():
        bind(record['destination'], prefix + source)
    from tools.stage_usb_firmware import verify_usb2_cpu_ram_selection
    verify_usb2_cpu_ram_selection(root,stage,profile['configuration'],
                                  metadata.get('usb2_cpu_ram_selection'),firmware=metadata['firmware'])
    copies = metadata['copied_source_destinations']
    if set(copies) != set(metadata['copied_sources_sha256']) or len(set(copies.values())) != len(copies):
        raise ValueError('workstation profile copied source ownership changed')
    for source, target in copies.items():
        if not (business_selected and target=='rtl/bluetooth/workstation_bluetooth.sv'):
            bind(target, prefix + source)
        staged_hash = metadata['copied_sources_sha256'][source]
        if target=='rtl/usb2/workstation_usb2_cpu_bus.sv' and metadata.get('usb2_cpu_ram_selection'):
            staged_hash=metadata['usb2_cpu_ram_selection']['after']
        if business_selected and target=='rtl/bluetooth/workstation_bluetooth.sv':
            staged_hash=ble_raw_adaptation['copied'][target]['sha256']
        elif ble_raw_selected and target == 'rtl/bluetooth/workstation_bluetooth.sv':
            staged_hash = ble_raw_adaptation['output_sha256']['workstation_bluetooth.sv']
        if paired_role is not None and target=='rtl/workstation/gw138k_push_workstation_top.v':
            from tools.workstation_task3_paired_board import inverse_top as inverse_common,role_helper,digest as pair_digest
            actual_top=(stage/target).read_text()
            parent_top=role_helper(paired_role).inverse_top(root,inverse_common(root,actual_top,paired_role))
            if (pair_digest(parent_top)!=metadata['copied_sources_sha256'][source] or
                    parent_top!=(root/source).read_text()):
                raise ValueError('paired top exact inverse differs from maintained source')
            staged_hash=metadata['task3_paired']['selected_top_sha256']
        if (metadata['copied_sources_sha256'][source] != profile['source_sha256'][prefix + source] or
                sha(checked_path(stage, target)) != staged_hash):
            raise ValueError('workstation profile copied source drift: ' + source)
    if business_selected:
        for target,record in ble_raw_adaptation['copied'].items():bind(target,prefix+record['source'])
    usage = {source: 'compiled_source' if target in metadata['enabled_inputs'] else 'staged_dependency'
             for target, source in bindings.items()}
    for source in metadata['firmware']['input_sha256']:
        if prefix + source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted firmware source: ' + source)
        usage[prefix + source] = 'usb_firmware_build_input'
    for source in metadata['bluetooth']['source_snapshot_sha256']:
        if source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted BLE source: ' + source)
        usage[source] = 'ble_build_input'
    for source in metadata['peripherals']['reviewed_sources']:
        if source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted peripheral source: ' + source)

    baseline = load_baseline(root, profile['parent_baseline']['name'])
    inputs = {}
    for relative in metadata['enabled_inputs']:
        source = checked_path(stage, relative)
        expected = metadata['staged_input_sha256'].get(relative)
        if sha(source) != expected:
            raise ValueError('workstation profile prepared input drift: ' + relative)
        record = dict(sha256=expected)
        if relative in bindings:
            origin = bindings[relative]
            record.update(origin='versioned_source', source=origin,
                          source_sha256=profile['source_sha256'][origin],
                          adapted=expected != profile['source_sha256'][origin])
        elif relative in baseline.inputs:
            original = hashlib.sha256(baseline.read_bytes(relative)).hexdigest()
            record.update(origin='locked_parent_baseline', source=relative,
                          source_sha256=original, adapted=expected != original)
            equivalent = metadata['unchanged_parent_inputs'].get(relative)
            if equivalent:
                owner = prefix + equivalent['source']
                if (profile['source_sha256'].get(owner) != original or
                        equivalent['sha256'] != original or expected != original):
                    raise ValueError('workstation profile unchanged parent equivalence drift: ' + relative)
                record['versioned_equivalent'] = dict(source=owner, sha256=original)
        elif relative in metadata['bluetooth']['sources']:
            record.update(origin='checked_ble_adaptation',
                          source_sha256=metadata['bluetooth']['source_snapshot_sha256'])
        elif relative in ('constraints/custom_138k.cst', 'constraints/custom_138k.sdc'):
            record.update(origin='reviewed_board_constraint_composition',
                          source_sha256={name: value for name, value in profile['source_sha256'].items()
                                         if '/boards/custom_138k/' in name or '/tools/' in name})
        else:
            raise ValueError('workstation profile has no input provenance: ' + relative)
        inputs[relative] = record

    reuse = {}
    for name, reference in profile['references'].items():
        rows = {}
        for source, historical in reference['source_sha256'].items():
            destinations = [target for target, origin in bindings.items() if origin == source]
            rows[source] = dict(reference_sha256=historical,
                                current_sha256=profile['source_sha256'][source],
                                same_bytes_as_reference=profile['source_sha256'][source] == historical,
                                selected_destinations=destinations,
                                selection=usage.get(source, 'reference_or_preparation_input'))
        reuse[name] = dict(user_code=reference['user_code'], scope=reference['scope'],
                           evidence=reference['evidence'], files=rows)
    config_hash = sha(root / spec['config'])
    ae350 = _ae350_evidence(root, output, metadata, profile)
    if spec.get('classic_runtime_enabled',False):
        from tools.workstation_classic_runtime import verify_selection
        verify_selection(root,stage,output,metadata.get('classic_runtime',{}),physical_rom_bytes=profile['configuration']['ae350_boot_rom_bytes'],selected_provider=spec['provider'] if spec.get('demo_role')=='W' else None,headless_worker=audio_only,media_worker=media_worker,
            **({'paired_worker':True}if spec.get('paired_worker',False)else{}))
        if media_worker:
            if paired_role=='W':
                from tools.workstation_task3_w_paired_profile import cnn_memory_configuration
            else:
                from tools.workstation_task3_w_media_profile import cnn_memory_configuration
            memory=dict(metadata['classic_runtime']['worker_media_source']['selected_CNN_memory'])
            if memory!=cnn_memory_configuration(profile['configuration']):
                raise ValueError('W CNN actual native memory selection does not match profile configuration')
    elif 'classic_runtime'in metadata:
        raise ValueError('unselected profile cannot claim Classic runtime composition')
    bluetooth = metadata['bluetooth']
    if bluetooth.get('rom_path_policy') != 'stage_relative':
        raise ValueError('workstation runtime BLE ROM path policy changed')
    ble_inputs = bluetooth.get('generated_input_provenance', {})
    header_path, patch_path = 'native_bluetooth/patch_path.vh', 'native_bluetooth/rtl8723ds_patch.mem'
    if set(ble_inputs) != {header_path, patch_path}:
        raise ValueError('workstation runtime BLE generated input inventory changed')
    for relative, record in ble_inputs.items():
        if sha(checked_path(stage, relative)) != record['sha256']:
            raise ValueError('workstation runtime BLE generated input changed: ' + relative)
    header, patch = ble_inputs[header_path], ble_inputs[patch_path]
    if (header.get('origin') != 'checked_ble_rom_path_header' or
            header.get('generator') != 'tools/workstation_bluetooth.py' or
            header.get('generator_sha256') != profile['source_sha256'][prefix + header['generator']] or
            header.get('target') != patch_path or header.get('target_path') != patch_path or
            (stage / header_path).read_text() != '`define WORKSTATION_BLE_PATCH_FILE ' + json.dumps(patch_path) + '\n'):
        raise ValueError('workstation runtime BLE header provenance changed')
    if (patch.get('origin') != 'locked_ble_vendor_patch' or
            patch.get('source') != 'example/RTL8723DS/vendor/rtl8723ds_ble/rtl8723ds_patch.mem' or
            profile['source_sha256'].get(patch['source']) != patch.get('source_sha256') or
            patch['sha256'] != patch['source_sha256']):
        raise ValueError('workstation runtime BLE patch provenance changed')
    candidate_hash = identity_digest(dict(profile_sha256=config_hash,
                                          staged_input_sha256=metadata['staged_input_sha256'],
                                          source_snapshot_sha256=metadata['source_snapshot_sha256'],
                                          firmware=metadata['firmware'], ae350_firmware=ae350))
    return dict(schema=1, profile=profile['name'], revision=profile['revision'], profile_source=spec['config'], profile_sha256=config_hash,
                candidate_identity=profile['name'] + '-' + candidate_hash[:16], candidate_input_sha256=candidate_hash,
                configuration=profile['configuration'], parent_baseline=profile['parent_baseline'],
                enabled_inputs=inputs, reference_reuse=reuse, features=profile['features'],
                staged_input_sha256=metadata['staged_input_sha256'],
                source_sha256=profile['source_sha256'],
                source_snapshot_sha256=metadata['source_snapshot_sha256'],
                selected_source_owners={target: dict(source=owner,
                    sha256=profile['source_sha256'][owner],
                    selection='compiled_source' if target in inputs else 'staged_dependency')
                    for target, owner in bindings.items()},
                firmware=metadata['firmware'],
                ae350_firmware=ae350,
                **({'classic_runtime':metadata['classic_runtime']}if spec.get('classic_runtime_enabled',False)else{}),
                scan_window=metadata['scan_window'],
                runtime_audio=metadata.get('runtime_audio'), recognition=metadata['recognition'],
                **({'task3_paired':metadata['task3_paired']}if paired_role is not None else{}),
                ae350_core_clock_placement=ae350_clock_placement, ae350_rtc=ae350_rtc,
                **({'recording':metadata['recording']} if spec.get('recording_enabled',False) else {}),
                **({'ble_recording_storage':metadata['ble_recording_storage']} if ble_raw_selected else {}),
                generated_data_inputs={**ble_inputs, 'firmware/boot.mem': dict(origin='maintained_ae350_firmware',
                    sha256=ae350['installed_rom']['sha256'], source_sha256=ae350['build']['input_sha256'],
                    tool_versions=ae350['build']['tool_versions'], capacity=ae350['build']['capacity'])},
                integration_metadata_sha256=identity_digest({key: value for key, value in metadata.items()
                                                             if key != 'workstation_profile'}),
                resource_overlays_sha256=sha(output / 'workstation/resource_rework_overlays.json'),
                adaptations=dict(resource_timing=parent['timing_structure'],
                                 native_timing=metadata['native_timing_adaptations'],
                                 video=metadata['hdmi'], bluetooth=metadata['bluetooth']),
                validation_stage='prepare_only', synthesis_passed=False, physical_gates_passed=False,
                hardware_tested=False, sram_programmed=False, flash_programmed=False,
                deployment_allowed=False, bitstream_sha256=None)


def attach(root, output, metadata, name):
    root, output = Path(root).resolve(), Path(output).resolve()
    profile = load(root, name, allow_high_speed=metadata['high_speed_allowed'],
                   hdmi_mode=metadata['hdmi']['mode'])
    artifact = _artifact(root, output, metadata, profile)
    destination = output / ARTIFACT
    destination.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    metadata['workstation_profile'] = dict(name=profile['name'], candidate_identity=artifact['candidate_identity'],
                                         configuration_sha256=artifact['profile_sha256'],
                                         artifact=ARTIFACT, artifact_sha256=sha(destination))
    return metadata['workstation_profile']


def verify(root, output):
    """Recheck source lock, compiled selection, staged closure and feature matrix."""
    root, output = Path(root).resolve(), Path(output).resolve()
    metadata = json.loads((output / 'integration_inputs.json').read_text())
    selected = metadata.get('workstation_profile', {})
    profile = load(root, selected.get('name'), allow_high_speed=metadata['high_speed_allowed'],
                   hdmi_mode=metadata['hdmi']['mode'])
    if selected.get('artifact') != ARTIFACT or selected.get('artifact_sha256') != sha(output / ARTIFACT):
        raise ValueError('workstation profile artifact changed')
    artifact = json.loads((output / ARTIFACT).read_text())
    if artifact != _artifact(root, output, metadata, profile):
        raise ValueError('workstation profile manifest changed')
    if (selected.get('configuration_sha256') != artifact['profile_sha256'] or
            selected.get('candidate_identity') != artifact['candidate_identity']):
        raise ValueError('workstation profile selection changed')
    stage = output / 'workstation/Prj1'
    enabled = [entry.get('path') for entry in ElementTree.parse(stage / 'Prj1.gprj').find('FileList')
               if entry.get('enable') == '1']
    if enabled != metadata['enabled_inputs'] or len(enabled) != len(set(enabled)):
        raise ValueError('workstation profile compilation selection changed')
    actual = {source.relative_to(stage).as_posix() for source in stage.rglob('*')
              if source.is_file() and 'impl' not in source.relative_to(stage).parts}
    if actual != set(metadata['staged_input_sha256']):
        raise ValueError('workstation profile staged file inventory changed')
    for relative, expected in metadata['staged_input_sha256'].items():
        if sha(checked_path(stage, relative)) != expected:
            raise ValueError('workstation profile staged closure changed: ' + relative)
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'verify'))
    parser.add_argument('candidate', type=Path, nargs='?')
    parser.add_argument('--profile', choices=tuple(PROFILE_REGISTRY),
                        help='Named source policy for check, or expected candidate policy for verify')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == 'check':
        if args.candidate is not None:
            parser.error('check does not take a candidate')
        selected_name = args.profile or NAME
        profile = load(root, selected_name)
        result = dict(profile=profile['name'], source_files=len(profile['source_sha256']),
                      configuration_sha256=sha(root / specification(selected_name)['config']), validation_stage='source_lock_only')
    else:
        if args.candidate is None:
            parser.error('verify requires a prepared candidate directory')
        artifact = verify(root, args.candidate)
        if args.profile is not None and artifact['profile'] != args.profile:
            parser.error('candidate does not match the expected workstation profile')
        result = dict(profile=artifact['profile'], candidate_identity=artifact['candidate_identity'],
                      enabled_inputs=len(artifact['enabled_inputs']), validation_stage='prepare_only')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
