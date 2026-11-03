"""Explicit M HDMI status composition and bounded observation CDC contracts."""
import hashlib

POLICY='usb_owner_link_and_render_voice_snapshot_v1'
SOURCES=('rtl/usb2/workstation_usb2_display_status.sv',
         'rtl/display_data/workstation_usb_status_panel.sv')
OLD_RELEASE_BLOCK=(
    'set_false_path -to [get_pins {u_native_usb/host/usb/bridge/ulpi_release_q_*/CLEAR}]\n'
    'set_max_delay 2.000 -from [get_pins {u_native_usb/host/usb/bridge/ulpi_release_q_0_s*/Q}] '
    '-to [get_pins {u_native_usb/host/usb/bridge/ulpi_release_q_1_s*/D}]\n')
ALIAS_NOTE='# M5 shared ULPI release: actual status-mailbox stages are constrained below.\n'


def constraints():
    lines=['# Read-only M USB status; held snapshots, no event/audio backpressure.']
    for path in ('u_usb_display_status/link_cdc','u_video/u_usb_status_panel/u_status_cdc'):
        lines += [
            f'set_max_delay 10.000 -from [get_regs {{{path}/held_data*}}] -to [get_regs {{{path}/destination_data*}}]',
            f'set_false_path -hold -from [get_regs {{{path}/held_data*}}] -to [get_regs {{{path}/destination_data*}}]',
            f'set_false_path -to [get_pins {{{path}/req_meta*/D {path}/ack_meta*/D}}]',
            f'set_max_delay 2.000 -from [get_regs {{{path}/req_meta* {path}/ack_meta*}}] -to [get_regs {{{path}/req_sync* {path}/ack_sync*}}]',
            f'set_false_path -to [get_pins {{{path}/source_release*/CLEAR {path}/destination_release*/CLEAR}}]',
        ]
        for release in ('source_release','destination_release'):
            for stage in range(2):
                lines.append(f'set_max_delay 2.000 -from [get_pins {{{path}/{release}_{stage}_s*/Q}}] '
                             f'-to [get_pins {{{path}/{release}_{stage+1}_s*/D}}]')
    path='u_usb_display_status'
    lines += [f'set_false_path -to [get_pins {{{path}/link_meta*/D}}]',
              f'set_max_delay 2.000 -from [get_regs {{{path}/link_meta*}}] -to [get_regs {{{path}/link_sync*}}]',
              f'set_false_path -to [get_pins {{{path}/ulpi_release*/CLEAR}}]']
    lines.append(f'set_max_delay 2.000 -from [get_pins {{{path}/ulpi_release_0_s*/Q}}] '
                 f'-to [get_pins {{{path}/ulpi_release_1_s*/D}}]')
    return '\n'.join(lines)+'\n'


def evidence():
    return dict(policy=POLICY,sources=list(SOURCES),owner='u_native_usb/input_owner',
        link_source='actual_host_levels_synchronized_snapshot_with_100ms_ULPI_expiry',
        status_source_clock='usb_48m',destination_clock='ddr_ui100',
        voice_source='shared_render_meta[159:128]',voice_semantics='current_render_cache_active_mask_popcount',
        freeze='renderer_start',pixel_path='renderer_to_existing_DDR_frame_writer',
        audio_backpressure=False,new_DDR_allocation=False,
        sdc_sha256=hashlib.sha256(constraints().encode()).hexdigest(),
        physical_cdc_verified=False,hardware_tested=False)


def install(sdc):
    if sdc.count(OLD_RELEASE_BLOCK)!=1 or ALIAS_NOTE in sdc:
        raise ValueError('M USB status parent release constraint anchor changed')
    installed=sdc.replace(OLD_RELEASE_BLOCK,ALIAS_NOTE)+constraints()
    selected=evidence()
    selected['reset_alias_rebinding']=dict(
        policy='exact_old_ULPI_release_to_proven_shared_mailbox_stages_v1',
        parent_sdc_sha256=hashlib.sha256(sdc.encode()).hexdigest(),
        installed_sdc_sha256=hashlib.sha256(installed.encode()).hexdigest())
    return installed,selected


def verify(sdc,selected):
    selected=dict(selected or {})
    binding=selected.pop('reset_alias_rebinding',{})
    if (selected!=evidence() or sdc.count(constraints())!=1 or
            not sdc.endswith(constraints()) or sdc.count(ALIAS_NOTE)!=1 or
            set(binding)!={'policy','parent_sdc_sha256','installed_sdc_sha256'} or
            binding.get('policy')!='exact_old_ULPI_release_to_proven_shared_mailbox_stages_v1' or
            binding.get('installed_sdc_sha256')!=hashlib.sha256(sdc.encode()).hexdigest()):
        raise ValueError('M USB status composition/CDC policy changed')
    restored=sdc[:-len(constraints())].replace(ALIAS_NOTE,OLD_RELEASE_BLOCK)
    if binding.get('parent_sdc_sha256')!=hashlib.sha256(restored.encode()).hexdigest():
        raise ValueError('M USB status parent constraint inverse changed')
    return restored
