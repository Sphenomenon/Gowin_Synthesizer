# Generate a distinct RxCmd diagnostic layout; preserve the termination layout.
set usb2_rxcmd_dir [file dirname [file normalize [info script]]]
file mkdir [file join $usb2_rxcmd_dir generated]
set usb2_rxcmd_input [open [file join $usb2_rxcmd_dir rtl usb2_termination_top.v] r]
set usb2_rxcmd_source [read $usb2_rxcmd_input]
close $usb2_rxcmd_input
set usb2_rxcmd_match "RXCMD_DIAG = 1'b0"
if {[regexp -all -- $usb2_rxcmd_match $usb2_rxcmd_source] != 1} {
    error "Expected exactly one RxCmd diagnostic parameter default"
}
set usb2_rxcmd_source [string map [list $usb2_rxcmd_match "RXCMD_DIAG = 1'b1"] $usb2_rxcmd_source]
set usb2_rxcmd_output [open [file join $usb2_rxcmd_dir generated usb2_rxcmd_top.v] w]
puts -nonewline $usb2_rxcmd_output $usb2_rxcmd_source
close $usb2_rxcmd_output
