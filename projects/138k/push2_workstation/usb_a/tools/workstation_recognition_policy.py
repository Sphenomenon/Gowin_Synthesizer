"""Exact retirement of constraints whose entire CNN endpoint has been removed.

The enabled policy is byte-preserving. Unknown or mixed CNN queries fail closed;
this is not a wildcard exemption or a change to retained clock/CDC limits.
"""
import hashlib

PROVIDER = 'rtl/workstation/workstation_profile_no_cnn_runtime.sv'
ENDPOINT_PREFIXES = ('u_music/', 'u_song_command_cdc/', 'u_score_push_cdc/', 'u_native_usb/input_owner/analysis_done_meta')
RETIRED_LINES = (
    'set_false_path -to [get_pins {u_music/u_trace_cdc/meta*/D}]',
    'set_max_delay 20.000 -from [get_regs {u_song_command_cdc/held_data*}] -to [get_regs {u_song_command_cdc/destination_data*}]',
    'set_false_path -hold -from [get_regs {u_song_command_cdc/held_data*}] -to [get_regs {u_song_command_cdc/destination_data*}]',
    'set_false_path -to [get_pins {u_song_command_cdc/req_meta*/D u_song_command_cdc/ack_meta*/D u_song_command_cdc/source_release*/CLEAR u_song_command_cdc/destination_release*/CLEAR}]',
    'set_max_delay 10.000 -from [get_regs {u_music/u_ddr_req_cdc/read_gray* u_music/u_ddr_req_cdc/read_binary_4*}] -to [get_regs {u_music/u_ddr_req_cdc/read_gray_meta*}]',
    'set_false_path -hold -from [get_regs {u_music/u_ddr_req_cdc/read_gray* u_music/u_ddr_req_cdc/read_binary_4*}] -to [get_regs {u_music/u_ddr_req_cdc/read_gray_meta*}]',
    'set_max_delay 10.000 -from [get_regs {u_music/u_ddr_req_cdc/write_gray*}] -to [get_regs {u_music/u_ddr_req_cdc/write_gray_meta*}]',
    'set_false_path -hold -from [get_regs {u_music/u_ddr_req_cdc/write_gray*}] -to [get_regs {u_music/u_ddr_req_cdc/write_gray_meta*}]',
    'set_max_delay 10.000 -from [get_regs {u_music/u_ddr_rsp_cdc/read_gray* u_music/u_ddr_rsp_cdc/read_binary_2*}] -to [get_regs {u_music/u_ddr_rsp_cdc/read_gray_meta*}]',
    'set_false_path -hold -from [get_regs {u_music/u_ddr_rsp_cdc/read_gray* u_music/u_ddr_rsp_cdc/read_binary_2*}] -to [get_regs {u_music/u_ddr_rsp_cdc/read_gray_meta*}]',
    'set_max_delay 10.000 -from [get_regs {u_music/u_ddr_rsp_cdc/write_gray*}] -to [get_regs {u_music/u_ddr_rsp_cdc/write_gray_meta*}]',
    'set_false_path -hold -from [get_regs {u_music/u_ddr_rsp_cdc/write_gray*}] -to [get_regs {u_music/u_ddr_rsp_cdc/write_gray_meta*}]',
    'set_max_delay 10.000 -from [get_regs {u_score_push_cdc/read_gray* u_score_push_cdc/read_binary_2*}] -to [get_regs {u_score_push_cdc/read_gray_meta*}]',
    'set_false_path -hold -from [get_regs {u_score_push_cdc/read_gray* u_score_push_cdc/read_binary_2*}] -to [get_regs {u_score_push_cdc/read_gray_meta*}]',
    'set_max_delay 10.000 -from [get_regs {u_score_push_cdc/write_gray*}] -to [get_regs {u_score_push_cdc/write_gray_meta*}]',
    'set_false_path -hold -from [get_regs {u_score_push_cdc/write_gray*}] -to [get_regs {u_score_push_cdc/write_gray_meta*}]',
    'set_false_path -to [get_pins {u_native_usb/input_owner/analysis_done_meta*/D}]',
    'set_false_path -to [get_pins {u_music/model_memory_meta*/D}]',
    'set_max_delay 2.000 -from [get_regs {u_music/model_memory_meta*}] -to [get_regs {u_music/model_memory_ready*}]',
)
RETIRED_SUBSET_SHA256 = 'd1eb3a7588f267fdf32dc7e032bf0b5bda6891f7eaab29a1df5e76ef90e93689'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def adapt_constraints(sdc, enabled):
    lines = sdc.splitlines(keepends=True)
    retired = []
    if not enabled:
        if digest(''.join(row+'\n' for row in RETIRED_LINES)) != RETIRED_SUBSET_SHA256:
            raise ValueError('recognition retired constraint identity changed')
        for row in RETIRED_LINES:
            if lines.count(row+'\n') != 1:
                raise ValueError('recognition constraint anchor missing/changed/duplicated: '+row)
        for index, row in enumerate(lines):
            if any(prefix in row for prefix in ENDPOINT_PREFIXES):
                if row.rstrip('\n') not in RETIRED_LINES:
                    raise ValueError('unknown or mixed recognition constraint: '+row)
                retired.append(dict(line=row, line_number=index+1, sha256=digest(row)))
        selected = ''.join(row for row in lines if row.rstrip('\n') not in RETIRED_LINES)
    else:
        selected = sdc
    return selected, dict(enabled=enabled, input_sha256=digest(sdc), output_sha256=digest(selected),
        retired_subset_sha256=RETIRED_SUBSET_SHA256 if not enabled else None,
        retired=retired, retained_constraints_unchanged=True, physical_cdc_verified=False)


def verify_adaptation(sdc, evidence, enabled):
    if evidence.get('enabled') is not enabled or evidence.get('output_sha256') != digest(sdc):
        raise ValueError('recognition constraint selection changed')
    original = sdc.splitlines(keepends=True)
    for record in evidence.get('retired', []):
        index = record['line_number']-1
        if index < 0 or index > len(original):
            raise ValueError('recognition constraint position changed')
        original.insert(index, record['line'])
    selected, expected = adapt_constraints(''.join(original), enabled)
    if selected != sdc or expected != evidence:
        raise ValueError('recognition constraint retirement evidence changed')
