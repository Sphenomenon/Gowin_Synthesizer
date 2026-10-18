`timescale 1ns/1ps
module audio_visual_extensions (
    input logic clk_i,rst_ni,sample_valid_i,
    input logic signed[31:0] left_i,right_i,
    input logic record_enable_i,record_ready_i,
    output logic record_valid_o,output logic[95:0] record_packet_o,
    output logic[31:0] record_drop_o,
    output logic fft_valid_o,output logic[7:0] fft_bin_o,
    output logic signed[23:0] fft_real_o,fft_imag_o,
    output logic[31:0] fft_frame_o,
    input logic score_write_i,input logic[7:0] score_address_i,
    input logic[63:0] score_data_i,input logic[8:0] score_length_i,
    input logic score_start_i,score_stop_i,
    output logic score_running_o,score_done_o,
    output logic[31:0] led_mask_o,score_frame_o
);
  spectrum_fft256 spectrum(.clk_i,.rst_ni,.sample_valid_i,.sample_i(left_i),
      .bin_valid_o(fft_valid_o),.bin_o(fft_bin_o),.real_o(fft_real_o),.imag_o(fft_imag_o),.frame_o(fft_frame_o));
  audio_capture_fifo recorder(.clk_i,.rst_ni,.enable_i(record_enable_i),.sample_valid_i,
      .left_i,.right_i,.valid_o(record_valid_o),.ready_i(record_ready_i),
      .packet_o(record_packet_o),.drop_count_o(record_drop_o));
  score_led_player score(.clk_i,.rst_ni,.sample_ce_i(sample_valid_i),.write_i(score_write_i),
      .write_address_i(score_address_i),.write_data_i(score_data_i),.start_i(score_start_i),
      .stop_i(score_stop_i),.length_i(score_length_i),.running_o(score_running_o),
      .done_o(score_done_o),.leds_o(led_mask_o),.frame_o(score_frame_o));
endmodule
