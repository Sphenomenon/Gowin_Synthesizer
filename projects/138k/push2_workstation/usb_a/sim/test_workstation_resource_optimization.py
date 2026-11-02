"""Resource candidate behavior: replay policy, DDR PCM and immutable cues."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT.parents[3] / 'projects/25k/example/RTL8723DS_PROTOCOL'
sys.path.insert(0, str(ROOT))
from tools.workstation_static_checks import validate_cues


class ResourceOptimization(unittest.TestCase):
    def simulate(self, bench, top, sources, marker, cwd=None, arguments=()):
        with tempfile.TemporaryDirectory(prefix='resource-opt-') as directory:
            path = Path(directory)
            (path / 'src/memory').mkdir(parents=True)
            shutil.copyfile(ROOT / 'rtl/ddr_address_map.vh', path / 'src/memory/ddr_address_map.vh')
            source = path / 'test.sv'
            source.write_text("`timescale 1ns/1ps\n"+bench)
            result = subprocess.run(['iverilog', '-g2012', '-I'+str(path), '-I'+str(ROOT / 'rtl/music'), '-s', top,
                                     '-o', str(path / 'sim'), str(source), *map(str, sources)],
                                    cwd=cwd or path, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            result = subprocess.run(['vvp', str(path / 'sim'), *arguments], cwd=cwd or path,
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertNotIn('ERROR:', result.stdout)
            self.assertIn(marker, result.stdout)

    def test_one_entry_replay_without_expiry(self):
        bench = (PROTOCOL / 'tests/tb_protocol_command.sv').read_text()
        bench = bench.replace('    ble_protocol_command dut(',
            '    ble_protocol_command #(.CACHE_ENTRIES(1),.CACHE_EXPIRY_MS(0),'
            '.CACHE_METADATA_RAM_STYLE("distributed_ram")) dut(')
        bench = bench.replace('elapsed=64000;', 'elapsed=64000;')
        bench = bench.replace('make_request(2,36,64\'h1020304050607080,0);send_request();verify_response(8\'h87,28);',
                              'make_request(2,36,64\'h1020304050607080,0);send_request();verify_response(0,84);')
        self.simulate(bench, 'tb_protocol_command', [PROTOCOL / 'rtl/ble_protocol_command.v',
            PROTOCOL / 'rtl/ble_recording.v'], 'PASS: protocol HELLO', PROTOCOL)

    def test_gatt_prepared_slots_and_serial_copy(self):
        with tempfile.TemporaryDirectory(prefix='gatt-prepared-') as directory:
            path = Path(directory)
            result = subprocess.run([sys.executable, str(PROTOCOL / 'prepare_adapted.py'), '--output', str(path)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            for bench, top, marker in [('tb_gatt_legacy.sv', 'tb_bt_gatt', 'PASS: bt_gatt'),
                                        ('tb_gatt_credits.sv', 'tb_gatt_credits', 'PASS')]:
                self.simulate((PROTOCOL / 'tests' / bench).read_text(), top,
                    [path / 'bt_gatt.v', PROTOCOL / 'rtl/ble_protocol_command.v',
                     PROTOCOL / 'rtl/ble_recording.v'], marker, PROTOCOL / 'vendor/rtl8723ds_ble')

    def test_ddr_pcm_capture_download_and_failures(self):
        bench = (ROOT / 'sim/usb2/tb_workstation_ble_recording.sv').read_text()
        bench = bench.replace('.EXTERNAL_PCM(1),', '.EXTERNAL_PCM(1),.STORAGE_DDR(1),')
        bench = bench.replace('.source_fault_i(source_fault),', '.source_fault_i(source_fault || storage_fault),')
        bench = bench.replace('.boot_id(BOOT_ID),', '''.pcm_store_write_o(sw),.pcm_store_write_frame_o(wa),
        .pcm_store_write_data_o(wd),.pcm_store_read_frame_o(ra),.pcm_store_fetch_o(fetch),
        .pcm_store_fetch_byte_o(fa),.pcm_store_fetch_bytes_o(fl),.pcm_store_read_data_i(rd),
        .pcm_store_fetched_i(fetched),.pcm_store_ready_i(storage_ready),.pcm_store_fault_i(storage_fault),
        .boot_id(BOOT_ID),''', 1)
        bench = bench.replace('    function [31:0] crc_byte', DDR_MODEL + '\n    function [31:0] crc_byte', 1)
        self.simulate(bench, 'tb_workstation_ble_recording', [PROTOCOL / 'rtl/ble_recording.v',
            ROOT / 'rtl/bluetooth/workstation_ble_pcm_store.sv', ROOT / 'rtl/music/music_async_fifo.sv'],
            'PASS live BLE PCM:')

    def test_bist_bypass_has_no_memory_transactions(self):
        self.simulate('''module tb;
        reg clk=0,rst=0;always #5 clk=~clk;
        wire req,done,failed;wire [31:0] errors;
        ddr3_bist #(.ENABLE_BIST(0)) dut(.clk(clk),.rst_n(rst),.req_valid(req),.req_ready(1'b0),
          .req_write(),.req_addr(),.req_wdata(),.rsp_valid(1'b0),.rsp_data(256'd0),
          .done(done),.failed(failed),.error_count(errors),.first_error_addr());
        initial begin #2;if(done || req)$fatal;#10;rst=1;#10;
          if(!done || req || failed || errors)$fatal;rst=0;#10;if(done || req)$fatal;
          $display("PASS bypass");$finish;end endmodule''', 'tb',
          [ROOT / 'rtl/memory/workstation_ddr_bist.v'], 'PASS bypass')

    def test_static_cue_validation(self):
        validate_cues(ROOT / 'rtl/audio/scope_vec/data/scene_controls.mem', 69)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.mem'
            for rows in ('0000000100000000\n0000000000000000\n', '0000000000004000\n'):
                path.write_text(rows)
                with self.assertRaises(ValueError):
                    validate_cues(path, len(rows.splitlines()))

    def test_cpu_48k_banks_byte_writes_and_bounds(self):
        bench = (ROOT / 'sim/usb2/tb_workstation_usb2_cpu_bus.sv').read_text()
        bench = bench.replace('.BUS_TIMEOUT_CYCLES(32)', '.BUS_TIMEOUT_CYCLES(32),.RAM_BYTES(49152)')
        point = '        $display("PASS workstation_usb2_cpu_bus:'
        extra = '''        command(1,32'h00003ffc,32'h10203040,15);
        command(1,32'h00004000,32'h50607080,15);
        command(1,32'h00007ffc,32'h90a0b0c0,15);
        command(1,32'h00008000,32'hd0e0f001,15);
        command(1,32'h0000bffc,32'h12345678,15);
        command(1,32'h00004000,32'h00aa00bb,5);
        read_word(32'h3ffc,32'h10203040);read_word(32'h4000,32'h50aa70bb);
        read_word(32'h7ffc,32'h90a0b0c0);read_word(32'h8000,32'hd0e0f001);
        read_word(32'hbffc,32'h12345678);
        command(1,32'hc000,32'hffffffff,15);read_word(32'hc000,0);
        check(fault[0] && fault_address==32'hc000,"48K data bound");
        @(negedge clk);instruction_valid=1;instruction_address=32'hc000;
        @(negedge clk);check(instruction_response && instruction_error,"48K instruction bound");
        instruction_valid=0;
'''
        self.assertEqual(bench.count(point), 1)
        bench = bench.replace(point, extra+point)
        self.simulate(bench, 'tb_workstation_usb2_cpu_bus', [ROOT / 'rtl/usb2/workstation_usb2_cpu_bus.sv',
            ROOT / 'vendor/usb_host_fs_8fc3/src/simpleuart.v'], 'PASS workstation_usb2_cpu_bus:')

    def test_model_flash_and_uart_fallback_without_ddr_readback(self):
        from tools.build_cnn_flash_image import build_image
        bench = (ROOT / 'sim/model_flash/tb_boot_model.sv').read_text()
        bench = bench.replace('.UART_BAUD(3125000)', '.UART_BAUD(3125000),.VERIFY_DDR(0)')
        bench = bench.replace('reads!=WORDS', 'reads!=0')
        bench = bench.replace('        wait(done);repeat(10)',
                              '        wait(done);if(reads!=0)$fatal(1,"Unexpected model readback");repeat(10)')
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.hex'
            payload, _ = build_image([(index*7919 ^ 0xa53c)&65535 for index in range(31)])
            image.write_text(''.join(f'{value:02x}\n' for value in payload))
            for case in (0, 1, 7):
                with self.subTest(case=case):
                    self.simulate(bench, 'tb_boot_model', [ROOT / 'rtl/music' / name for name in (
                        'basic_pitch_flash_io_guard.sv', 'basic_pitch_boot_model_loader.sv',
                        'basic_pitch_flash_model_loader.sv', 'basic_pitch_uart_model_loader.sv',
                        'basic_pitch_uart_rx.sv')], f'PASS case={case}',
                        arguments=[f'+IMAGE={image}', f'+CASE={case}'])

    def test_ddr_pcm_maximum_window_and_cancelled_prefetch(self):
        model = DDR_MODEL.replace('wire sw,fetch,fetched,storage_ready,storage_fault;',
            'reg sw=0,fetch=0;wire fetched,storage_ready,storage_fault;')
        model = model.replace('wire [13:0] wa,ra;wire [31:0] wd,rd,fa;wire [12:0] fl;',
            'reg [13:0] wa=0,ra=0;reg [31:0] wd=0,fa=0;wire [31:0] rd;reg [12:0] fl=0;')
        bench = '''module tb;
        reg clk=0,resetn=0;always #10 clk=~clk;
        integer frame;
''' + model + '''
        initial begin
          repeat(5)@(negedge clk);resetn=1;wait(storage_ready);
          for(frame=0;frame<16384;frame=frame+1)begin
            @(negedge clk);wa=frame;wd=32'h12340000+frame;sw=1;
            @(negedge clk);sw=0;repeat(7)@(negedge clk);
          end
          // Abandon a prefetch while its DDR response is still outstanding.
          fa=0;fl=8112;fetch=1;wait(store.phase==2);
          @(negedge clk);fetch=0;repeat(2)@(negedge clk);
          fa=57424;fl=8112;fetch=1;wait(fetched);
          for(frame=14356;frame<16384;frame=frame+1)begin
            @(negedge clk);ra=frame;repeat(2)@(negedge clk);
            if(rd!==32'h12340000+frame)$fatal(1,"Max-window PCM mismatch %0d",frame);
          end
          @(negedge clk);fetch=0;repeat(4)@(negedge clk);
          $display("PASS max PCM window and cancelled prefetch");$finish;
        end
        initial begin #20000000;$fatal(1,"PCM max-window watchdog");end
        endmodule'''
        self.simulate(bench, 'tb', [ROOT / 'rtl/bluetooth/workstation_ble_pcm_store.sv',
            ROOT / 'rtl/music/music_async_fifo.sv'], 'PASS max PCM window')

    def test_ddr_pair_fairness_backpressure_and_response_ownership(self):
        self.simulate(r'''module tb;
          reg clk=0,rst=0;always #5 clk=~clk;
          integer a=0,b=0,cycle=0,pending=0,responses=0,expected_responses=0;
          reg response=0,response_b=0,held=0;reg [317:0] saved;
          wire ar,br,ap,bp,req,wr;wire [28:0] addr;wire [255:0] data;wire [31:0] mask;
          wire ready=cycle%5==0 && pending==0;
          workstation_ddr_pair dut(.clk_i(clk),.rst_ni(rst),
            .a_req_i(a<20),.a_write_i(a[0]),.b_req_i(b<20),.b_write_i(!b[0]),
            .a_address_i(29'h100+a),.b_address_i(29'h200+b),
            .a_data_i(256'h1111),.b_data_i(256'h2222),.a_mask_i(32'h1234),.b_mask_i(32'h5678),
            .a_ready_o(ar),.b_ready_o(br),.a_response_o(ap),.b_response_o(bp),
            .req_o(req),.write_o(wr),.address_o(addr),.data_o(data),.mask_o(mask),
            .ready_i(ready),.response_i(response));
          always @(posedge clk) if(rst)begin
            cycle<=cycle+1;response<=0;
            if(ar)begin
              if(addr!==29'h100+a || data!==256'h1111 || mask!==32'h1234)$fatal(1,"A payload");
              a<=a+1;
            end
            if(br)begin
              if(addr!==29'h200+b || data!==256'h2222 || mask!==32'h5678)$fatal(1,"B payload");
              b<=b+1;
            end
            if(ar && br)$fatal(1,"Double accept");
            if(held && {wr,addr,data,mask}!==saved)$fatal(1,"Stalled grant changed");
            held<=req && !ready;saved<={wr,addr,data,mask};
            if(req && ready && !wr)begin
              pending<=4;response_b<=addr[9];expected_responses<=expected_responses+1;
            end
            if(pending>0)begin pending<=pending-1;if(pending==1)response<=1;end
            if(response)begin
              if(ap===bp || bp!==response_b)$fatal(1,"Read ownership");
              responses<=responses+1;
            end
            if(a==20 && b==20 && responses==expected_responses && pending==0 && !response)begin
              $display("PASS fair DDR pair");$finish;
            end
          end
          initial begin #20;rst=1;#50000;$fatal(1,"DDR pair starvation");end
          endmodule''', 'tb', [ROOT / 'rtl/memory/workstation_ddr_pair.sv'], 'PASS fair DDR pair')

    def test_ddr_capture_overflow_is_reported(self):
        self.simulate(r'''module tb;
          reg clk=0,rst=0,mrst=0,write=0;always #5 clk=~clk;
          wire fault,ready;integer i,failures=0;
          workstation_ble_pcm_store dut(.clk_i(clk),.rst_ni(rst),.memory_clk_i(clk),.memory_rst_ni(mrst),
            .memory_ready_i(rst),.write_i(write),.write_frame_i(14'd0),.write_pcm_i(32'h12345678),
            .fetch_i(1'b0),.fetch_byte_i(32'd0),.fetch_bytes_i(13'd0),.fetched_o(),.ready_o(ready),.fault_o(fault),
            .read_frame_i(14'd0),.read_pcm_o(),.req_o(),.write_o(),.address_o(),.data_o(),.mask_o(),
            .req_ready_i(1'b0),.response_i(1'b0),.response_data_i(256'd0));
          always @(posedge clk)if(fault)failures<=failures+1;
          initial begin
            repeat(4)@(negedge clk);rst=1;mrst=1;wait(ready);repeat(8)@(negedge clk);
            write=1;repeat(40)@(negedge clk);write=0;
            if(failures==0)$fatal(1,"Overflow silently lost PCM");
            mrst=0;#1;if(ready)$fatal(1,"DDR-only reset must immediately revoke ready");
            repeat(3)@(negedge clk);mrst=1;wait(ready);
            rst=0;repeat(3)@(negedge clk);if(fault || ready)$fatal(1,"Overflow reset");
            $display("PASS PCM overflow");$finish;
          end endmodule''', 'tb', [ROOT / 'rtl/bluetooth/workstation_ble_pcm_store.sv',
            ROOT / 'rtl/music/music_async_fifo.sv'], 'PASS PCM overflow')


DDR_MODEL = r'''
    wire sw,fetch,fetched,storage_ready,storage_fault;
    wire [13:0] wa,ra;wire [31:0] wd,rd,fa;wire [12:0] fl;
    wire mr,mw;wire [28:0] ma;wire [255:0] md;wire [31:0] mm;
    reg mclk=0;always #7 mclk=~mclk;
    reg [255:0] memory[0:2047];reg [255:0] response_data=0,pending_data;
    reg response=0;integer count=0,delay_count=0,byte_lane;
    wire ready=(count%7)!=0 && delay_count==0;
    workstation_ble_pcm_store store(.clk_i(clk),.rst_ni(resetn),.memory_clk_i(mclk),
      .memory_rst_ni(resetn),.memory_ready_i(resetn),.write_i(sw),.write_frame_i(wa),.write_pcm_i(wd),
      .fetch_i(fetch),.fetch_byte_i(fa),.fetch_bytes_i(fl),.fetched_o(fetched),.ready_o(storage_ready),
      .fault_o(storage_fault),.read_frame_i(ra),.read_pcm_o(rd),.req_o(mr),.write_o(mw),
      .address_o(ma),.data_o(md),.mask_o(mm),.req_ready_i(ready),.response_i(response),
      .response_data_i(response_data));
    always @(posedge mclk) begin
      count<=count+1;response<=0;
      if(!resetn)delay_count<=0;
      else begin
        if(delay_count>0) begin
          delay_count<=delay_count-1;
          if(delay_count==1)begin response<=1;response_data<=pending_data;end
        end
        if(mr && ready) begin
          if(ma<29'h0c040000 || ma>29'h0c043ff8 || ma[2:0]!=0)$fatal(1,"PCM DDR allocation");
          if(mw)begin
            for(byte_lane=0;byte_lane<32;byte_lane=byte_lane+1)
              if(!mm[byte_lane])memory[(ma-29'h0c040000)>>3][byte_lane*8+:8]<=md[byte_lane*8+:8];
          end else begin
            pending_data<=memory[(ma-29'h0c040000)>>3];delay_count<=3+(count%13);
          end
        end
      end
    end
    always @(posedge clk) if(resetn && storage_fault)$fatal(1,"Unexpected PCM storage overflow");
'''

if __name__ == '__main__':
    unittest.main()
