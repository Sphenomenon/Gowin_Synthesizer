`timescale 1ns/1ps
// Control-only pattern store. No PCM memory or audio stream ports.
module sampler_sequencer(
  input logic clk,rst_n,panic,restart,sample_tick,start,stop,record_enable,
  input logic [8:0] bpm,input logic [5:0] swing, // BPM 30..300; swing 0..50 percent
  input logic select_valid,input logic [3:0] select_pattern,
  input logic edit_valid,input logic [3:0] edit_pattern,edit_step,
  input logic [1:0] edit_track,input logic [6:0] edit_note,edit_velocity,
  input logic [31:0] edit_gate_frames,
  input logic chain_write,input logic [3:0] chain_index,chain_pattern,
  input logic [4:0] chain_length,
  input logic live_valid,input logic [17:0] live_event,
  output logic event_valid,input logic event_ready,output logic [17:0] event_data,
  output logic [31:0] event_timestamp,sample_time,
  output logic running,click,
  output logic [3:0] pattern,step,
  output logic [63:0] grid,
  output logic [31:0] max_jitter_samples,dispatched,
  output logic [7:0] error
);
  import sampler_pkg::*;
  logic [3:0] chain[16],chain_pos;
  logic [63:0] grids[16];
  logic [7:0] ram_read_address,ram_write_address;
  logic [45:0] ram_data[4],ram_write_data;
  logic [3:0] ram_write;
  logic [2:0] fetch_delay;
  logic [31:0] fetch_time;
  logic [31:0] phase;logic target_odd,initial_step;
  logic [3:0] pending_pattern;logic pending;
  logic [3:0] held;logic [6:0] held_note[4];logic [31:0] off_time[4];
  // Eight independent control slots: at most off+on per track per timestamp.
  // Serial dispatch avoids a variable multi-write pointer chain in one clock.
  logic [7:0] queued;logic [3:0] on_first;
  logic [17:0] queued_data[8];logic [31:0] queued_time[8];
  logic [2:0] queue_index,candidate_index,locked_index;logic found,locked;
  integer dispatch_step,dispatch_pattern;
  logic [31:0] phase_next,threshold,now_time;
  logic do_step;
  // One 256x46 synchronous RAM per track. Data is not reset; validity bits are.
  for(genvar t=0;t<4;t++) begin:track_ram
    sampler_pattern_ram u_ram(.clk(clk),.rst_n(rst_n),.write(ram_write[t]),
      .write_address(ram_write_address),.write_data(ram_write_data),
      .read_address(ram_read_address),.read_data(ram_data[t]));
  end
  function automatic logic [31:0] gate_for_bpm(input logic [8:0] tempo);
    // ROM, rather than a long combinational divider on the live-record path.
    case(tempo)
      9'd30:gate_for_bpm=32'd24000;
      9'd31:gate_for_bpm=32'd23225;
      9'd32:gate_for_bpm=32'd22500;
      9'd33:gate_for_bpm=32'd21818;
      9'd34:gate_for_bpm=32'd21176;
      9'd35:gate_for_bpm=32'd20571;
      9'd36:gate_for_bpm=32'd20000;
      9'd37:gate_for_bpm=32'd19459;
      9'd38:gate_for_bpm=32'd18947;
      9'd39:gate_for_bpm=32'd18461;
      9'd40:gate_for_bpm=32'd18000;
      9'd41:gate_for_bpm=32'd17560;
      9'd42:gate_for_bpm=32'd17142;
      9'd43:gate_for_bpm=32'd16744;
      9'd44:gate_for_bpm=32'd16363;
      9'd45:gate_for_bpm=32'd16000;
      9'd46:gate_for_bpm=32'd15652;
      9'd47:gate_for_bpm=32'd15319;
      9'd48:gate_for_bpm=32'd15000;
      9'd49:gate_for_bpm=32'd14693;
      9'd50:gate_for_bpm=32'd14400;
      9'd51:gate_for_bpm=32'd14117;
      9'd52:gate_for_bpm=32'd13846;
      9'd53:gate_for_bpm=32'd13584;
      9'd54:gate_for_bpm=32'd13333;
      9'd55:gate_for_bpm=32'd13090;
      9'd56:gate_for_bpm=32'd12857;
      9'd57:gate_for_bpm=32'd12631;
      9'd58:gate_for_bpm=32'd12413;
      9'd59:gate_for_bpm=32'd12203;
      9'd60:gate_for_bpm=32'd12000;
      9'd61:gate_for_bpm=32'd11803;
      9'd62:gate_for_bpm=32'd11612;
      9'd63:gate_for_bpm=32'd11428;
      9'd64:gate_for_bpm=32'd11250;
      9'd65:gate_for_bpm=32'd11076;
      9'd66:gate_for_bpm=32'd10909;
      9'd67:gate_for_bpm=32'd10746;
      9'd68:gate_for_bpm=32'd10588;
      9'd69:gate_for_bpm=32'd10434;
      9'd70:gate_for_bpm=32'd10285;
      9'd71:gate_for_bpm=32'd10140;
      9'd72:gate_for_bpm=32'd10000;
      9'd73:gate_for_bpm=32'd9863;
      9'd74:gate_for_bpm=32'd9729;
      9'd75:gate_for_bpm=32'd9600;
      9'd76:gate_for_bpm=32'd9473;
      9'd77:gate_for_bpm=32'd9350;
      9'd78:gate_for_bpm=32'd9230;
      9'd79:gate_for_bpm=32'd9113;
      9'd80:gate_for_bpm=32'd9000;
      9'd81:gate_for_bpm=32'd8888;
      9'd82:gate_for_bpm=32'd8780;
      9'd83:gate_for_bpm=32'd8674;
      9'd84:gate_for_bpm=32'd8571;
      9'd85:gate_for_bpm=32'd8470;
      9'd86:gate_for_bpm=32'd8372;
      9'd87:gate_for_bpm=32'd8275;
      9'd88:gate_for_bpm=32'd8181;
      9'd89:gate_for_bpm=32'd8089;
      9'd90:gate_for_bpm=32'd8000;
      9'd91:gate_for_bpm=32'd7912;
      9'd92:gate_for_bpm=32'd7826;
      9'd93:gate_for_bpm=32'd7741;
      9'd94:gate_for_bpm=32'd7659;
      9'd95:gate_for_bpm=32'd7578;
      9'd96:gate_for_bpm=32'd7500;
      9'd97:gate_for_bpm=32'd7422;
      9'd98:gate_for_bpm=32'd7346;
      9'd99:gate_for_bpm=32'd7272;
      9'd100:gate_for_bpm=32'd7200;
      9'd101:gate_for_bpm=32'd7128;
      9'd102:gate_for_bpm=32'd7058;
      9'd103:gate_for_bpm=32'd6990;
      9'd104:gate_for_bpm=32'd6923;
      9'd105:gate_for_bpm=32'd6857;
      9'd106:gate_for_bpm=32'd6792;
      9'd107:gate_for_bpm=32'd6728;
      9'd108:gate_for_bpm=32'd6666;
      9'd109:gate_for_bpm=32'd6605;
      9'd110:gate_for_bpm=32'd6545;
      9'd111:gate_for_bpm=32'd6486;
      9'd112:gate_for_bpm=32'd6428;
      9'd113:gate_for_bpm=32'd6371;
      9'd114:gate_for_bpm=32'd6315;
      9'd115:gate_for_bpm=32'd6260;
      9'd116:gate_for_bpm=32'd6206;
      9'd117:gate_for_bpm=32'd6153;
      9'd118:gate_for_bpm=32'd6101;
      9'd119:gate_for_bpm=32'd6050;
      9'd120:gate_for_bpm=32'd6000;
      9'd121:gate_for_bpm=32'd5950;
      9'd122:gate_for_bpm=32'd5901;
      9'd123:gate_for_bpm=32'd5853;
      9'd124:gate_for_bpm=32'd5806;
      9'd125:gate_for_bpm=32'd5760;
      9'd126:gate_for_bpm=32'd5714;
      9'd127:gate_for_bpm=32'd5669;
      9'd128:gate_for_bpm=32'd5625;
      9'd129:gate_for_bpm=32'd5581;
      9'd130:gate_for_bpm=32'd5538;
      9'd131:gate_for_bpm=32'd5496;
      9'd132:gate_for_bpm=32'd5454;
      9'd133:gate_for_bpm=32'd5413;
      9'd134:gate_for_bpm=32'd5373;
      9'd135:gate_for_bpm=32'd5333;
      9'd136:gate_for_bpm=32'd5294;
      9'd137:gate_for_bpm=32'd5255;
      9'd138:gate_for_bpm=32'd5217;
      9'd139:gate_for_bpm=32'd5179;
      9'd140:gate_for_bpm=32'd5142;
      9'd141:gate_for_bpm=32'd5106;
      9'd142:gate_for_bpm=32'd5070;
      9'd143:gate_for_bpm=32'd5034;
      9'd144:gate_for_bpm=32'd5000;
      9'd145:gate_for_bpm=32'd4965;
      9'd146:gate_for_bpm=32'd4931;
      9'd147:gate_for_bpm=32'd4897;
      9'd148:gate_for_bpm=32'd4864;
      9'd149:gate_for_bpm=32'd4832;
      9'd150:gate_for_bpm=32'd4800;
      9'd151:gate_for_bpm=32'd4768;
      9'd152:gate_for_bpm=32'd4736;
      9'd153:gate_for_bpm=32'd4705;
      9'd154:gate_for_bpm=32'd4675;
      9'd155:gate_for_bpm=32'd4645;
      9'd156:gate_for_bpm=32'd4615;
      9'd157:gate_for_bpm=32'd4585;
      9'd158:gate_for_bpm=32'd4556;
      9'd159:gate_for_bpm=32'd4528;
      9'd160:gate_for_bpm=32'd4500;
      9'd161:gate_for_bpm=32'd4472;
      9'd162:gate_for_bpm=32'd4444;
      9'd163:gate_for_bpm=32'd4417;
      9'd164:gate_for_bpm=32'd4390;
      9'd165:gate_for_bpm=32'd4363;
      9'd166:gate_for_bpm=32'd4337;
      9'd167:gate_for_bpm=32'd4311;
      9'd168:gate_for_bpm=32'd4285;
      9'd169:gate_for_bpm=32'd4260;
      9'd170:gate_for_bpm=32'd4235;
      9'd171:gate_for_bpm=32'd4210;
      9'd172:gate_for_bpm=32'd4186;
      9'd173:gate_for_bpm=32'd4161;
      9'd174:gate_for_bpm=32'd4137;
      9'd175:gate_for_bpm=32'd4114;
      9'd176:gate_for_bpm=32'd4090;
      9'd177:gate_for_bpm=32'd4067;
      9'd178:gate_for_bpm=32'd4044;
      9'd179:gate_for_bpm=32'd4022;
      9'd180:gate_for_bpm=32'd4000;
      9'd181:gate_for_bpm=32'd3977;
      9'd182:gate_for_bpm=32'd3956;
      9'd183:gate_for_bpm=32'd3934;
      9'd184:gate_for_bpm=32'd3913;
      9'd185:gate_for_bpm=32'd3891;
      9'd186:gate_for_bpm=32'd3870;
      9'd187:gate_for_bpm=32'd3850;
      9'd188:gate_for_bpm=32'd3829;
      9'd189:gate_for_bpm=32'd3809;
      9'd190:gate_for_bpm=32'd3789;
      9'd191:gate_for_bpm=32'd3769;
      9'd192:gate_for_bpm=32'd3750;
      9'd193:gate_for_bpm=32'd3730;
      9'd194:gate_for_bpm=32'd3711;
      9'd195:gate_for_bpm=32'd3692;
      9'd196:gate_for_bpm=32'd3673;
      9'd197:gate_for_bpm=32'd3654;
      9'd198:gate_for_bpm=32'd3636;
      9'd199:gate_for_bpm=32'd3618;
      9'd200:gate_for_bpm=32'd3600;
      9'd201:gate_for_bpm=32'd3582;
      9'd202:gate_for_bpm=32'd3564;
      9'd203:gate_for_bpm=32'd3546;
      9'd204:gate_for_bpm=32'd3529;
      9'd205:gate_for_bpm=32'd3512;
      9'd206:gate_for_bpm=32'd3495;
      9'd207:gate_for_bpm=32'd3478;
      9'd208:gate_for_bpm=32'd3461;
      9'd209:gate_for_bpm=32'd3444;
      9'd210:gate_for_bpm=32'd3428;
      9'd211:gate_for_bpm=32'd3412;
      9'd212:gate_for_bpm=32'd3396;
      9'd213:gate_for_bpm=32'd3380;
      9'd214:gate_for_bpm=32'd3364;
      9'd215:gate_for_bpm=32'd3348;
      9'd216:gate_for_bpm=32'd3333;
      9'd217:gate_for_bpm=32'd3317;
      9'd218:gate_for_bpm=32'd3302;
      9'd219:gate_for_bpm=32'd3287;
      9'd220:gate_for_bpm=32'd3272;
      9'd221:gate_for_bpm=32'd3257;
      9'd222:gate_for_bpm=32'd3243;
      9'd223:gate_for_bpm=32'd3228;
      9'd224:gate_for_bpm=32'd3214;
      9'd225:gate_for_bpm=32'd3200;
      9'd226:gate_for_bpm=32'd3185;
      9'd227:gate_for_bpm=32'd3171;
      9'd228:gate_for_bpm=32'd3157;
      9'd229:gate_for_bpm=32'd3144;
      9'd230:gate_for_bpm=32'd3130;
      9'd231:gate_for_bpm=32'd3116;
      9'd232:gate_for_bpm=32'd3103;
      9'd233:gate_for_bpm=32'd3090;
      9'd234:gate_for_bpm=32'd3076;
      9'd235:gate_for_bpm=32'd3063;
      9'd236:gate_for_bpm=32'd3050;
      9'd237:gate_for_bpm=32'd3037;
      9'd238:gate_for_bpm=32'd3025;
      9'd239:gate_for_bpm=32'd3012;
      9'd240:gate_for_bpm=32'd3000;
      9'd241:gate_for_bpm=32'd2987;
      9'd242:gate_for_bpm=32'd2975;
      9'd243:gate_for_bpm=32'd2962;
      9'd244:gate_for_bpm=32'd2950;
      9'd245:gate_for_bpm=32'd2938;
      9'd246:gate_for_bpm=32'd2926;
      9'd247:gate_for_bpm=32'd2914;
      9'd248:gate_for_bpm=32'd2903;
      9'd249:gate_for_bpm=32'd2891;
      9'd250:gate_for_bpm=32'd2880;
      9'd251:gate_for_bpm=32'd2868;
      9'd252:gate_for_bpm=32'd2857;
      9'd253:gate_for_bpm=32'd2845;
      9'd254:gate_for_bpm=32'd2834;
      9'd255:gate_for_bpm=32'd2823;
      9'd256:gate_for_bpm=32'd2812;
      9'd257:gate_for_bpm=32'd2801;
      9'd258:gate_for_bpm=32'd2790;
      9'd259:gate_for_bpm=32'd2779;
      9'd260:gate_for_bpm=32'd2769;
      9'd261:gate_for_bpm=32'd2758;
      9'd262:gate_for_bpm=32'd2748;
      9'd263:gate_for_bpm=32'd2737;
      9'd264:gate_for_bpm=32'd2727;
      9'd265:gate_for_bpm=32'd2716;
      9'd266:gate_for_bpm=32'd2706;
      9'd267:gate_for_bpm=32'd2696;
      9'd268:gate_for_bpm=32'd2686;
      9'd269:gate_for_bpm=32'd2676;
      9'd270:gate_for_bpm=32'd2666;
      9'd271:gate_for_bpm=32'd2656;
      9'd272:gate_for_bpm=32'd2647;
      9'd273:gate_for_bpm=32'd2637;
      9'd274:gate_for_bpm=32'd2627;
      9'd275:gate_for_bpm=32'd2618;
      9'd276:gate_for_bpm=32'd2608;
      9'd277:gate_for_bpm=32'd2599;
      9'd278:gate_for_bpm=32'd2589;
      9'd279:gate_for_bpm=32'd2580;
      9'd280:gate_for_bpm=32'd2571;
      9'd281:gate_for_bpm=32'd2562;
      9'd282:gate_for_bpm=32'd2553;
      9'd283:gate_for_bpm=32'd2544;
      9'd284:gate_for_bpm=32'd2535;
      9'd285:gate_for_bpm=32'd2526;
      9'd286:gate_for_bpm=32'd2517;
      9'd287:gate_for_bpm=32'd2508;
      9'd288:gate_for_bpm=32'd2500;
      9'd289:gate_for_bpm=32'd2491;
      9'd290:gate_for_bpm=32'd2482;
      9'd291:gate_for_bpm=32'd2474;
      9'd292:gate_for_bpm=32'd2465;
      9'd293:gate_for_bpm=32'd2457;
      9'd294:gate_for_bpm=32'd2448;
      9'd295:gate_for_bpm=32'd2440;
      9'd296:gate_for_bpm=32'd2432;
      9'd297:gate_for_bpm=32'd2424;
      9'd298:gate_for_bpm=32'd2416;
      9'd299:gate_for_bpm=32'd2408;
      9'd300:gate_for_bpm=32'd2400;
      default:gate_for_bpm=1;
    endcase
  endfunction
  logic [3:0] live_step;
  integer live_track;
  logic accepted_live,accepted_off;
  logic [3:0] recorded;
  logic [6:0] recorded_note[4],recorded_velocity[4];
  logic [7:0] recorded_address[4];logic [31:0] recorded_time[4];
  always_comb begin
    live_track=(int'(live_event[13:7])-36)/16;live_step=step;
    if(phase*2>=(target_odd ? (720000+7200*swing) : 1440000+(720000+7200*swing))) live_step=step+1'b1;
    accepted_live=live_valid && record_enable && bpm>=30 && bpm<=300 &&
      live_event[17:14]==1 && live_event[6:0]!=0 && live_event[13:7]>=36 && live_event[13:7]<=99;
    accepted_off=live_valid && record_enable && live_track>=0 && live_track<4 &&
      recorded[live_track] && recorded_note[live_track]==live_event[13:7] &&
      (live_event[17:14]==0 || (live_event[17:14]==1 && live_event[6:0]==0));
    ram_write=0;ram_write_address={edit_pattern,edit_step};
    ram_write_data={edit_note,edit_velocity,edit_gate_frames==0 ? 32'd1 : edit_gate_frames};
    if(edit_valid) ram_write[edit_track]=1;
    if(accepted_live) begin
      ram_write=0;ram_write[live_track]=1;ram_write_address={pattern,live_step};
      ram_write_data={live_event[13:7],live_event[6:0],gate_for_bpm(bpm)};
    end else if(accepted_off) begin
      ram_write=0;ram_write[live_track]=1;ram_write_address=recorded_address[live_track];
      ram_write_data={recorded_note[live_track],recorded_velocity[live_track],
        sample_time==recorded_time[live_track] ? 32'd1 : sample_time-recorded_time[live_track]};
    end
  end
  task automatic queue_off(input integer t,input logic [6:0] key,input logic [31:0] timestamp);
    if(queued[t*2] && !(event_valid && event_ready && queue_index==3'(t*2))) error<=E_OVERFLOW;
    else begin on_first[t]<=queued[t*2+1];queued[t*2]<=1;queued_data[t*2]<={4'd0,key,7'd0};queued_time[t*2]<=timestamp;end
  endtask
  task automatic queue_on(input integer t,input logic [6:0] key,velocity,input logic [31:0] timestamp);
    if(queued[t*2+1] && !(event_valid && event_ready && queue_index==3'(t*2+1))) error<=E_OVERFLOW;
    else begin queued[t*2+1]<=1;queued_data[t*2+1]<={4'd1,key,velocity};queued_time[t*2+1]<=timestamp;end
  endtask
  always_comb begin
    candidate_index=0;found=0;
    for(int t=0;t<4;t++) if(!found && (queued[t*2] || queued[t*2+1])) begin
      found=1;
      // A stalled note-on must be dispatched before its later note-off.
      candidate_index=3'(t*2);
      if(queued[t*2+1] && (!queued[t*2] || on_first[t])) candidate_index=3'(t*2+1);
    end
  end
  assign queue_index=locked ? locked_index : candidate_index;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin locked<=0;locked_index<=0;end
    else begin
      if(event_valid && !event_ready && !locked) begin locked<=1;locked_index<=queue_index;end
      if(event_ready || panic || restart) locked<=0;
    end
  end
  assign event_valid=|queued;assign event_data=queued_data[queue_index];assign event_timestamp=queued_time[queue_index];
  assign grid=grids[pattern];
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin
      running<=0;click<=0;pattern<=0;step<=0;sample_time<=0;phase<=0;
      target_odd<=1;initial_step<=0;pending<=0;pending_pattern<=0;held<=0;
      queued<=0;on_first<=0;chain_pos<=0;max_jitter_samples<=0;dispatched<=0;error<=0;
      ram_read_address<=0;fetch_delay<=0;fetch_time<=0;recorded<=0;
      for(int t=0;t<4;t++) begin held_note[t]<=0;off_time[t]<=0;
        recorded_note[t]<=0;recorded_velocity[t]<=0;recorded_address[t]<=0;recorded_time[t]<=0;end
      for(int p=0;p<16;p++) begin chain[p]<=4'(p);grids[p]<=0;end
      for(int q=0;q<8;q++) begin queued_data[q]<=0;queued_time[q]<=0;end
    end else begin
      click<=0;do_step=0;now_time=sample_time+1;
      if(event_valid && event_ready) begin
        queued[queue_index]<=0;dispatched<=dispatched+1;
        if(sample_time-event_timestamp>max_jitter_samples) max_jitter_samples<=sample_time-event_timestamp;
      end
      if(sample_tick) sample_time<=now_time;
      if(edit_valid) grids[edit_pattern][int'(edit_track)*16+int'(edit_step)]<=edit_velocity!=0;
      if(accepted_live) begin
        grids[pattern][live_track*16+int'(live_step)]<=1;
        recorded[live_track]<=1;recorded_note[live_track]<=live_event[13:7];
        recorded_velocity[live_track]<=live_event[6:0];recorded_address[live_track]<={pattern,live_step};
        recorded_time[live_track]<=sample_time;
      end else if(accepted_off) recorded[live_track]<=0;
      if(chain_write) chain[chain_index]<=chain_pattern;
      if(select_valid) begin
        if(running) begin pending<=1;pending_pattern<=select_pattern;end
        else pattern<=select_pattern;
      end
      if(start) begin
        if(bpm<30 || bpm>300 || swing>50 || chain_length>16) error<=E_BOUNDS;
        else begin running<=1;phase<=0;target_odd<=1;initial_step<=1;step<=0;chain_pos<=0;end
      end
      if(sample_tick && running && !stop) begin
        if(bpm<30 || bpm>300 || swing>50 || chain_length>16) begin
          running<=0;error<=E_BOUNDS;
          for(int t=0;t<4;t++) if(held[t]) begin queue_off(t,held_note[t],now_time);held[t]<=0;end
        end else begin
          phase_next=phase+bpm;threshold=target_odd ? 720000+7200*swing : 1440000;
          if(initial_step) begin
            initial_step<=0;phase<=0;dispatch_step=0;dispatch_pattern=pattern;do_step=1;
          end else if(phase_next>=threshold) begin
            do_step=1;dispatch_step=(step+1)%16;dispatch_pattern=pattern;
            target_odd<=!target_odd;
            phase<=target_odd ? phase_next : phase_next-1440000;
            if(dispatch_step==0) begin
              if(pending) begin dispatch_pattern=pending_pattern;pending<=0;end
              else if(chain_length!=0) begin
                chain_pos<=4'(chain_pos+1>=chain_length ? 0 : chain_pos+1);
                dispatch_pattern=chain[chain_pos+1>=chain_length ? 0 : chain_pos+1];
              end
            end
          end else phase<=phase_next;
          if(do_step) begin
            step<=4'(dispatch_step);pattern<=4'(dispatch_pattern);click<=dispatch_step%4==0;
            ram_read_address<={4'(dispatch_pattern),4'(dispatch_step)};fetch_delay<=3;fetch_time<=now_time;
          end
          for(int t=0;t<4;t++) if(held[t] && $signed(now_time-off_time[t])>=0) begin
            queue_off(t,held_note[t],now_time);held[t]<=0;
          end
        end
      end
      // Pipeline has ample room in the 16-clock pre-render dispatch window.
      if(fetch_delay!=0) begin
        fetch_delay<=fetch_delay-1;
        if(fetch_delay==1 && running && !stop) for(int t=0;t<4;t++) if(ram_data[t][38:32]!=0) begin
          if(held[t]) queue_off(t,held_note[t],fetch_time);
          queue_on(t,ram_data[t][45:39],ram_data[t][38:32],fetch_time);
          held[t]<=1;held_note[t]<=ram_data[t][45:39];off_time[t]<=fetch_time+ram_data[t][31:0];
        end
      end
      if(stop) begin
        running<=0;fetch_delay<=0;
        for(int t=0;t<4;t++) if(held[t]) begin queue_off(t,held_note[t],sample_time);held[t]<=0;end
      end
      if(panic || restart) begin
        running<=0;held<=0;recorded<=0;queued<=0;on_first<=0;pending<=0;initial_step<=0;phase<=0;fetch_delay<=0;
      end
    end
  end
endmodule

module sampler_pattern_ram(
  input logic clk,rst_n,write,input logic [7:0] write_address,read_address,
  input logic [45:0] write_data,output logic [45:0] read_data
);
  logic [45:0] memory[256];logic [255:0] valid;
  logic [45:0] raw;logic read_valid;
  always_ff @(posedge clk) begin
    if(write) memory[write_address]<=write_data;
    raw<=memory[read_address];read_valid<=valid[read_address];
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) valid<=0;else if(write) valid[write_address]<=1;
  end
  assign read_data=read_valid ? raw : 46'd0;
endmodule
