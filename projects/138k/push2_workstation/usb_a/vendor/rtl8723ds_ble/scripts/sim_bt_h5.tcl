run all
set passed [get_value -radix unsigned /tb_bt_h5/test_passed]
if {$passed ne "1"} {
    error "bt_h5 test did not complete successfully (test_passed=$passed)"
}
puts "SIM_BT_H5_PASS"
quit
