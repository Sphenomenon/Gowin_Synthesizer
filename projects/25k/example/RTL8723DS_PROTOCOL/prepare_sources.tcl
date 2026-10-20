# Source only after changing into the ble_bringup project directory.
# GowinSynthesis resolves $readmemh relative to impl/gwsynthesis, not gw_sh's
# working directory. Generate a build-local top with an absolute ROM parameter;
# leave the portable source template and every vendor file unchanged.
set adaptation_python [auto_execok python3]
if {$adaptation_python eq ""} { error "python3 is required to generate the verified storage adaptation" }
puts [exec {*}$adaptation_python [file normalize prepare_adapted.py] 2>@1]
set rom_source [file normalize vendor/rtl8723ds_ble/rtl8723ds_patch.mem]
if {![file isfile $rom_source] || [file size $rom_source] == 0} {
    error "Missing BLE firmware ROM: $rom_source"
}
# This macOS GowinSynthesis release cannot parse a non-ASCII string inside
# $readmemh. Stage only the unchanged ROM in an ASCII directory for this run.
# Keep it until compilation completes; rebuilding regenerates it automatically.
set rom_stage_dir /private/tmp/gw25k-ble-rom-[pid]
file mkdir $rom_stage_dir
set rom_file [file join $rom_stage_dir rtl8723ds_patch.mem]
file copy -force $rom_source $rom_file
set rom_verilog [string map [list "\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "\\r"] $rom_file]
set template_handle [open rtl/ble_bringup_top.v r]
set top_text [read $template_handle]
close $template_handle
set template_parameter {parameter PATCH_FILE = "vendor/rtl8723ds_ble/rtl8723ds_patch.mem"}
if {[string first $template_parameter $top_text] < 0} {
    error "BLE top template PATCH_FILE parameter changed; update prepare_sources.tcl"
}
set prepared_text [string map [list $template_parameter "parameter PATCH_FILE = \"$rom_verilog\""] $top_text]
file mkdir generated
set generated_top [file normalize generated/ble_bringup_top.v]
set generated_handle [open $generated_top w]
puts -nonewline $generated_handle $prepared_text
close $generated_handle
puts "BLE firmware ROM source: $rom_source"
puts "BLE firmware ROM staged ASCII path: $rom_file"

# Audio PCM ROM is immutable source data; this tool resolves readmemh from impl/gwsynthesis.
set audio_rom [file normalize audio/test_tone.mem]
set adapted_core [file normalize generated/rtl/bt_verilog_core.v]
set core_in [open adaptations/bt_verilog_core.v r]
set core_text [read $core_in]
close $core_in
set core_out [open $adapted_core w]
puts -nonewline $core_out [string map [list {parameter AUDIO_FILE="audio/test_tone.mem"} "parameter AUDIO_FILE=\"$audio_rom\""] $core_text]
close $core_out
