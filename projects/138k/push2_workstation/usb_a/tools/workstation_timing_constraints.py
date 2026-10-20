"""Targeted CDC bounds for the existing full83 workstation structures.

No clocks are relaxed. Gray pointer flight is bounded by the shortest relevant period;
only metastability entry D pins and async reset entry pins are exempted.
"""


def constraints(diagnostic_cdc=True):
    text = '''
# Workstation timing constraints: bounded CDC entries and PLL control routes.
# DDR-only UART status inputs are sampled in a local two-stage receiver.
set_false_path -to [get_pins {u_music/u_trace_cdc/meta*/D}]
# USB reset enters the audio domain only through the local release chain.
set_false_path -to [get_pins {u_push/audio_release*/CLEAR}]
# TF diagnostic level flags: audio -> 50MHz, explicit two-stage receivers.
set_false_path -to [get_pins {tf_format_meta50*/D tf_source_meta50*/D}]
# USB lifecycle: asynchronous assertion enters explicit local release chains.
# Preserve all later release-Q -> business reset and same-clock paths.
set_false_path -to [get_pins {u_push/queue_release*/CLEAR u_push/queue_write_release*/CLEAR u_push/online_sync*/CLEAR u_push/panic_sync*/CLEAR u_push/defaults_sync*/CLEAR}]
set_false_path -to [get_pins {u_push/settled_sync_0*/D u_push/queue_write_release_0*/D u_push/panic_sync_0*/D u_push/defaults_sync_0*/D}]
# TF playback bridge: existing first-stage level/held-rate samplers. Their
# second stages and DAC consumers retain normal audio setup/hold checks.
set_false_path -to [get_pins {u_tf_audio/rate_meta*/D u_tf_audio/format_meta*/D u_tf_audio/unsupported_meta*/D u_tf_audio/clear_meta*/D u_tf_audio/hold_meta*/D}]
# USB song command: the source holds the word through the ACK round trip.
set_max_delay 20.000 -from [get_regs {u_song_command_cdc/held_data*}] -to [get_regs {u_song_command_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_song_command_cdc/held_data*}] -to [get_regs {u_song_command_cdc/destination_data*}]
set_false_path -to [get_pins {u_song_command_cdc/req_meta*/D u_song_command_cdc/ack_meta*/D u_song_command_cdc/source_release*/CLEAR u_song_command_cdc/destination_release*/CLEAR}]
'''
    # All these are existing dual-clock FIFOs. The read Gray MSB aliases the
    # registered binary MSB after synthesis. Do not exempt binary buses.
    for instance, msb, bound in [
        ('u_managed/u_audio/u_workstation/effects/delay_stage/u_write_fifo', 9, 10),
        ('u_managed/u_audio/u_workstation/effects/delay_stage/u_read_fifo', 9, 10),
        ('u_music/u_ddr_req_cdc', 4, 10),
        ('u_music/u_ddr_rsp_cdc', 2, 10),
        ('u_score_push_cdc', 2, 10),
        ('u_playlist_bridge/fifo', 2, 10),
    ]:
        for source, target in [
            (f'{instance}/read_gray* {instance}/read_binary_{msb}*', f'{instance}/read_gray_meta*'),
            (f'{instance}/write_gray*', f'{instance}/write_gray_meta*'),
        ]:
            text += f'set_max_delay {bound}.000 -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
            text += f'set_false_path -hold -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
    # TF's FIFO has its own clear-to-zero pointer gating; the existing route
    # auditor proves that gate selects the pointer or zero, never binary data.
    for source, target in [
        ('u_tf_audio/u_pcm_cdc/rd_gray* u_tf_audio/u_pcm_cdc/rd_bin_4*', 'u_tf_audio/u_pcm_cdc/rd_gray_w1*'),
        ('u_tf_audio/u_pcm_cdc/wr_gray*', 'u_tf_audio/u_pcm_cdc/wr_gray_r1*'),
    ]:
        text += f'set_max_delay 10.000 -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
        text += f'set_false_path -hold -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
    # Existing TF byte-FIFO crossings (50MHz <-> DDR UI100).
    for instance in ['u_tf_audio/u_path/u_capture_fifo', 'u_tf_audio/u_path/u_playback_fifo']:
        for source, target in [
            (f'{instance}/rd_gray* {instance}/rd_bin_12*', f'{instance}/rd_gray_w1*'),
            (f'{instance}/wr_gray*', f'{instance}/wr_gray_r1*'),
        ]:
            text += f'set_max_delay 10.000 -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
            text += f'set_false_path -hold -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
    # The two byte FIFOs share restart; synthesis merges the DDR first samplers.
    # The 50MHz clear sampler shares the source clock and keeps normal checks.
    text += 'set_false_path -to [get_pins {u_tf_audio/u_path/u_capture_fifo/clear_rd_meta*/D}]\n'
    text += """
# DDR status samplers, plus the stable file-size word accompanying valid.
set_false_path -to [get_pins {u_tf_audio/u_path/file_size_valid_meta*/D u_tf_audio/u_path/pb_meta*/D u_tf_audio/u_path/pb_done_meta*/D u_push/analysis_done_meta*/D}]
set_max_delay 10.000 -from [get_regs {u_tf_audio/u_path/u_dma/staged_file_size*}] -to [get_regs {u_tf_audio/u_path/file_size_meta*}]
set_false_path -hold -from [get_regs {u_tf_audio/u_path/u_dma/staged_file_size*}] -to [get_regs {u_tf_audio/u_path/file_size_meta*}]
"""
    if not diagnostic_cdc:
        text=text.replace('set_false_path -to [get_pins {u_music/u_trace_cdc/meta*/D}]\n','')
    return text


def physical_constraints():
    """Internal nonexclusive helper locality; no I/O or PLL site changes."""
    return '''
// Workstation video PLL helper locality; no I/O/pin or PLL configuration change.
// Reuse the existing reference-helper region; constrain only dynamic pin drivers.
GROUP workstation_reference_pll_helper = { "u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/RomDreg*" "u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/state*" "u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/enable_r*" "u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/pll_reset*" };
GRP_LOC workstation_reference_pll_helper R[100:108]C[24:44];
'''


def timing_reports():
    """Global reports include asynchronous paths omitted from clock summaries."""
    text='\n# Timing experiment: reports only; preserve all clocks and exceptions.\n'
    for clock in ['clk_50m','audio_76m8','usb_48m','ddr_ui100','video_pixel148']:
        for kind in ['setup','hold']:
            text+=f'report_timing -{kind} -from_clock [get_clocks {{{clock}}}] -to_clock [get_clocks {{{clock}}}] -max_paths 50\n'
    for kind in ['setup','hold','recovery','removal']:
        text+=f'report_timing -{kind} -max_paths 100\n'
    return text


def gray_write_alias_constraints():
    """Match only synthesized MSB aliases of the two 512-word delay FIFOs.

    Gray's MSB equals binary's MSB. Gowin may retain the binary register name;
    the original write_gray wildcard then misses that one source. Keep the
    existing 10 ns flight bound and hold exception, with a bit-specific target.
    """
    text = "\n# Registered Gray MSB aliases, proven against the routed synchronizers.\n"
    for fifo in ('u_write_fifo', 'u_read_fifo'):
        instance = 'u_managed/u_audio/u_workstation/effects/delay_stage/' + fifo
        source = instance + '/write_binary_9*'
        target = instance + '/write_gray_meta_9*'
        text += f'set_max_delay 10.000 -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
        text += f'set_false_path -hold -from [get_regs {{{source}}}] -to [get_regs {{{target}}}]\n'
    return text
