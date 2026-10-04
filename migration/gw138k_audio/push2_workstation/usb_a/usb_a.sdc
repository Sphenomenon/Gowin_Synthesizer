
# USB-A Push controls -> existing audio event FIFO; bound Gray bus flight.
set_max_delay 10.000 -from [get_regs {u_push/events/fifo/unbuffered/produce_w_gry* u_push/events/fifo/unbuffered/produce_w_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/produce_cdc/stage0*}]
set_false_path -hold -from [get_regs {u_push/events/fifo/unbuffered/produce_w_gry* u_push/events/fifo/unbuffered/produce_w_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/produce_cdc/stage0*}]
set_max_delay 10.000 -from [get_regs {u_push/events/fifo/unbuffered/consume_r_gry* u_push/events/fifo/unbuffered/consume_r_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/consume_cdc/stage0*}]
set_false_path -hold -from [get_regs {u_push/events/fifo/unbuffered/consume_r_gry* u_push/events/fifo/unbuffered/consume_r_bin_6*}] -to [get_regs {u_push/events/fifo/unbuffered/consume_cdc/stage0*}]
set_false_path -to [get_pins {u_push/event_release*/CLEAR u_push/events/fifo/unbuffered/rst_cdc/stage*/PRESET}]
# Existing 50MHz coherent performance snapshot -> USB48 CPU/rendering.
# Held payload remains immutable through the acknowledged toggle crossing.
set_max_delay 20.000 -from [get_regs {u_push/feedback/held_data*}] -to [get_regs {u_push/feedback/destination_data*}]
set_false_path -hold -from [get_regs {u_push/feedback/held_data*}] -to [get_regs {u_push/feedback/destination_data*}]
set_false_path -to [get_pins {u_push/feedback/req_meta*/D u_push/feedback/ack_meta*/D u_push/feedback/source_release*/CLEAR u_push/feedback/destination_release*/CLEAR}]
# P12/P13 shared DDR display summary: held data crosses ddr_ui100 -> usb_48m
# through the same acknowledged stream CDC primitive; constrain only this
# mailbox, not the audio/video clock domains.
set_max_delay 20.000 -from [get_regs {u_display_push_cdc/held_data*}] -to [get_regs {u_display_push_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_display_push_cdc/held_data*}] -to [get_regs {u_display_push_cdc/destination_data*}]
set_false_path -to [get_pins {u_display_push_cdc/req_meta*/D u_display_push_cdc/ack_meta*/D u_display_push_cdc/source_release*/CLEAR u_display_push_cdc/destination_release*/CLEAR}]
# P27 audio service state: held score/record payload crosses audio_76m8 ->
# usb_48m through the same acknowledged stream CDC primitive.
set_max_delay 20.000 -from [get_regs {u_service_push_cdc/held_data*}] -to [get_regs {u_service_push_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_service_push_cdc/held_data*}] -to [get_regs {u_service_push_cdc/destination_data*}]
set_false_path -to [get_pins {u_service_push_cdc/req_meta*/D u_service_push_cdc/ack_meta*/D u_service_push_cdc/source_release*/CLEAR u_service_push_cdc/destination_release*/CLEAR}]

# TF transport state and exact final DAC pairs: acknowledged audio76m8 -> 50m.
# Release FFs are shared and constrained at u_tf_control_cdc by build.py.
set_max_delay 20.000 -from [get_regs {u_tf_control_cdc/held_data*}] -to [get_regs {u_tf_control_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_tf_control_cdc/held_data*}] -to [get_regs {u_tf_control_cdc/destination_data*}]
set_false_path -to [get_pins {u_tf_control_cdc/req_meta*/D u_tf_control_cdc/ack_meta*/D}]
set_max_delay 20.000 -from [get_regs {u_final_output_cdc/held_data*}] -to [get_regs {u_final_output_cdc/destination_data*}]
set_false_path -hold -from [get_regs {u_final_output_cdc/held_data*}] -to [get_regs {u_final_output_cdc/destination_data*}]
set_false_path -to [get_pins {u_final_output_cdc/req_meta*/D u_final_output_cdc/ack_meta*/D}]
set_false_path -to [get_pins {u_tf_audio/hold_meta*/D}]
