# Generate only USB2 adaptations after the clean staging copy.
set usb2_prepare_dir [file dirname [file normalize [info script]]]
exec python3 [file join $usb2_prepare_dir generate_serial_core.py]
