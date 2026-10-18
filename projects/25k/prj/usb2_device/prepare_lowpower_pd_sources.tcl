# Generate only in the isolated ASCII build. Distinct GAO D2AE identifies this
# Table 6-8 FS DP-pullup/DM-pulldown comparison; all other phases are unchanged.
set usb2_lowpower_pd_dir [file dirname [file normalize [info script]]]
file mkdir [file join $usb2_lowpower_pd_dir generated]
set usb2_lowpower_pd_input [open [file join $usb2_lowpower_pd_dir rtl usb2_lowpower_top.v] r]
set usb2_lowpower_pd_source [read $usb2_lowpower_pd_input]
close $usb2_lowpower_pd_input
set usb2_lowpower_pd_match "FS_OTG_CTRL = 8'h00"
if {[regexp -all -- $usb2_lowpower_pd_match $usb2_lowpower_pd_source] != 1} {
    error "Expected exactly one FS_OTG_CTRL default in low-power top"
}
set usb2_lowpower_pd_source [string map [list $usb2_lowpower_pd_match "FS_OTG_CTRL = 8'h04"] $usb2_lowpower_pd_source]
set usb2_lowpower_pd_output [open [file join $usb2_lowpower_pd_dir generated usb2_lowpower_pd_top.v] w]
puts -nonewline $usb2_lowpower_pd_output $usb2_lowpower_pd_source
close $usb2_lowpower_pd_output
