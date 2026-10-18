# Reproduce the address-filtered bridge after the clean-build staging copy.
set usb1_prepare_dir [file dirname [file normalize [info script]]]
exec python3 [file join $usb1_prepare_dir generate_core.py]
