`timescale 1ns/1ps
module complete_case #(parameter bit SYNTH=1)(output reg finished=0);
reg clk=0,rst=0,v=0,act=0,extbusy=0,failed=0,busy=0,request=0,rate=0,history=0;
reg quiet=1,fxready=1,lifecycle=0;wire accepted,ready;
workstation_audio_render_service #(.RUNTIME_RATE_ENABLE(1),.RUNTIME_EFFECTS_ENABLE(1),.SYNTH_ENGINES_ENABLE(SYNTH),.D_ONLY_ENABLE(!SYNTH)) dut(
 .clk_i(clk),.rst_ni(rst),.config_valid_i(v),.config_rate_44100_i(rate),.history_clear_i(history),
 .config_ready_o(ready),.config_accepted_o(accepted),.render_request_i(request),.render_44k1_i(rate),
 .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
 .cpu_event_valid_i(1'b0),.cpu_event_i(18'd0),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
 .delay_peer_heartbeat_i(1'b0),.delay_dma_fault_i(1'b0),.delay_mem_clk_i(clk),.delay_mem_rst_ni(rst),
 .delay_dwr_pop_i(1'b0),.delay_drd_push_i(1'b0),.delay_drd_data_i(65'd0));
integer checks=0,one=0,zero=0,unknowns=0;integer k,e;
function automatic digit4(input integer value);begin case(value&3)0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase end endfunction
task check;begin #2;
 if(accepted !== (v && ready))$fatal(1,"RECEIPT mismatch synth=%0d n=%0d valid=%b ready=%b receipt=%b",SYNTH,checks,v,ready,accepted);
 if(dut.core_rate_accepted !== dut.workstation.engine_rate_commit)$fatal(1,"not actual engine broadcast");
 checks=checks+1;case(accepted)1:one=one+1;0:zero=zero+1;default:unknowns=unknowns+1;endcase
end endtask
initial begin
force dut.active=act;force dut.external_busy=extbusy;force dut.held_rate=1'b0;force dut.response_sent=1'b0;force dut.cancelled=1'b0;
force dut.cancel_delivery_pending=1'b0;
force dut.workstation.runtime_configuration.busy=busy;force dut.workstation.runtime_configuration.failed=failed;
force dut.workstation.runtime_configuration.pipeline_quiet=quiet;force dut.workstation.fx_fault=1'b0;
force dut.workstation.fx_config_ready=fxready;force dut.workstation.usb_lifecycle=lifecycle;
force dut.workstation.native_clear=1'b0;force dut.workstation.pending=1'b0;force dut.workstation.releasing=1'b0;
force dut.workstation.load_busy=1'b0;force dut.workstation.mix_busy=1'b0;force dut.workstation.vec_busy=1'b0;
force dut.workstation.mode_pending=1'b0;force dut.workstation.mode_ready=1'b1;force dut.workstation.event_valid=1'b0;
force dut.workstation.event_data=18'd0;force dut.workstation.allocated=32'd0;force dut.workstation.core_event_ready=1'b1;
force dut.workstation.core_expression_ready=1'b1;force dut.workstation.scope_enable=1'b0;force dut.workstation.deferred_current=1'b1;
force dut.workstation.runtime_quiescent=1'b1;force dut.workstation.vec_ready=1'b1;force dut.workstation.fx_sample_slot_ready=1'b1;
force dut.workstation.synth_joined=1'b0;force dut.workstation.vec_joined=1'b0;
#2;rst=1;
for(e=0;e<4;e=e+1)begin rate=e&1;history=(e>>1)&1;
for(k=0;k<4096;k=k+1)begin v=digit4(k);act=digit4(k>>2);extbusy=digit4(k>>4);failed=digit4(k>>6);busy=digit4(k>>8);request=digit4(k>>10);check();end end
v=1;act=0;extbusy=0;failed=0;busy=0;request=1;history=0;rate=0;
for(k=0;k<256;k=k+1)begin quiet=digit4(k);fxready=digit4(k>>2);lifecycle=digit4(k>>4);rst=digit4(k>>6);check();end
if(one==0 || zero==0 || unknowns==0)$fatal(1,"missing four-state coverage");
$display("PASS COMPLETE_RECEIPT_FOUR_STATE synth=%0d checks=%0d one=%0d zero=%0d unknown=%0d",SYNTH,checks,one,zero,unknowns);finished=1;
end
endmodule
module tb;wire m,w;complete_case #(.SYNTH(1)) master_case(m);complete_case #(.SYNTH(0)) worker_case(w);
initial begin wait(m&&w);$display("PASS COMPLETE_RECEIPT_ALL_FOUR_STATE");$finish;end
initial begin #1000000;$fatal(1,"timeout");end endmodule
