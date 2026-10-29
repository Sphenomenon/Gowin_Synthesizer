# SUG940-2.0.1E PDF66-69: explicit -master_clock and -add are supported.
# Both raw oscillators run simultaneously; only their DCS output clocks exclude
# each other. Do not put50MHz/raw clocks in a broad asynchronous clock group.
create_clock -name reference50 -period 20.000 [get_ports {clk_50mhz}]
create_clock -name raw48 -period 81.380208 [get_ports {clk_12m288}]
create_clock -name raw44 -period 59.051398 [get_ports {clk_16m9344}]
create_generated_clock -name selected48 -source [get_ports {clk_12m288}] -master_clock raw48 -divide_by 1 [get_pins {audio_domain/selector/CLKOUT}]
create_generated_clock -name selected44 -source [get_ports {clk_16m9344}] -master_clock raw44 -divide_by 1 -add [get_pins {audio_domain/selector/CLKOUT}]
# Scope only the two impossible cross-mode relations. The independent CDC
# bounds below remain effective and are verified from setup timing tables.
set_false_path -from [get_clocks {selected48}] -to [get_clocks {selected44}]
set_false_path -from [get_clocks {selected44}] -to [get_clocks {selected48}]

# Registered Gray first-stage data bound20ns <59.05ns. Pairwise hold exceptions
# affect only the named asynchronous receiver, never its second stage.
set_max_delay 20 -from [get_regs {audio_domain/reference_48_monitor/source_gray*}] -to [get_regs {audio_domain/reference_48_monitor/gray_meta*}]
set_false_path -hold -from [get_regs {audio_domain/reference_48_monitor/source_gray*}] -to [get_regs {audio_domain/reference_48_monitor/gray_meta*}]
set_max_delay 20 -from [get_regs {audio_domain/reference_44_monitor/source_gray*}] -to [get_regs {audio_domain/reference_44_monitor/gray_meta*}]
set_false_path -hold -from [get_regs {audio_domain/reference_44_monitor/source_gray*}] -to [get_regs {audio_domain/reference_44_monitor/gray_meta*}]
set_max_delay 20 -from [get_regs {audio_domain/selected_monitor/source_gray*}] -to [get_regs {audio_domain/selected_monitor/gray_meta*}]
set_false_path -hold -from [get_regs {audio_domain/selected_monitor/source_gray*}] -to [get_regs {audio_domain/selected_monitor/gray_meta*}]

# Stable single-bit controls, first receive stage only. All later stages keep
# setup/hold/recovery/removal checks; no entire-domain false path is permitted.
set_max_delay 20 -to [get_pins {quiesce_sync_0_s0/D resume_sync_0_s0/D snapshot_request_sync_0_s0/D}]
set_false_path -hold -through [get_pins {quiesce_sync_0_s0/D resume_sync_0_s0/D snapshot_request_sync_0_s0/D}]
set_max_delay 20 -to [get_pins {quiet_sync_0_s0/D prefill_sync_0_s0/D running_sync_0_s0/D idle_sync_0_s0/D snapshot_ack_sync_0_s0/D}]
set_false_path -hold -through [get_pins {quiet_sync_0_s0/D prefill_sync_0_s0/D running_sync_0_s0/D idle_sync_0_s0/D snapshot_ack_sync_0_s0/D}]
set_max_delay 20 -from [get_regs {snapshot_hold*}] -to [get_regs {snapshot_payload_meta*}]
set_false_path -hold -from [get_regs {snapshot_hold*}] -to [get_regs {snapshot_payload_meta*}]

# Bundled configuration is staged before deselection/qualification/local reset
# release and sampled only on the first selected edge. Bound its propagation;
# this hold exception applies only to the two explicitly held-data receivers.
set_max_delay 20 -from [get_regs {audio_domain/transaction/pending_epoch* audio_domain/transaction/pending_44k1_s0}] -to [get_regs {serializer/epoch* serializer/mode_44k1*}]
set_false_path -hold -from [get_regs {audio_domain/transaction/pending_epoch* audio_domain/transaction/pending_44k1_s0}] -to [get_regs {serializer/epoch* serializer/mode_44k1*}]

# Source-level sampling is separate from the Gray counters. Limit only its
# first asynchronous level receiver; second level_sync remains ordinarily timed.
set_max_delay 20 -to [get_pins {audio_domain/reference_48_monitor/level_meta_s0/D audio_domain/reference_44_monitor/level_meta_s0/D audio_domain/selected_monitor/level_meta_s0/D}]
set_false_path -hold -through [get_pins {audio_domain/reference_48_monitor/level_meta_s0/D audio_domain/reference_44_monitor/level_meta_s0/D audio_domain/selected_monitor/level_meta_s0/D}]

# External restart is asynchronous to the POR registers. No internal reset net
# is globally excepted; see physical_checks.json for explicit reset audit gates.
set_false_path -from [get_ports {restart_n}] -to [get_regs {power_on_count* power_ready_s0}]
report_timing -setup -max_paths 2000 -max_common_paths 1
report_timing -hold -max_paths 2000 -max_common_paths 1
report_timing -recovery -max_paths 2000 -max_common_paths 1
report_timing -removal -max_paths 2000 -max_common_paths 1
report_min_pulse_width -nworst 200 -detail
report_timing -setup -from [get_regs {audio_domain/reference_48_monitor/source_gray*}] -to [get_regs {audio_domain/reference_48_monitor/gray_meta*}] -max_paths 10000 -max_common_paths 1
report_timing -setup -from [get_regs {audio_domain/reference_44_monitor/source_gray*}] -to [get_regs {audio_domain/reference_44_monitor/gray_meta*}] -max_paths 10000 -max_common_paths 1
report_timing -setup -from [get_regs {audio_domain/selected_monitor/source_gray*}] -to [get_regs {audio_domain/selected_monitor/gray_meta*}] -max_paths 10000 -max_common_paths 1
report_timing -setup -from [get_regs {snapshot_hold*}] -to [get_regs {snapshot_payload_meta*}] -max_paths 10000 -max_common_paths 1
report_timing -setup -from [get_regs {audio_domain/transaction/pending_epoch* audio_domain/transaction/pending_44k1_s0}] -to [get_regs {serializer/epoch* serializer/mode_44k1*}] -max_paths 10000 -max_common_paths 1
report_timing -setup -to [get_clocks {selected48}] -max_paths 20 -max_common_paths 1
report_timing -hold -to [get_clocks {selected48}] -max_paths 20 -max_common_paths 1
report_timing -recovery -to [get_clocks {selected48}] -max_paths 20 -max_common_paths 1
report_timing -removal -to [get_clocks {selected48}] -max_paths 20 -max_common_paths 1
report_timing -setup -to [get_clocks {selected44}] -max_paths 20 -max_common_paths 1
report_timing -hold -to [get_clocks {selected44}] -max_paths 20 -max_common_paths 1
report_timing -recovery -to [get_clocks {selected44}] -max_paths 20 -max_common_paths 1
report_timing -removal -to [get_clocks {selected44}] -max_paths 20 -max_common_paths 1
# MPW uses register objects; the SDK selects the faster44.1-family clock
# on the shared DCS output. Its half-period bound also covers48-family.
report_min_pulse_width -nworst 1000 -detail [get_regs {serializer/*}]
