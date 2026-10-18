# Use xelab tb_bt_gatt -s bt_gatt_sim -debug typical before this script.
run all
set passed [get_value -radix unsigned /tb_bt_gatt/test_passed]
if {$passed ne "1"} {
    error "bt_gatt test did not complete successfully (test_passed=$passed)"
}
puts "SIM_BT_GATT_PASS"
quit
