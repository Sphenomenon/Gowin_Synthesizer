# Application-core synthesis only. These are abstract message ports, not the
# board pinout. No CST, PnR, timing sign-off, or downloadable image is produced.
set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
set_device -name GW5A-25A GW5A-LV25MG121NC1/I0
set_option -synthesis_tool gowinsynthesis
set_option -top_module midi_keyboard_core
set_option -output_base_name midi_keyboard_core
set_option -verilog_std v2001
set_option -global_freq 50
# SUG1220-2.0E, section 3.3: do not map abstract core ports to package I/O.
set_option -disable_io_insertion 1
add_file rtl/core/midi_event_fifo.v
add_file rtl/core/midi_event_router.v
add_file rtl/input/keyboard_event_mapper.v
add_file rtl/transport/usb_midi_codec.v
add_file rtl/transport/ble_midi_codec.v
add_file rtl/control/screen_control_endpoint.v
add_file rtl/midi_keyboard_core.v
run syn
