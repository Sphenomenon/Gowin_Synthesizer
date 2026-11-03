"""Actual BLE business RTL with a live, non-repeating workstation PCM source."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT.parents[3] / 'projects/25k/example/RTL8723DS_PROTOCOL'
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT / 'sim'))
from tools import workstation_bluetooth,workstation_pinout
from tools.read_ble_status import decode_line
from test_workstation_pinout import fixture


class Bluetooth(unittest.TestCase):
    def test_status_accepts_uart_rate_switch_and_rejects_unknown_configuration(self):
        words = [0x42545647, 1] + [0] * 20 + [50000000, 115200]
        for baud in (115200, 921600):
            words[23] = baud
            line = 'BLE1 ' + ''.join(f'{word:08X}' for word in words) + '\n'
            self.assertEqual(decode_line(line)['baud'], baud)
        for index, value in ((0, 0), (1, 2), (22, 48000000), (23, 1000000)):
            changed = words.copy()
            changed[index] = value
            line = 'BLE1 ' + ''.join(f'{word:08X}' for word in changed) + '\n'
            with self.assertRaises(ValueError):
                decode_line(line)

    def run_simulation(self, top, sources, cwd, marker):
        with tempfile.TemporaryDirectory(prefix='workstation-ble-') as directory:
            binary = Path(directory) / 'simulation'
            compilation = subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(binary), *map(str,sources)],
                                         cwd=cwd, capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode,0,compilation.stdout+compilation.stderr)
            execution = subprocess.run(['vvp',str(binary)],cwd=cwd,capture_output=True,text=True,timeout=120)
            self.assertEqual(execution.returncode,0,execution.stdout+execution.stderr)
            self.assertIn(marker,execution.stdout)

    def test_live_pcm_storage_download_and_failures(self):
        self.run_simulation('tb_workstation_ble_recording',[
            ROOT / 'sim/usb2/tb_workstation_ble_recording.sv',PROTOCOL / 'rtl/ble_recording.v'],
            ROOT,'PASS live BLE PCM:')

    def test_existing_protocol_recording_replay_and_disconnect(self):
        self.run_simulation('tb_protocol_recording',[
            PROTOCOL / 'tests/tb_protocol_recording.sv',PROTOCOL / 'rtl/ble_protocol_command.v',
            PROTOCOL / 'rtl/ble_recording.v'],PROTOCOL,'PASS: recording START/STOP')

    def test_request_cache_replay_eviction_and_expiry_with_both_storage_styles(self):
        original=(PROTOCOL / 'tests/tb_protocol_command.sv').read_text()
        hold_anchor='        save_response();release_response();elapsed=900;'
        self.assertEqual(original.count(hold_anchor),1)
        original=original.replace(hold_anchor,'''        save_response();
        repeat(24) begin
            @(negedge clk);elapsed=elapsed+1;
            if(!valid || length!=84)$fatal(1,"Maximum reply changed while stalled");
            compare_saved();
        end
        release_response();elapsed=900;''')
        original=original.replace('        elapsed=64000;',
            '''        elapsed=62999;
        make_request(2,36,64'h1020304050607080,0);send_request();verify_response(0,84);release_response();
        elapsed=63000;''')
        for style in ('block_ram','distributed_ram'):
            with self.subTest(style=style),tempfile.TemporaryDirectory(prefix='ble-cache-time-') as directory:
                bench=Path(directory) / 'tb_protocol_command.sv'
                bench.write_text(original.replace('    ble_protocol_command dut(',
                    f'    defparam dut.CACHE_METADATA_RAM_STYLE="{style}";\n    ble_protocol_command dut('))
                self.run_simulation('tb_protocol_command',[
                    bench,PROTOCOL / 'rtl/ble_protocol_command.v',PROTOCOL / 'rtl/ble_recording.v'],
                    PROTOCOL,'PASS: protocol HELLO')

    def test_existing_gatt_database_and_acl_credits(self):
        self.run_simulation('tb_bt_gatt',[
            PROTOCOL / 'tests/tb_gatt_legacy.sv',PROTOCOL / 'adaptations/bt_gatt.v',
            PROTOCOL / 'rtl/ble_protocol_command.v',PROTOCOL / 'rtl/ble_recording.v'],
            PROTOCOL / 'vendor/rtl8723ds_ble','PASS:')

    def test_streamed_completions_cover_full_event_and_reject_malformed_lengths(self):
        original=(PROTOCOL / 'tests/tb_gatt_credits.sv').read_text()
        anchor='        $display("PASS: negotiated ACL credits'
        self.assertEqual(original.count(anchor),1)
        extension='''        before_count=completed;
        for(k=0;k<63;k=k+1) begin
            put_word(3+4*k,k==62 ? 16'hf234 : k%3==0 ? 16'h0234 : 16'h0111);
            put_word(5+4*k,k==62 ? 16'hffff : k+1);
        end
        receive_data[0]=8'h13;receive_data[1]=253;receive_data[2]=63;
        send_packet(4,255);repeat(8)@(posedge clk);
        if(completed!=before_count+66186 || dut.tx_credits!=4)
            $fatal(1,"Full completion event lost matching handles beyond header cache");
        before_count=completed;
        receive_data[1]=252;send_packet(4,254);repeat(8)@(posedge clk);
        if(completed!=before_count)$fatal(1,"Truncated completion event applied");
        send_packet(4,255);repeat(8)@(posedge clk);
        if(completed!=before_count)$fatal(1,"Bad HCI length applied");
        for(k=0;k<63;k=k+1)put_word(3+4*k,16'h0111);
        receive_data[1]=253;send_packet(4,255);repeat(8)@(posedge clk);
        if(completed!=before_count)$fatal(1,"Foreign handles applied");
        receive_data[1]=1;receive_data[2]=0;send_packet(4,3);repeat(8)@(posedge clk);
        if(completed!=before_count)$fatal(1,"Empty completion event applied");
        $display("PASS streamed completions: 63 handles, 16-bit counts, malformed lengths and foreign handles");
'''
        with tempfile.TemporaryDirectory(prefix='ble-completion-stream-') as directory:
            bench=Path(directory) / 'tb_gatt_credits.sv'
            bench.write_text(original.replace(anchor,extension+anchor))
            self.run_simulation('tb_gatt_credits',[
                bench,PROTOCOL / 'adaptations/bt_gatt.v',PROTOCOL / 'rtl/ble_protocol_command.v',
                PROTOCOL / 'rtl/ble_recording.v'],PROTOCOL / 'vendor/rtl8723ds_ble',
                'PASS streamed completions: 63 handles')

    def test_connector_drift_rejected_before_staging(self):
        for node in ('J2.56','J2.58'):
            with self.subTest(node=node),tempfile.TemporaryDirectory(prefix='ble-pin-drift-') as directory:
                profile,payloads,core=fixture()
                netlists={role:workstation_pinout.Netlist(payload) for role,payload in payloads.items()}
                plan=workstation_pinout.resolve(profile,netlists,core)
                netlists['carrier'].nodes[node]='WRONG_CONNECTION'
                stage=Path(directory)
                with patch.object(workstation_pinout,'load_sources',return_value=(netlists,{})):
                    with self.assertRaises(ValueError):
                        workstation_bluetooth.prepare(ROOT,stage,stage,stage,plan)
                self.assertFalse((stage / 'native_bluetooth').exists())

    def test_native_wrapper_real_uart_patch_gatt_and_pcm(self):
        with tempfile.TemporaryDirectory(prefix='workstation-ble-uart-') as directory:
            stage=Path(directory)
            profile,payloads,core=fixture()
            netlists={role:workstation_pinout.Netlist(payload) for role,payload in payloads.items()}
            plan=workstation_pinout.resolve(profile,netlists,core)
            pinout_output=stage / 'pinout'
            pinout_output.mkdir()
            with patch.object(workstation_pinout,'load_sources',return_value=(netlists,{})):
                metadata=workstation_bluetooth.prepare(ROOT,stage,stage,pinout_output,plan)
            peer=(PROTOCOL / 'tests/tb_protocol_system.sv').read_text()
            instance=re.search(r'    rtl8723ds_ble #\(.*?\) dut \(.*?\);',peer,re.S)
            self.assertIsNotNone(instance)
            replacement='''    reg [31:0] pcm_counter=0, pcm_sequence=0;
    reg [31:0] reference_crc=32'hffffffff;
    integer reference_frames=0;
    reg pcm_valid=0;
    reg [31:0] pcm_pair=0;
    always @(negedge clk) begin
        pcm_valid=0;
        if(!resetn || !enable) begin pcm_counter=0;pcm_sequence=0;end
        else if(pcm_counter==191) begin
            pcm_counter=0;pcm_sequence=pcm_sequence+1;pcm_valid=1;
            pcm_pair={pcm_sequence[15:0],~pcm_sequence[15:0]};
        end else pcm_counter=pcm_counter+1;
    end
    always @(posedge clk) begin
        if(pcm_valid && dut.u_core.application.command_endpoint.recording.record_state!=0 &&
            dut.u_core.application.command_endpoint.recording.record_state<4) begin
            reference_crc=crc32_byte(reference_crc,pcm_pair[23:16]);
            reference_crc=crc32_byte(reference_crc,pcm_pair[31:24]);
            reference_crc=crc32_byte(reference_crc,pcm_pair[7:0]);
            reference_crc=crc32_byte(reference_crc,pcm_pair[15:8]);
            reference_frames=reference_frames+1;
        end
    end
    workstation_bluetooth #(.CLK_HZ(CLK_HZ),.CAPACITY_FRAMES(64),.STORAGE_DDR(0),.DISABLE_MS(1),.STARTUP_MS(2)) dut (
        .clk_i(clk),.rst_ni(resetn && enable),.module_uart_tx_i(uart_rx),
        .pcm_valid_i(pcm_valid),.pcm_pair_i(pcm_pair),.pcm_sequence_i(pcm_sequence),.source_allowed_i(1'b1),
        .module_uart_rx_o(uart_tx),.module_bt_dis_no(bt_enable),.module_wl_dis_no(),.outputs_active_o(outputs_active),
        .initialized_o(initialized),.connected_o(connected),.subscribed_o(subscribed),.failed_o(failed),.status_o(debug));'''
            peer=peer[:instance.start()]+replacement+peer[instance.end():]
            peer=peer.replace('dut.core','dut.u_core')
            def replace_once(before,after):
                self.assertEqual(peer.count(before),1,before)
                return peer.replace(before,after)
            for declaration in ('defparam dut.u_core.PATCH_BYTES=MODEL_PATCH_BYTES;',
                'defparam dut.u_core.FAST_BAUD=RUN_FAST ? 921600 : 115200;',
                'defparam dut.u_core.AUDIO_FILE="../../audio/test_tone.mem";'):
                peer=replace_once(declaration,'')
            peer=replace_once('size=op==1 ? 24 : 20;',
                "size=op==1 ? 24 : op==8'h20 ? 28 : op==8'h22 ? 24 : 20;")
            peer=replace_once('if(op==1) business_request[16]=1;',
                "if(op==1 || op==8'h20) business_request[16]=1; if(op==8'h20) business_request[20]=64;")
            scan_name=re.search(r'12: case\(at\).*?endcase',peer,re.S)
            self.assertIsNotNone(scan_name)
            scan_parameters=[13,12,9,*b'GW138K-MAIN']
            scan_expected='12: case(at)\n'+''.join(f"{index}:setup_parameter=8'h{value:02x};\n"
                for index,value in enumerate(scan_parameters))+'endcase'
            peer=replace_once(scan_name[0],scan_expected)
            peer=replace_once('business_reply[1]!=0 || business_used!=20+business_reply[2]',
                "business_reply[1]!=(business_opcode==8'h20 ? 1 : 0) || business_used!=20+business_reply[2]")
            peer=replace_once('end else if(business_used!=84 || business_reply[60]!=8) $fatal(1,"Status snapshot");',
                '''end else if(business_opcode==2) begin
                    if(business_used!=84 || business_reply[60]!=8) $fatal(1,"Status snapshot");
                end else if(business_opcode==8'h20) begin
                    if(business_used!=28) $fatal(1,"Native PCM start response");
                end else if(business_opcode==8'h22) begin
                    if(business_used!=68 || business_reply[28]!=4 || reference_frames!=64 ||
                        {business_reply[51],business_reply[50],business_reply[49],business_reply[48]}!==~reference_crc)
                        $fatal(1,"Native UART PCM recording CRC/frames/byte order");
                    $display("PASS native UART live PCM recording CRC and stereo byte order");
                end''')
            peer=replace_once("business_command(2,2,64'h1020304050607080);", 
                """business_command(2,2,64'h1020304050607080);
        business_command(8'h20,3,64'h1020304050607080);
        wait(dut.u_core.application.command_endpoint.recording.record_state==4);
        business_command(8'h22,4,64'h1020304050607080);""")
            sources=[stage / relative for relative in metadata['sources']]
            bench=stage / 'tb_native_bluetooth.sv'
            bench.write_text(peer)
            binary=stage / 'simulation'
            compilation=subprocess.run(['verilator','--binary','--timing','-j','2','-Wno-fatal',
                '-I'+str(stage),'--top-module','tb_bt_verilog_system','--Mdir',str(stage / 'obj'),
                '-o',str(binary),str(bench),str(ROOT / 'rtl/bluetooth/workstation_bluetooth.sv'),*map(str,sources)],
                cwd=stage,capture_output=True,text=True,timeout=180)
            self.assertEqual(compilation.returncode,0,compilation.stdout+compilation.stderr)
            execution=subprocess.run([str(binary)],cwd=PROTOCOL / 'vendor/rtl8723ds_ble',
                capture_output=True,text=True,timeout=240)
            self.assertEqual(execution.returncode,0,execution.stdout+execution.stderr)
            self.assertIn('PASS: protocol UART8E1/H5 checked patch',execution.stdout)
            self.assertIn('PASS native UART live PCM recording CRC and stereo byte order',execution.stdout)


if __name__ == '__main__':
    unittest.main()
