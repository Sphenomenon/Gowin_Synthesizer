#!/usr/bin/env python3
"""Maintained GATT wire values, controller credit and interrupted construction."""
from pathlib import Path
import os
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


def find_information_fixture():
    text = legacy_fixture().replace('transmitted [0:4095]', 'transmitted [0:131071]')
    text = text.replace('lengths [0:49]', 'lengths [0:1599]')
    start = text.index('    initial begin\n        for(k=0;k<264;')
    end = text.index('    initial begin #2000000;', start)
    matrix = r'''
    integer first, last, mode, count, body_length, error_code, at, bank, n, h;
    reg [7:0] saved_response[0:63];
    function integer endpoint;
        input integer index;
        begin case(index)
            10:endpoint=16'h0100;11:endpoint=16'h7fff;
            12:endpoint=16'h8000;13:endpoint=16'hffff;
            default:endpoint=index;
        endcase end
    endfunction
    function [15:0] expected_uuid;
        input integer handle_number;
        begin case(handle_number)
            1,4,5,9:expected_uuid=16'h2800;
            2,6:expected_uuid=16'h2803;
            3:expected_uuid=16'h2a00;
            7:expected_uuid=16'hfff1;
            8:expected_uuid=16'h2902;
            default:expected_uuid=0;
        endcase end
    endfunction
    task find_request;
        input integer first_handle,last_handle,packet_length;
        begin
            att_header(4,packet_length-8);put_word(9,first_handle);put_word(11,last_handle);
            send_packet(2,packet_length);
        end
    endtask
    task await_queued;
        input integer expected;
        integer watchdog;
        begin
            watchdog=0;
            while((dut.queued!=expected || dut.state!=0) && watchdog<5000)begin
                @(posedge clk);#2;watchdog=watchdog+1;
            end
            if(watchdog==5000)$fatal(1,"Find Information queue did not settle");
        end
    endtask
    task check_pair;
        input integer first_handle,last_handle,packet_length;
        reg [15:0] uuid;
        begin
            @(negedge clk);tx_ready=0;busy_cycles=0;before_count=tx_count;
            for(at=0;at<64;at=at+1)dut.response[at]=8'h80+at;
            find_request(first_handle,last_handle,packet_length);
            await_queued(1);
            find_request(first_handle,last_handle,packet_length);
            await_queued(2);
            if(tx_count!=before_count)$fatal(1,"Find Information escaped backpressure");
            error_code=0;
            if(packet_length!=13)error_code=4;
            else if(first_handle==0 || first_handle>last_handle)error_code=1;
            else if(first_handle>22)error_code=10;
            count=last_handle<8 ? last_handle:first_handle==9 ? 9:8;
            count=count-first_handle+1;if(count>5)count=5;
            body_length=error_code ? 5:first_handle==9 ? 6:2+4*count;
            // Verify both physical banks, including every untouched tail byte.
            for(bank=0;bank<2;bank=bank+1)begin
                for(at=8+body_length;at<32;at=at+1)
                    if(dut.response[32*bank+at]!==((8'h80+32*bank+at)&255))
                        $fatal(1,"Find Information changed unused tail: bank%0d byte%0d",bank,at);
            end
            if(first_handle==1 && last_handle==8 && packet_length==13)begin
                for(at=0;at<64;at=at+1)saved_response[at]=dut.response[at];
                before_errors=errors;find_request(8,8,13);await_queued(2);
                if(errors!=before_errors+1)$fatal(1,"Find Information full queue not rejected");
                for(at=0;at<64;at=at+1)
                    if(dut.response[at]!==saved_response[at])$fatal(1,"Queued response overwritten");
            end
            $write("BANK %0d %0d %0d %0d ",mode,first_handle,last_handle,packet_length);
            for(at=0;at<64;at=at+1)$write("%02x",dut.response[at]);$write("\n");
            @(negedge clk);tx_ready=1;await_tx(before_count+1);
            complete_acl(16'h0234,1);await_tx(before_count+2);
            complete_acl(16'h0234,1);repeat(32)@(posedge clk);
            for(n=before_count;n<before_count+2;n=n+1)begin
                verify_acl(n,body_length);
                if(error_code)begin
                    byte_is(n,8,1);byte_is(n,9,4);
                    h=packet_length!=13 ? 0:first_handle;
                    byte_is(n,10,h);byte_is(n,11,h>>8);byte_is(n,12,error_code);
                end else begin
                    byte_is(n,8,5);byte_is(n,9,1);
                    for(at=0;at<(first_handle==9 ? 1:count);at=at+1)begin
                        h=first_handle+at;uuid=expected_uuid(h);
                        byte_is(n,10+4*at,h);byte_is(n,11+4*at,h>>8);
                        byte_is(n,12+4*at,uuid[7:0]);byte_is(n,13+4*at,uuid[15:8]);
                    end
                end
                $write("WIRE %0d ",lengths[n]);
                for(at=0;at<lengths[n];at=at+1)$write("%02x",transmitted[n*80+at]);$write("\n");
            end
        end
    endtask
    initial begin
        for(k=0;k<264;k=k+1)receive_data[k]=0;
        for(mode=0;mode<2;mode=mode+1)begin
            @(negedge clk);resetn=0;enable=0;tx_ready=1;busy_cycles=0;
            repeat(3)@(posedge clk);@(negedge clk);resetn=1;enable=1;
            receive_data[0]=8'h3e;receive_data[1]=19;receive_data[2]=1;
            receive_data[3]=0;put_word(4,16'h0234);send_packet(4,21);
            before_count=tx_count;att_header(2,3);put_word(9,mode ? 247:23);
            send_packet(2,11);await_tx(before_count+1);complete_acl(16'h0234,1);
            repeat(32)@(posedge clk);
            for(first=0;first<14;first=first+1)
                for(last=0;last<14;last=last+1)check_pair(endpoint(first),endpoint(last),13);
            check_pair(1,8,12);check_pair(8,8,14);
            check_pair(0,0,12);check_pair(9,16'hffff,14);
        end
        $display("PASS: bt_gatt Find Information request matrix");$finish;
    end
'''
    return text[:start] + matrix + text[end:].replace('#2000000', '#20000000')


class GattValues(unittest.TestCase):
    def run_fixture(self, text, marker='PASS: bt_gatt', gatt_source=None):
        sources = [OWNER / name for name in (
            'bt_gatt.v', 'ble_protocol_command.v',
            'workstation_ble_record_data_engine.sv', 'workstation_ble_record_data_service.sv')]
        sources += [ROOT / 'rtl/services/workstation_business_mailbox.sv',
                    ROOT / 'rtl/memory/workstation_sdp.sv']
        if gatt_source is not None:
            sources[0] = Path(gatt_source)
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
            return executed.stdout

    def test_find_information_ranges_banks_backpressure_and_queued_bytes(self):
        text = find_information_fixture()
        actual = self.run_fixture(text, 'PASS: bt_gatt Find Information')
        reference = os.environ.get('BT_GATT_REFERENCE_SOURCE')
        if reference:
            expected = self.run_fixture(text, 'PASS: bt_gatt Find Information', reference)
            trace = lambda output: [line for line in output.splitlines() if line.startswith(('BANK ', 'WIRE '))]
            self.assertEqual(trace(actual), trace(expected))

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
