# Distinct full Scratch + reset + RxCmd layout; generated only in isolated build directory.
set usb2_buscheck_dir [file dirname [file normalize [info script]]]
file mkdir [file join $usb2_buscheck_dir generated]
set usb2_buscheck_input [open [file join $usb2_buscheck_dir rtl usb2_termination_top.v] r]
set usb2_buscheck_source [read $usb2_buscheck_input]
close $usb2_buscheck_input
foreach usb2_buscheck_param {RXCMD_DIAG PHY_SOFT_RESET FULL_SCRATCH_TEST} {
    set usb2_buscheck_match "$usb2_buscheck_param = 1'b0"
    if {[regexp -all -- $usb2_buscheck_match $usb2_buscheck_source] != 1} {
        error "Expected exactly one default for $usb2_buscheck_param"
    }
    set usb2_buscheck_source [string map [list $usb2_buscheck_match "$usb2_buscheck_param = 1'b1"] $usb2_buscheck_source]
}
set usb2_buscheck_output [open [file join $usb2_buscheck_dir generated usb2_buscheck_top.v] w]
puts -nonewline $usb2_buscheck_output $usb2_buscheck_source
close $usb2_buscheck_output
