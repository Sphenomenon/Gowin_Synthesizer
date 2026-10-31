#!/usr/bin/env python3
"""Maintained GATT wire values, controller credit and interrupted construction."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT.parents[3] / 'projects/25k/example/RTL8723DS_PROTOCOL'
OWNER = ROOT / 'rtl/bluetooth/cpu_owner'


def legacy_fixture():
    text = (PROTOCOL / 'tests/tb_gatt_legacy.sv').read_text()
    anchor = '.clk(clk),.resetn(resetn),.enable(enable),.acl_packet_count'
    assert text.count(anchor) == 1
    return text.replace(anchor, '''.business_owner_reset_ni(resetn && enable),
        .business_command_valid_i(1'b0),.business_command_write_i(1'b0),
        .business_command_address_i(12'd0),.business_command_data_i(32'd0),
        .business_command_strobes_i(4'd0),
        .clk(clk),.resetn(resetn),.enable(enable),.acl_packet_count''')


class GattValues(unittest.TestCase):
    def run_fixture(self, text, marker='PASS: bt_gatt'):
        sources = [OWNER / name for name in (
            'bt_gatt.v', 'ble_protocol_command.v',
            'workstation_ble_record_data_engine.sv', 'workstation_ble_record_data_service.sv')]
        sources += [ROOT / 'rtl/services/workstation_business_mailbox.sv',
                    ROOT / 'rtl/memory/workstation_sdp.sv']
        with tempfile.TemporaryDirectory(prefix='ae350-gatt-values-') as directory:
            stage = Path(directory)
            bench, binary = stage / 'bench.sv', stage / 'simulation'
            bench.write_text(text)
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'tb_bt_gatt',
                '-o', str(binary), str(bench), *map(str, sources)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            executed = subprocess.run(['vvp', str(binary)],
                cwd=PROTOCOL / 'vendor/rtl8723ds_ble', capture_output=True, text=True, timeout=60)
            self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
            self.assertIn(marker, executed.stdout)

    def test_legacy_wire_database_crc_notifications_credit_and_reconnect(self):
        self.run_fixture(legacy_fixture())

    def test_value_snapshot_backpressure_and_session_reset(self):
        for reset in ('enable', 'resetn'):
            with self.subTest(reset=reset):
                text = legacy_fixture()
                anchor = '        test_passed=1;'
                self.assertEqual(text.count(anchor), 1)
                extension = '''        // Restart the link and hold TX while a nonzero sample is built.
        @(negedge clk); enable=1;tx_ready=0;busy_cycles=0;
        receive_data[0]=8'h3e;receive_data[1]=19;
        receive_data[2]=1;receive_data[3]=0;put_word(4,16'h0234);
        send_packet(4,21);
        force dut.notification_count=32'h01234567;
        force dut.elapsed_ms=32'h11223344;
        read_request(7);
        // These live values change before the queued payload can be transmitted.
        force dut.notification_count=32'h89abcdef;
        force dut.elapsed_ms=32'haabbccdd;
        repeat(32)@(posedge clk);
        if(tx_count!=15)$fatal(1,"Value escaped TX backpressure");
        tx_ready=1;await_tx(16);verify_acl(15,21);
        byte_is(15,9,"B");byte_is(15,10,"T");byte_is(15,11,"S");byte_is(15,12,"T");
        byte_is(15,13,8'h67);byte_is(15,14,8'h45);byte_is(15,15,8'h23);byte_is(15,16,8'h01);
        byte_is(15,17,8'h44);byte_is(15,18,8'h33);byte_is(15,19,8'h22);byte_is(15,20,8'h11);
        checked_crc=independent_crc(15,9);
        byte_is(15,27,checked_crc[7:0]);byte_is(15,28,checked_crc[15:8]);
        release dut.notification_count;release dut.elapsed_ms;

        // Interrupt another read before its value is complete. A new connection
        // must see neither a partial old reply nor the previous sequence.
        complete_acl(16'h0234,1);read_request(7);
        @(negedge clk);RESET_SIGNAL=0;
        repeat(2)@(posedge clk);
        @(negedge clk);RESET_SIGNAL=1;tx_ready=1;busy_cycles=0;
        receive_data[0]=8'h3e;receive_data[1]=19;
        receive_data[2]=1;receive_data[3]=0;put_word(4,16'h0234);
        send_packet(4,21);repeat(32)@(posedge clk);
        if(tx_count!=16 || !connected)$fatal(1,"Old value survived session reset");
        read_request(7);await_tx(17);verify_acl(16,21);
        for(k=13;k<17;k=k+1)byte_is(16,k,0);
        checked_crc=independent_crc(16,9);
        byte_is(16,27,checked_crc[7:0]);byte_is(16,28,checked_crc[15:8]);
        $display("PASS value snapshot, backpressure and interrupted session");
'''.replace('RESET_SIGNAL', reset)
                self.run_fixture(text.replace(anchor, extension + anchor), 'PASS value snapshot')


if __name__ == '__main__':
    unittest.main()
