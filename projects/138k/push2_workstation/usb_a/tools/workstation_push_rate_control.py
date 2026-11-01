"""Explicit M Session-key admission transport; no clock-control owner here."""
import hashlib

POLICY = 'push_session_committed_toggle_generation_v1'


def constraints():
    lines = ['# M Session control: bounded held-data CDC, no audio FIFO command queue.']
    mailboxes = ('u_push_rate_bridge/window_cdc', 'u_video/u_rate_status/status_cdc')
    for path in mailboxes:
        lines += [
            f'set_max_delay 10.000 -from [get_regs {{{path}/held_data*}}] -to [get_regs {{{path}/destination_data*}}]',
            f'set_false_path -hold -from [get_regs {{{path}/held_data*}}] -to [get_regs {{{path}/destination_data*}}]',
            f'set_false_path -to [get_pins {{{path}/req_meta*/D {path}/ack_meta*/D}}]',
            f'set_false_path -to [get_pins {{{path}/source_release*/CLEAR {path}/destination_release*/CLEAR}}]',
        ]
    path = 'u_push_rate_bridge'
    lines += [
        f'set_max_delay 10.000 -from [get_regs {{{path}/held_generation*}}] -to [get_regs {{{path}/service_generation_o*}}]',
        f'set_false_path -hold -from [get_regs {{{path}/held_generation*}}] -to [get_regs {{{path}/service_generation_o*}}]',
        f'set_false_path -to [get_pins {{{path}/req_meta*/D {path}/ack_meta*/D}}]',
        f'set_false_path -to [get_pins {{{path}/usb_release*/CLEAR {path}/control_release*/CLEAR}}]',
    ]
    return '\n'.join(lines) + '\n'


def evidence():
    return dict(policy=POLICY, session_cc=51, release_triggers=False,
        target='inverse_actual_committed_rate', busy_policy='consume_reject_never_queue',
        fault_policy='reject_push_existing_apb_recover', stale_generation='reject',
        clock_owner='u_clock_service', display='frame_frozen_actual_status_final_scanout',
        sdc_sha256=hashlib.sha256(constraints().encode()).hexdigest(),
        physical_cdc_verified=False, hardware_tested=False)


def verify(sdc, selected):
    if selected != evidence() or sdc.count(constraints()) != 1:
        raise ValueError('Push Session rate control policy/CDC constraints changed')
