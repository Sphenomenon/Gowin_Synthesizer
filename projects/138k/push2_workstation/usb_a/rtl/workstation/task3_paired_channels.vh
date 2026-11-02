`ifndef TASK3_PAIRED_CHANNELS_VH
`define TASK3_PAIRED_CHANNELS_VH
// Internal typed transactions AFTER validated transport. Low payload bits are
// significant; unused high bits and high bits of the final byte MUST be zero.
// This is not an electrical LCD framing protocol or a replacement BLE format.
`define TASK3_PAIR_CH_ANALYSIS 4'd1
`define TASK3_PAIR_CH_ANALYSIS_CANCEL 4'd2
`define TASK3_PAIR_CH_RESULT 4'd3
`define TASK3_PAIR_CH_RECORD 4'd4
`define TASK3_PAIR_CH_RECORD_ACK 4'd5
`define TASK3_PAIR_CH_PHONE 4'd6
`define TASK3_PAIR_CH_PHONE_ACK 4'd7
`define TASK3_PAIR_CH_STATUS 4'd8
`define TASK3_PAIR_CH_RECORD_DEMAND 4'd9
`define TASK3_PAIR_KIND_ARM 2'd0
`define TASK3_PAIR_KIND_DATA 2'd1
`define TASK3_PAIR_KIND_CANCEL 2'd2
// Analysis ch1 low202={kind2,payload200}: 0 descriptor200,
// 1 {8'd0,identity128,index32,PCM32}, 2 {8'd0,identity128,frames32,CRC32}.
// ch2 low128=identity128. identity={Mboot32,session32,task32,generation32}.
// ch3 low168={terminal1,payload167}; score={identity128,index32,note7};
// terminal={3'd0,identity128,count32,code4}.
// Record ch4 low196={kind2,common96,body98}; common={Mboot,session,generation}.
// kind0 body={34'd0,epoch32,firstSequence32}; kind1 body=physical frame
// {44k1,error,epoch32,sequence32,PCM32}; kind2 body=98'd0.
// ch5 low98={common96,accepted1,rejected1}.
// Phone ch6 low180={kind2,common96,body82}; kind0/2 body=82'd0;
// kind1 body={requestSequence32,target1,write1,address12,data32,strobes4}.
// ch7 low163={kind2,common96,body65}; kind0 body={63'd0,accepted,rejected};
// kind1 body={requestSequence32,error1,data32}.
// ch8 low198={Wboot32,Mboot32,session32,generation32,HCIepoch32,
// HCIgeneration32,HCIready1,backendReady1,modelStatus4}; status never grants link.
// ch9 low98={kind2,common96}, length13: kind0 actual CPU/BLE source demand,
// kind2 demand cancelled/object terminal. M owns acceptance and physical tap ARM.
`define TASK3_PAIR_ANALYSIS_BYTES 6'd26
`define TASK3_PAIR_CANCEL_BYTES 6'd16
`define TASK3_PAIR_RESULT_BYTES 6'd21
`define TASK3_PAIR_RECORD_BYTES 6'd25
`define TASK3_PAIR_RECORD_ACK_BYTES 6'd13
`define TASK3_PAIR_PHONE_BYTES 6'd23
`define TASK3_PAIR_PHONE_ACK_BYTES 6'd21
`define TASK3_PAIR_STATUS_BYTES 6'd25
`define TASK3_PAIR_RECORD_DEMAND_BYTES 6'd13
`endif
