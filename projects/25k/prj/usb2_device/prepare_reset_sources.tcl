# Distinct reset + RxCmd layout; generated only in isolated build directory.
set usb2_reset_dir [file dirname [file normalize [info script]]]
file mkdir [file join $usb2_reset_dir generated]
set usb2_reset_input [open [file join $usb2_reset_dir rtl usb2_termination_top.v] r]
set usb2_reset_source [read $usb2_reset_input]
close $usb2_reset_input
foreach usb2_reset_param {RXCMD_DIAG PHY_SOFT_RESET} {
    set usb2_reset_match "$usb2_reset_param = 1'b0"
    if {[regexp -all -- $usb2_reset_match $usb2_reset_source] != 1} {
        error "Expected exactly one default for $usb2_reset_param"
    }
    set usb2_reset_source [string map [list $usb2_reset_match "$usb2_reset_param = 1'b1"] $usb2_reset_source]
}
set usb2_reset_output [open [file join $usb2_reset_dir generated usb2_reset_top.v] w]
puts -nonewline $usb2_reset_output $usb2_reset_source
close $usb2_reset_output
