`timescale 1ns/1ps
`default_nettype none
// GW25K complete instrument. All board I/O banks are powered at 3.3 V.
module midi_keyboard_top #(parameter integer HOST_PANEL_CONTROLS=1)(
 input wire clk_50mhz,clk_ulpi60,
 inout wire[7:0]ulpi_data,input wire ulpi_dir,ulpi_nxt,output wire ulpi_stp,
 input wire sw1_a,sw1_b,sw1_key_n,sw2_a,sw2_b,sw2_key_n,
 input wire module_uart_tx,output wire module_uart_rx,module_bt_dis_n,
 inout wire touch1_scl,touch1_sda,touch2_scl,touch2_sda,pca_scl,pca_sda,
 input wire touch_change_n,output wire ws2812_data,
 output wire lcd_mosi,lcd_sck,lcd_dc,lcd_ncs,
 input wire lcd_te,output wire led_ready,led_done
);
 localparam integer CLK_HZ=50000000;
 reg[19:0]por_count=0;
 wire reset=!(&por_count);
 always @(posedge clk_50mhz)if(reset)por_count<=por_count+1'b1;
 wire[15:0]raw_keys,keys,touch_errors;wire key_update,keypad_ready,slider_ready,slider_valid,slider_touch;
 wire[7:0]slider_position,slider_raw_position,slider_general_status,slider_sample_count;
 wire slider_overrun;
 midi_touch_frontend touch(.clk(clk_50mhz),.reset(reset),.change_n(touch_change_n),
  .touch1_scl(touch1_scl),.touch1_sda(touch1_sda),.touch2_scl(touch2_scl),.touch2_sda(touch2_sda),
  .key_bitmap(raw_keys),.key_update(key_update),.slider_valid(slider_valid),.slider_position(slider_position),
  .slider_touch(slider_touch),.keypad_ready(keypad_ready),.slider_ready(slider_ready),.errors(touch_errors),
  .slider_raw_position(slider_raw_position),.slider_general_status(slider_general_status),
  .slider_overrun(slider_overrun),.slider_sample_count(slider_sample_count));
 midi_key_layout key_layout(.raw_keys(raw_keys),.key_bitmap(keys));
 wire e1step,e1press,e1pressed,e1long,e2step,e2press,e2pressed,e2rawpress;wire signed[1:0]e1dir,e2dir;
 encoder_input #(.DETENTS_PER_STEP(HOST_PANEL_CONTROLS ? 1 : 2)) e1(.clk(clk_50mhz),.reset(reset),.a(sw1_a),.b(sw1_b),.key_n(sw1_key_n),
  .position(),.press_count(),.invalid_count(),.ab_state(),.key_pressed(e1pressed),.direction(e1dir),.step_pulse(e1step),.press_pulse());
 encoder_button_gestures #(.CLK_HZ(CLK_HZ)) e1_button(
  .clk(clk_50mhz),.reset(reset),.pressed(e1pressed),.short_press(e1press),.long_press(e1long));
 encoder_input #(.DETENTS_PER_STEP(HOST_PANEL_CONTROLS ? 1 : 2)) e2(.clk(clk_50mhz),.reset(reset),.a(sw2_a),.b(sw2_b),.key_n(sw2_key_n),
  .position(),.press_count(),.invalid_count(),.ab_state(),.key_pressed(e2pressed),.direction(e2dir),.step_pulse(e2step),.press_pulse(e2rawpress));
 wire e2short;
 encoder_button_gestures #(.CLK_HZ(CLK_HZ)) e2_button(
  .clk(clk_50mhz),.reset(reset),.pressed(e2pressed),.short_press(e2short),.long_press());
 assign e2press=HOST_PANEL_CONTROLS ? e2short : e2rawpress;
 wire uv,ur,urv,urr,cv,cr,crv,crr,usb_online,control_reset,hs_active;
 wire[31:0]ud,urd;wire[7:0]cd,crd;
 midi_usb2_link usb(.clk_50mhz(clk_50mhz),.reset(reset),.clk_ulpi60(clk_ulpi60),
  .ulpi_data(ulpi_data),.ulpi_dir(ulpi_dir),.ulpi_nxt(ulpi_nxt),.ulpi_stp(ulpi_stp),
  .midi_tx_valid(uv),.midi_tx_ready(ur),.midi_tx_data(ud),.midi_rx_valid(urv),.midi_rx_ready(urr),.midi_rx_data(urd),
  .control_tx_valid(cv),.control_tx_ready(cr),.control_tx_data(cd),.control_rx_valid(crv),.control_rx_ready(crr),.control_rx_data(crd),
  .online(usb_online),.control_reset(control_reset),.hs_active(hs_active));
 // Both business protocols share the existing vendor bulk interface. MIDI
 // keeps its own endpoints, queues and clocks while display traffic stalls.
 wire mk_rv,mk_rr,mk_tv,mk_tr,mk_reset,pl_rv,pl_rr,pl_tv,pl_tr,pl_reset;
 wire[7:0]mk_rd,mk_td,pl_rd,pl_td;
 screen_stream_router #(.CLK_HZ(CLK_HZ)) screen_router(
  .clk(clk_50mhz),.reset(reset||control_reset),
  .rx_valid(crv),.rx_ready(crr),.rx_data(crd),.tx_valid(cv),.tx_ready(cr),.tx_data(cd),
  .mk_rx_valid(mk_rv),.mk_rx_ready(mk_rr),.mk_rx_data(mk_rd),
  .mk_tx_valid(mk_tv),.mk_tx_ready(mk_tr),.mk_tx_data(mk_td),.mk_reset(mk_reset),
  .pl_rx_valid(pl_rv),.pl_rx_ready(pl_rr),.pl_rx_data(pl_rd),
  .pl_tx_valid(pl_tv),.pl_tx_ready(pl_tr),.pl_tx_data(pl_td),.pl_reset(pl_reset));
 wire remote_enable,manual_settings,redraw_required,tile_valid,tile_ready,tile_done;
 wire[8:0]tile_x,tile_width;wire[7:0]tile_y,tile_height,tile_read_addr;
 wire[15:0]tile_read_data,display_errors;
 panel_display_endpoint #(.CLK_HZ(CLK_HZ)) panel_input(
  .clk(clk_50mhz),.reset(reset),.link_reset(control_reset||pl_reset),.settings_toggle(HOST_PANEL_CONTROLS ? 1'b0 : e1long),
  .rx_valid(pl_rv),.rx_ready(pl_rr),.rx_data(pl_rd),.tx_valid(pl_tv),.tx_ready(pl_tr),.tx_data(pl_td),
  .remote_enable(remote_enable),.manual_settings(manual_settings),.redraw_required(redraw_required),
  .protocol_errors(display_errors),.tile_valid(tile_valid),.tile_ready(tile_ready),
  .tile_x(tile_x),.tile_y(tile_y),.tile_width(tile_width),.tile_height(tile_height),
  .tile_read_addr(tile_read_addr),.tile_read_data(tile_read_data),.tile_done(tile_done));
 wire bv,br,brv,brr,ble_online,ble_initialized,ble_failed;
 wire[39:0]bd,brd;wire[2:0]bl,brl;
 // A controller transport failure gets a fresh disable/patch cycle after 5 s.
 // Normal BLE disconnects are handled by the GATT transport without reboot.
 reg[27:0]ble_retry_count=0;reg ble_retry=0;
 always @(posedge clk_50mhz)begin
  ble_retry<=0;
  if(reset||!ble_failed)ble_retry_count<=0;
  else if(ble_retry_count==250000000-1)begin ble_retry_count<=0;ble_retry<=1;end
  else ble_retry_count<=ble_retry_count+1'b1;
 end
 midi_ble_link ble(.clk(clk_50mhz),.reset(reset||ble_retry),.module_uart_tx(module_uart_tx),
  .module_uart_rx(module_uart_rx),.module_bt_dis_n(module_bt_dis_n),
  .value_tx_valid(bv),.value_tx_ready(br),.value_tx_data(bd),.value_tx_length(bl),
  .value_rx_valid(brv),.value_rx_ready(brr),.value_rx_data(brd),.value_rx_length(brl),
  .online(ble_online),.initialized(ble_initialized),.failed(ble_failed));
 wire[3:0]channel,page;wire signed[7:0]transpose;wire[6:0]velocity,program_number;
 wire[1:0]slider_mode;wire[7:0]brightness,strip_value;wire[2:0]focus;
 wire[15:0]active_keys,lamp_keys,theme,background;wire panic_busy,screen_update;
 wire[31:0]status_flags,events;
 midi_keyboard_application #(.HOST_PANEL_CONTROLS(HOST_PANEL_CONTROLS)) app(.clk(clk_50mhz),.reset(reset),.control_reset(control_reset||mk_reset),.usb_online(usb_online),.ble_online(ble_online),
  .key_bitmap(keys),.keypad_ready(keypad_ready),.slider_valid(slider_valid),.slider_touch(slider_touch),.slider_position(slider_position),
  .enc1_step(e1step&&(HOST_PANEL_CONTROLS || !remote_enable)),.enc1_press(e1press&&(HOST_PANEL_CONTROLS || !remote_enable)),.enc1_direction(e1dir),
  .enc2_step(e2step&&(HOST_PANEL_CONTROLS || !remote_enable)),.enc2_press(e2press),.enc2_direction(e2dir),
  .usb_packet_tx_valid(uv),.usb_packet_tx_ready(ur),.usb_packet_tx_data(ud),.usb_packet_rx_valid(urv),.usb_packet_rx_ready(urr),.usb_packet_rx_data(urd),
  .ble_value_tx_valid(bv),.ble_value_tx_ready(br),.ble_value_tx_data(bd),.ble_value_tx_length(bl),.ble_value_rx_valid(brv),.ble_value_rx_ready(brr),.ble_value_rx_data(brd),.ble_value_rx_length(brl),
  .control_rx_valid(mk_rv),.control_rx_ready(mk_rr),.control_rx_data(mk_rd),.control_tx_valid(mk_tv),.control_tx_ready(mk_tr),.control_tx_data(mk_td),
  .midi_channel(channel),.transpose(transpose),.velocity(velocity),.program_number(program_number),.slider_mode(slider_mode),
  .brightness(brightness),.strip_value(strip_value),.focus(focus),.active_keys(active_keys),.lamp_keys(lamp_keys),.panic_busy(panic_busy),
  .theme_rgb565(theme),.clear_rgb565(background),.screen_page(page),.screen_update(screen_update),.status_flags(status_flags),.emitted_events(events));
 wire pca_ready;wire[15:0]pca_errors,strip_leds;
 // PCA9685 belongs to the slider; WS2812 belongs to the sixteen keys.
 midi_slider_led_map slider_lamps(.enabled(slider_ready),.position(strip_value),.led_bitmap(strip_leds));
 pca9685_led_driver lamps(.clk(clk_50mhz),.reset(reset),.scl(pca_scl),.sda(pca_sda),
  .led_bitmap(strip_leds),.brightness(brightness),.ready(pca_ready),.errors(pca_errors));
 midi_ws2812 rgb(.clk(clk_50mhz),.reset(reset),.key_bitmap(lamp_keys),.brightness(brightness),.data_out(ws2812_data));
 wire[8:0]px;wire[7:0]py;wire[15:0]color;wire snapshot;wire[31:0]frames;
 midi_landscape_view view(.clk(clk_50mhz),.reset(reset),.snapshot(snapshot),.key_bitmap(lamp_keys),
  .midi_channel(channel),.transpose(transpose),.velocity(velocity),.program_number(program_number),.slider_mode(slider_mode),
  .brightness(brightness),.strip_value(strip_value),.focus(focus),.usb_online(usb_online),.ble_online(ble_online),
  .touch_ready(keypad_ready&&slider_ready),.panic_busy(panic_busy),.theme_rgb565(theme),.clear_rgb565(background),
  .slider_ready(slider_ready),.slider_touched(slider_touch),.slider_raw_position(slider_raw_position),
  .slider_filtered_position(slider_position),.slider_error(touch_errors[15:8]),
  .slider_general_status(slider_general_status),.slider_overrun(slider_overrun),.slider_sample_count(slider_sample_count),
  .pixel_x(px),.pixel_y(py),.pixel_color(color));
 wire[26:0]dirty_regions;
 midi_display_regions regions(.clk(clk_50mhz),.reset(reset),.snapshot(snapshot),.key_bitmap(lamp_keys),
  .midi_channel(channel),.transpose(transpose),.velocity(velocity),.program_number(program_number),.slider_mode(slider_mode),
  .brightness(brightness),.strip_value(strip_value),.focus(focus),.usb_online(usb_online),.ble_online(ble_online),
  .touch_ready(keypad_ready&&slider_ready),.panic_busy(panic_busy),.theme_rgb565(theme),.clear_rgb565(background),
  .slider_ready(slider_ready),.slider_touched(slider_touch),.slider_raw_position(slider_raw_position),
  .slider_filtered_position(slider_position),.slider_error(touch_errors[15:8]),
  .slider_general_status(slider_general_status),.slider_overrun(slider_overrun),.slider_sample_count(slider_sample_count),
  .dirty_regions(dirty_regions));
 midi_landscape_display display(.clk(clk_50mhz),.reset(reset),.pixel_color(color),.dirty_regions(dirty_regions),.pixel_x(px),.pixel_y(py),
  .remote_enable(remote_enable),.tile_valid(tile_valid),.tile_ready(tile_ready),
  .tile_x(tile_x),.tile_y(tile_y),.tile_width(tile_width),.tile_height(tile_height),
  .tile_read_addr(tile_read_addr),.tile_read_data(tile_read_data),.tile_done(tile_done),
  .snapshot(snapshot),.completed_refreshes(frames),.lcd_ncs(lcd_ncs),.lcd_dc(lcd_dc),.lcd_sck(lcd_sck),.lcd_mosi(lcd_mosi));
 assign led_ready=keypad_ready&&slider_ready&&pca_ready;
 assign led_done=usb_online||ble_online;
endmodule
`default_nettype wire
