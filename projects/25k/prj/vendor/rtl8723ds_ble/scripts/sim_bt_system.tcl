run all
set passed [get_value -radix unsigned /tb_bt_verilog_system/test_passed]
if {$passed ne "1"} {error "Pure Verilog Bluetooth system test did not complete"}
puts "SIM_BT_VERILOG_SYSTEM_PASS"
quit
