`timescale 1ns/1ps
module tb_gw138k_panel_controls;
    reg clk=0;always #10 clk=~clk;
    reg reset=1,control_reset=0,usb_online=0,ble_online=0;
    reg [15:0] key_bitmap=0;
    reg [799:0] touch_diagnostics=0;
    reg keypad_ready=1,slider_valid=0,slider_touch=0;
    reg [7:0] slider_position=0;
    reg enc1_step=0,enc1_press=0,enc2_step=0,enc2_press=0;
    reg signed [1:0] enc1_direction=1,enc2_direction=1;
    wire usb_packet_tx_valid;reg usb_packet_tx_ready=1;wire [31:0] usb_packet_tx_data;
    reg usb_packet_rx_valid=0;wire usb_packet_rx_ready;reg [31:0] usb_packet_rx_data=0;
    wire ble_value_tx_valid;reg ble_value_tx_ready=1;wire [39:0] ble_value_tx_data;
    wire [2:0] ble_value_tx_length;
    reg ble_value_rx_valid=0;wire ble_value_rx_ready;reg [39:0] ble_value_rx_data=0;
    reg [2:0] ble_value_rx_length=0;
    reg control_rx_valid=0;wire control_rx_ready;reg [7:0] control_rx_data=0;
    wire control_tx_valid;reg control_tx_ready=0;wire [7:0] control_tx_data;
    wire [3:0] midi_channel,screen_page;
    wire signed [7:0] transpose;
    wire [6:0] velocity,program_number;
    wire [1:0] slider_mode;
    wire [7:0] brightness,strip_value;
    wire [2:0] focus;
    wire [15:0] active_keys,lamp_keys,theme_rgb565,clear_rgb565;
    wire panic_busy,screen_update;
    wire [31:0] status_flags,emitted_events;
    midi_keyboard_application #(.CLK_HZ(4000),.FIFO_DEPTH(2)) dut(.pluck_diagnostics(512'd0),.pluck_noise_diagnostics(512'd0),.pluck_diagnostics_valid(1'b1),.input_config_write(),.input_config_opcode(),.input_config_value(),.*);
    wire [15:0] strip_leds;
    midi_slider_led_map slider_lamps(.enabled(1'b1),.position(strip_value),.led_bitmap(strip_leds));

    reg [23:0] messages[0:4095];integer received=0,ble_received=0,sequence_number=0,mark,i,last_bend,current_bend;
    reg stalled=0;reg[31:0] held_packet;
    always @(posedge clk)if(!reset)begin
      if(stalled && usb_online && (!usb_packet_tx_valid || usb_packet_tx_data!==held_packet))$fatal(1,"stalled USB changed");
      stalled=usb_online&&usb_packet_tx_valid&&!usb_packet_tx_ready;held_packet=usb_packet_tx_data;
      if(ble_value_tx_valid&&ble_value_tx_ready)ble_received=ble_received+1;
      if(usb_packet_tx_valid&&usb_packet_tx_ready)begin
        messages[received]={usb_packet_tx_data[15:8],usb_packet_tx_data[23:16],usb_packet_tx_data[31:24]};received=received+1;
      end
    end
    task ticks(input integer n);repeat(n)@(negedge clk);endtask
    task drain;begin ticks(400);if(usb_packet_tx_valid || dut.host_panel.performance.q_count!=0 || dut.host_panel.performance.valid_slot)$fatal(1,"panel did not drain");end endtask
    task expect_at(input integer n,input[23:0] value);begin if(messages[n]!==value)$fatal(1,"message %0d got %06h wanted %06h",n,messages[n],value);end endtask
    task step(input integer which,input integer direction);begin
      @(negedge clk);if(which==1)begin enc1_direction=direction;enc1_step=1;end else begin enc2_direction=direction;enc2_step=1;end
      @(negedge clk);enc1_step=0;enc2_step=0;
    end endtask
    task press(input integer which);begin
      @(negedge clk);if(which==1)enc1_press=1;else enc2_press=1;
      @(negedge clk);enc1_press=0;enc2_press=0;
    end endtask
    task slider(input integer pos,input integer touch);begin
      @(negedge clk);slider_position=pos;slider_touch=touch;slider_valid=1;
      @(negedge clk);slider_valid=0;
    end endtask
    function [15:0] crc_byte(input [15:0] crc,input [7:0] value);
        reg [15:0] work;integer bit_index;
        begin
            work=crc^{value,8'd0};
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)
                if(work[15])work=(work<<1)^16'h1021;else work=work<<1;
            crc_byte=work;
        end
    endfunction
    function [15:0] frame_crc(input [127:0] frame);
        reg [15:0] work;integer k;
        begin work=16'hffff;for(k=0;k<14;k=k+1)work=crc_byte(work,frame[k*8+:8]);frame_crc=work;end
    endfunction
    task control_request(input [7:0] opcode,input [31:0] value,input corrupt_crc,input [31:0] expected_status,input [31:0] expected_result);
        reg [127:0] request,response;reg [7:0] held_byte;integer k;
        begin
            sequence_number=sequence_number+1;
            request={16'd0,32'd0,value,sequence_number[15:0],opcode,8'h01,16'h4b4d};
            request[127:112]=frame_crc(request)^(corrupt_crc?16'd1:16'd0);
            for(k=0;k<16;k=k+1)begin
                @(negedge clk);control_rx_valid=1;control_rx_data=request[k*8+:8];
                while(!control_rx_ready)@(negedge clk);
                @(posedge clk);
            end
            @(negedge clk);control_rx_valid=0;
            while(!control_tx_valid)@(negedge clk);
            held_byte=control_tx_data;
            repeat(4)begin @(negedge clk);if(!control_tx_valid||control_tx_data!==held_byte)$fatal(1,"Control response changed under backpressure");end
            response=0;control_tx_ready=1;
            for(k=0;k<16;k=k+1)begin
                @(posedge clk);if(!control_tx_valid)$fatal(1,"Control response truncated");response[k*8+:8]=control_tx_data;
            end
            @(negedge clk);control_tx_ready=0;
            if(response[15:0]!==16'h4b4d||response[23:16]!==1||response[31:24]!==(opcode|8'h80)||
                response[47:32]!==sequence_number[15:0]||response[79:48]!==expected_status||
                response[111:80]!==expected_result||response[127:112]!==frame_crc(response))
                $fatal(1,"Bad control response %032h status/result wanted%0d/%h",response,expected_status,expected_result);
        end
    endtask
    initial begin
      ticks(5);reset=0;ticks(2);
      for(i=0;i<256;i=i+1)begin
        slider(i,1);
        if(strip_value!==i[7:0] || strip_leds!==16'((1<<((i+15)/16))-1))
          $fatal(1,"offline slider feedback frozen: pos=%0d strip=%0d leds=%04h",i,strip_value,strip_leds);
      end
      drain();
      if(received!=0 || ble_received!=0)$fatal(1,"offline slider emitted MIDI");
      usb_online=1;drain();
      if(strip_value!=255 || strip_leds!=16'hffff || received!=0)$fatal(1,"USB attach reset local slider or replayed offline bend");
      slider(255,0);drain();
      if(received!=0 || program_number!=73 || velocity!=100 || slider_mode!=2 || strip_value!=128 || dut.host_panel.performance.volume!=127)$fatal(1,"attach defaults or unexpected device initialization");
      key_bitmap=16'hffff;drain();if(received!=16)$fatal(1,"16 key presses");
      for(i=0;i<16;i=i+1)expect_at(i,{8'h90,8'(48+i),8'd100});
      drain();if(received!=16)$fatal(1,"held key repeated");
      key_bitmap=0;drain();if(received!=32)$fatal(1,"16 releases");
      for(i=0;i<16;i=i+1)expect_at(16+i,{8'h80,8'(48+i),8'd0});
      mark=received;step(1,-1);step(1,1);step(1,1);press(1);press(2);drain();
      if(received!=mark+4)$fatal(1,"encoder messages repeated or lost");
      expect_at(mark,24'hb0077e);expect_at(mark+1,24'hb0077f);expect_at(mark+2,24'hb05901);expect_at(mark+3,24'hb0587f);
      mark=received;repeat(5)step(2,1);step(2,-1);drain();
      expect_at(mark,24'hc02800);expect_at(mark+1,24'hc03800);expect_at(mark+2,24'hc00c00);
      expect_at(mark+3,24'hc00000);expect_at(mark+4,24'hc04900);expect_at(mark+5,24'hc00000);
      mark=received;slider(0,1);slider(128,1);slider(255,1);slider(255,0);slider(128,0);drain();
      if(received!=mark+4)$fatal(1,"bend release/repeat count");
      expect_at(mark,24'he00000);expect_at(mark+1,24'he00040);expect_at(mark+2,24'he07f7f);expect_at(mark+3,24'he00040);
      // All 256 positions are monotonic, with full endpoints and a center dead zone.
      last_bend=-1;
      for(i=0;i<256;i=i+1)begin
        mark=received;slider(i,1);drain();
        if(received>mark)begin
          if(received!=mark+1 || messages[mark][23:16]!=8'he0)$fatal(1,"slider is not Pitch Bend");
          current_bend={messages[mark][6:0],messages[mark][14:8]};
        end else current_bend=last_bend;
        if(current_bend<last_bend || (i==0 && current_bend!=0) || (i==255 && current_bend!=16383) || (i>=125 && i<=131 && current_bend!=8192))$fatal(1,"bend mapping %0d %0d",i,current_bend);
        last_bend=current_bend;
      end
      slider(255,0);drain();
      // Real MK control endpoint: held transposition must release every old note first.
      key_bitmap=3;drain();mark=received;
      control_request(8'h11,12,0,0,12);drain();
      if(received!=mark+4)$fatal(1,"held transpose event count");
      expect_at(mark,24'h803000);expect_at(mark+1,24'h803100);expect_at(mark+2,24'h903c64);expect_at(mark+3,24'h903d64);
      key_bitmap=0;drain();expect_at(received-2,24'h803c00);expect_at(received-1,24'h803d00);
      // Full downstream queue: retain individual toggles and volume steps in order.
      mark=received;usb_packet_tx_ready=0;
      repeat(20)begin press(1);press(2);end
      repeat(8)step(1,-1);
      ticks(100);if(!usb_packet_tx_valid)$fatal(1,"backpressure never reached codec");
      ble_online=1;ticks(5); // a new BLE link must not inherit or discard pending USB controls
      usb_packet_tx_ready=1;drain();if(ble_received!=0)$fatal(1,"new BLE inherited old controls");
      if(received!=mark+48)$fatal(1,"queued controls lost");
      for(i=0;i<20;i=i+1)begin expect_at(mark+2*i,24'hb05901);expect_at(mark+2*i+1,24'hb0587f);end
      for(i=0;i<8;i=i+1)expect_at(mark+40+i,{8'hb0,8'd7,8'(126-i)});
      ble_online=0;ticks(5);
      // Display/control session recovery must not reset local sound settings.
      mark=received;control_reset=1;ticks(3);control_reset=0;drain();
      if(received!=mark || program_number!=0 || dut.host_panel.performance.volume!=119)$fatal(1,"PL/MK session changed audio state");
      // Old stalled controls and held notes cannot be replayed after USB reconnect.
      usb_packet_tx_ready=0;press(2);key_bitmap=1;ticks(100);mark=received;
      usb_online=0;ticks(5);usb_online=1;ticks(5);usb_packet_tx_ready=1;drain();
      if(received!=mark || active_keys!=0 || program_number!=73 || dut.host_panel.performance.volume!=127)$fatal(1,"reconnect replay or local defaults");
      key_bitmap=0;drain();key_bitmap=1;drain();expect_at(received-1,24'h903c64);key_bitmap=0;drain();
      usb_online=0;ble_online=0;drain();mark=received;
      slider(0,1);
      if(strip_value!=0 || strip_leds!=0)$fatal(1,"disconnected slider left endpoint");
      slider(255,1);
      if(strip_value!=255 || strip_leds!=16'hffff)$fatal(1,"disconnected slider right endpoint");
      control_reset=1;ticks(3);control_reset=0;drain();
      if(strip_value!=255)$fatal(1,"control reset changed local slider");
      slider(255,0);
      if(strip_value!=128 || strip_leds!=16'h00ff)$fatal(1,"disconnected slider release did not center LEDs");
      usb_online=1;drain();
      if(received!=mark)$fatal(1,"reconnect replayed offline slider");
      if(dut.host_panel.performance.control_overflows!=0)$fatal(1,"control queue overflow");
      $display("METRIC offline_slider_positions=256 offline_led_release=1 attach_preserves_slider=1 offline_bend_replay=0");
      $display("METRIC keys=16 bend_positions=256 queued_controls=48 held_transpose=1 reconnect_replay=0 device_init_messages=0");
      $display("PASS tb_gw138k_panel_controls");$finish;
    end
    initial begin #100000000;$fatal(1,"panel control timeout");end
endmodule
