# Generate an activity-only default without changing the preserved CDC layout.
set usb2_activity_dir [file dirname [file normalize [info script]]]
source [file join $usb2_activity_dir prepare_serial_sources.tcl]
set usb2_activity_input [open [file join $usb2_activity_dir rtl usb2_serial_top.v] r]
set usb2_activity_source [read $usb2_activity_input]
close $usb2_activity_input
set usb2_activity_match "SERIAL_ACTIVITY_DIAG = 1'b0"
if {[regexp -all -- $usb2_activity_match $usb2_activity_source] != 1} {
    error "Expected exactly one activity diagnostic parameter default"
}
set usb2_activity_source [string map [list $usb2_activity_match "SERIAL_ACTIVITY_DIAG = 1'b1"] $usb2_activity_source]
set usb2_activity_output [open [file join $usb2_activity_dir generated usb2_activity_top.v] w]
puts -nonewline $usb2_activity_output $usb2_activity_source
close $usb2_activity_output
