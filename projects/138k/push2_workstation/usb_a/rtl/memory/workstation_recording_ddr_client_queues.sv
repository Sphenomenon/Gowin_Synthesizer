`timescale 1ns/1ps
// One stable local request slot per client; no BSRAM or audio storage.
module workstation_recording_ddr_client_queues #(
    parameter TAG_BITS=5,
    parameter bit RECORDING_ENABLE=0
)(
    input wire clk,reset_n,bist_done,
    input wire bist_valid,bist_write,
    input wire [28:0] bist_address,
    input wire [255:0] bist_data,
    output wire bist_ready,bist_response,
    input wire scan_valid,
    input wire [28:0] scan_address,
    output wire scan_ready,scan_response,
    input wire display_valid,
    input wire [28:0] display_address,
    output wire display_ready,display_response,
    input wire audio_valid,audio_write,
    input wire [28:0] audio_address,
    input wire [255:0] audio_data,
    output wire audio_ready,audio_response,
    input wire music_valid,music_write,
    input wire [28:0] music_address,
    input wire [255:0] music_data,
    input wire [31:0] music_mask,
    output wire music_ready,music_response,
    input wire delay_valid,delay_write,
    input wire [28:0] delay_address,
    input wire [255:0] delay_data,
    output wire delay_ready,delay_response,
    input wire writer_valid,
    input wire [28:0] writer_address,
    input wire [255:0] writer_data,
    output wire writer_ready,
    input wire cpu_valid,cpu_write,
    input wire [28:0] cpu_address,
    input wire [255:0] cpu_data,
    input wire [31:0] cpu_mask,
    output wire cpu_ready,cpu_response,
    output wire [2:0] app_cmd,
    output wire app_en,app_wren,app_wend,
    output wire [28:0] app_address,
    output wire [255:0] app_data,
    output wire [31:0] app_mask,
    input wire app_ready,app_write_ready,app_response,
    input wire app_ready_fault_probe_i,
    input wire [255:0] app_response_data,
    output wire [255:0] response_data,
    output wire response_fault,
    input wire recording_valid,recording_write,
    input wire [28:0] recording_address,
    input wire [255:0] recording_data,
    input wire [31:0] recording_mask,
    output wire recording_ready,recording_response,
    output wire [8:0] slot_accept_o,core_accept_o,native_accept_o,
    output wire transport_fault_o,
    output wire [8:0] native_fault_probe_o
);
    generate if(!RECORDING_ENABLE)begin:g_legacy
        basic_pitch_ddr_client_queues #(.TAG_BITS(TAG_BITS)) u_legacy(
            .clk(clk),
            .reset_n(reset_n),
            .bist_done(bist_done),
            .bist_valid(bist_valid),
            .bist_write(bist_write),
            .bist_address(bist_address),
            .bist_data(bist_data),
            .bist_ready(bist_ready),
            .bist_response(bist_response),
            .scan_valid(scan_valid),
            .scan_address(scan_address),
            .scan_ready(scan_ready),
            .scan_response(scan_response),
            .display_valid(display_valid),
            .display_address(display_address),
            .display_ready(display_ready),
            .display_response(display_response),
            .audio_valid(audio_valid),
            .audio_write(audio_write),
            .audio_address(audio_address),
            .audio_data(audio_data),
            .audio_ready(audio_ready),
            .audio_response(audio_response),
            .music_valid(music_valid),
            .music_write(music_write),
            .music_address(music_address),
            .music_data(music_data),
            .music_mask(music_mask),
            .music_ready(music_ready),
            .music_response(music_response),
            .delay_valid(delay_valid),
            .delay_write(delay_write),
            .delay_address(delay_address),
            .delay_data(delay_data),
            .delay_ready(delay_ready),
            .delay_response(delay_response),
            .writer_valid(writer_valid),
            .writer_address(writer_address),
            .writer_data(writer_data),
            .writer_ready(writer_ready),
            .cpu_valid(cpu_valid),
            .cpu_write(cpu_write),
            .cpu_address(cpu_address),
            .cpu_data(cpu_data),
            .cpu_mask(cpu_mask),
            .cpu_ready(cpu_ready),
            .cpu_response(cpu_response),
            .app_cmd(app_cmd),
            .app_en(app_en),
            .app_wren(app_wren),
            .app_wend(app_wend),
            .app_address(app_address),
            .app_data(app_data),
            .app_mask(app_mask),
            .app_ready(app_ready),
            .app_write_ready(app_write_ready),
            .app_response(app_response),
            .app_response_data(app_response_data),
            .response_data(response_data),
            .response_fault(response_fault));
        assign recording_ready=0;assign recording_response=0;
        assign slot_accept_o={1'b0,display_valid&&display_ready,delay_valid&&delay_ready,music_valid&&music_ready,audio_valid&&audio_ready,writer_valid&&writer_ready,cpu_valid&&cpu_ready,scan_valid&&scan_ready,bist_valid&&bist_ready};
        assign native_fault_probe_o=0;
        assign core_accept_o=0;assign native_accept_o=0;
        assign transport_fault_o=response_fault;
    end else begin:g_recording
        // One legacy primitive per owner: no duplicate payload shadow buffer.
        wire [8:0] valid,write_kind,slot_ready,qvalid,qwrite,qready;
        wire [28:0] address[0:8],qaddress[0:8];
        wire [255:0] data[0:8],qdata[0:8];
        wire [31:0] mask[0:8],qmask[0:8];
        assign slot_accept_o=valid & slot_ready;
        assign valid[0]=bist_valid;assign write_kind[0]=bist_write;
        assign address[0]=bist_address;assign data[0]=bist_data;assign mask[0]=32'd0;
        assign bist_ready=slot_ready[0];
        assign valid[1]=scan_valid;assign write_kind[1]=1'b0;
        assign address[1]=scan_address;assign data[1]=256'd0;assign mask[1]=32'd0;
        assign scan_ready=slot_ready[1];
        assign valid[2]=cpu_valid;assign write_kind[2]=cpu_write;
        assign address[2]=cpu_address;assign data[2]=cpu_data;assign mask[2]=cpu_mask;
        assign cpu_ready=slot_ready[2];
        assign valid[3]=writer_valid;assign write_kind[3]=1'b1;
        assign address[3]=writer_address;assign data[3]=writer_data;assign mask[3]=32'd0;
        assign writer_ready=slot_ready[3];
        assign valid[4]=audio_valid;assign write_kind[4]=audio_write;
        assign address[4]=audio_address;assign data[4]=audio_data;assign mask[4]=32'd0;
        assign audio_ready=slot_ready[4];
        assign valid[5]=music_valid;assign write_kind[5]=music_write;
        assign address[5]=music_address;assign data[5]=music_data;assign mask[5]=music_mask;
        assign music_ready=slot_ready[5];
        assign valid[6]=delay_valid;assign write_kind[6]=delay_write;
        assign address[6]=delay_address;assign data[6]=delay_data;assign mask[6]=32'd0;
        assign delay_ready=slot_ready[6];
        assign valid[7]=display_valid;assign write_kind[7]=1'b0;
        assign address[7]=display_address;assign data[7]=256'd0;assign mask[7]=32'd0;
        assign display_ready=slot_ready[7];
        assign valid[8]=recording_valid;assign write_kind[8]=recording_write;
        assign address[8]=recording_address;assign data[8]=recording_data;assign mask[8]=recording_mask;
        assign recording_ready=slot_ready[8];
        for(genvar client=0;client<9;client=client+1)begin:g_slot
            basic_pitch_ddr_client_slot u_slot(
                .clk(clk),.reset_n(reset_n),.request_valid(valid[client]),.request_write(write_kind[client]),
                .request_address(address[client]),.request_data(data[client]),.request_mask(mask[client]),
                .request_ready(slot_ready[client]),.queued_valid(qvalid[client]),.queued_write(qwrite[client]),
                .queued_address(qaddress[client]),.queued_data(qdata[client]),.queued_mask(qmask[client]),
                .queued_ready(qready[client]));
        end
        workstation_recording_ddr_arbiter_pipeline #(.TAG_BITS(TAG_BITS),.REGISTER_GRANTS(1),.RECORDING_ENABLE(1)) u_core(
            .clk(clk),
            .reset_n(reset_n),
            .bist_done(bist_done),
            .bist_valid(qvalid[0]),
            .bist_write(qwrite[0]),
            .bist_address(qaddress[0]),
            .bist_data(qdata[0]),
            .bist_ready(qready[0]),
            .bist_response(bist_response),
            .scan_valid(qvalid[1]),
            .scan_address(qaddress[1]),
            .scan_ready(qready[1]),
            .scan_response(scan_response),
            .display_valid(qvalid[7]),
            .display_address(qaddress[7]),
            .display_ready(qready[7]),
            .display_response(display_response),
            .audio_valid(qvalid[4]),
            .audio_write(qwrite[4]),
            .audio_address(qaddress[4]),
            .audio_data(qdata[4]),
            .audio_ready(qready[4]),
            .audio_response(audio_response),
            .music_valid(qvalid[5]),
            .music_write(qwrite[5]),
            .music_address(qaddress[5]),
            .music_data(qdata[5]),
            .music_mask(qmask[5]),
            .music_ready(qready[5]),
            .music_response(music_response),
            .delay_valid(qvalid[6]),
            .delay_write(qwrite[6]),
            .delay_address(qaddress[6]),
            .delay_data(qdata[6]),
            .delay_ready(qready[6]),
            .delay_response(delay_response),
            .writer_valid(qvalid[3]),
            .writer_address(qaddress[3]),
            .writer_data(qdata[3]),
            .writer_ready(qready[3]),
            .cpu_valid(qvalid[2]),
            .cpu_write(qwrite[2]),
            .cpu_address(qaddress[2]),
            .cpu_data(qdata[2]),
            .cpu_mask(qmask[2]),
            .cpu_ready(qready[2]),
            .cpu_response(cpu_response),
            .app_cmd(app_cmd),
            .app_en(app_en),
            .app_wren(app_wren),
            .app_wend(app_wend),
            .app_address(app_address),
            .app_data(app_data),
            .app_mask(app_mask),
            .app_ready(app_ready),
            .app_write_ready(app_write_ready),
            .app_response(app_response),
            .app_response_data(app_response_data),
            .response_data(response_data),
            .response_fault(response_fault),
            .recording_valid(qvalid[8]),
            .recording_write(qwrite[8]),
            .recording_address(qaddress[8]),
            .recording_data(qdata[8]),
            .recording_mask(qmask[8]),
            .recording_ready(qready[8]),
            .app_ready_fault_probe_i(app_ready_fault_probe_i),
            .recording_response(recording_response),
            .core_accept_o(core_accept_o),
            .native_accept_o(native_accept_o),
            .native_fault_probe_o(native_fault_probe_o),
            .transport_fault_o(transport_fault_o));
    end endgenerate
endmodule
