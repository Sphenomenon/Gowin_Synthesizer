`timescale 1ns/1ps
module sampler_voice # (parameter integer N=16)(
  input logic clk,rst_n,restart,panic,sample_tick,
  input logic event_valid, input logic [17:0] event_data,
  input sampler_pkg::pad_t event_pad,
  input sampler_pkg::descriptor_t event_descriptor,
  output logic event_ready,
  output logic read_valid, input logic read_ready,
  output logic [31:0] read_address,read_base,read_capacity,
  input logic response_valid,input logic [255:0] response_data,
  input logic [7:0] response_error,
  output logic pcm_valid,output logic signed [15:0] pcm_l,pcm_r,
  output logic [N-1:0] active_mask,
  output logic [63:0] referenced,
  output logic [5:0] active_count,
  output logic [31:0] deadline_misses,read_beats,frame_cycles_max,
  output logic [7:0] error
);
  import sampler_pkg::*;
  pad_t cfg[N]; descriptor_t desc[N];
  logic [6:0] key[N],velocity[N],pressure[N];
  logic [47:0] phase[N]; logic [31:0] increment[N];
  logic [15:0] envelope[N];logic [1:0] env_state[N];
  logic releasing[N];logic [255:0] cache[N];logic cache_valid[N];logic [31:0] cache_addr[N];
  typedef enum logic [4:0] {IDLE,SELECT,A_REQ,A_WAIT,B_SELECT,B_REQ,B_WAIT,MIX,GAIN,ENV_GAIN,VOL_GAIN,VEL_GAIN,PRESS_GAIN,PAN_L,PAN_R,ADVANCE,ADVANCE_COMMIT,WRAP,FINISH} state_t;
  state_t state;logic [$clog2(N)-1:0] v;integer chosen,frame_cycles;
  logic [31:0] index_a,index_b,addr_a,addr_b;
  logic signed [15:0] a,b;
  logic signed [39:0] acc_l,acc_r;
  logic signed [31:0] scaled;logic signed [63:0] interpolated;
  logic [31:0] wrap_distance;
  logic [15:0] wrap_numerator,wrap_divisor,wrap_fraction,wrap_remainder;
  logic [47:0] wrap_anchor;
  logic wrap_reverse;
  logic [4:0] wrap_bit;
  logic [16:0] trial;
  logic [15:0] reduced;
  logic [31:0] loop_span,registered_span,registered_distance;
  logic [47:0] computed_phase;
  pad_t work_cfg;
  descriptor_t work_desc;
  logic [47:0] work_phase;
  logic [31:0] work_increment;
  logic [15:0] work_envelope;
  logic [6:0] work_velocity,work_pressure;
  logic work_releasing;
  logic [1:0] work_env_state;
  logic [15:0] next_env;
  logic [47:0] next_phase;
  logic [47:0] lo,hi,span;
  logic [3:0] kind;logic [6:0] note,value;
  assign kind=event_data[17:14];assign note=event_data[13:7];assign value=event_data[6:0];
  assign event_ready=(state==IDLE && !sample_tick && !restart && !panic);
  assign read_valid=(state==A_REQ && !(cache_valid[v] && cache_addr[v]==addr_a)) ||
    (state==B_REQ && !(cache_valid[v] && cache_addr[v]==addr_b));
  assign read_address=state==A_REQ ? addr_a : addr_b;
  assign read_base=desc[v].base_bytes;assign read_capacity=desc[v].capacity_bytes;
  always_comb begin
    active_count=0;referenced=0;
    for(int k=0;k<N;k++) if(active_mask[k]) begin active_count=active_count+1'b1;referenced[cfg[k].slot]=1;end
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin
      state<=IDLE;v<=0;active_mask<=0;pcm_valid<=0;pcm_l<=0;pcm_r<=0;
      deadline_misses<=0;read_beats<=0;frame_cycles_max<=0;error<=OK;
      frame_cycles<=0;acc_l<=0;acc_r<=0;index_a<=0;index_b<=0;addr_a<=0;addr_b<=0;a<=0;b<=0;scaled<=0;
      work_cfg<='0;work_desc<='0;work_phase<=0;work_increment<=0;work_envelope<=0;
      work_velocity<=0;work_pressure<=0;work_releasing<=0;work_env_state<=0;
      wrap_numerator<=0;wrap_divisor<=1;wrap_fraction<=0;wrap_remainder<=0;
      wrap_anchor<=0;wrap_reverse<=0;wrap_bit<=0;registered_span<=0;registered_distance<=0;computed_phase<=0;
      for(int k=0;k<N;k++) begin
        cfg[k]<='0;desc[k]<='0;key[k]<=0;velocity[k]<=0;pressure[k]<=127;
        phase[k]<=0;increment[k]<=65536;envelope[k]<=0;env_state[k]<=0;
        releasing[k]<=0;cache[k]<=0;cache_valid[k]<=0;cache_addr[k]<=0;
      end
    end else begin
      pcm_valid<=0;
      if(restart || panic) begin
        state<=IDLE;active_mask<=0;pcm_l<=0;pcm_r<=0;
        for(int k=0;k<N;k++) begin cache_valid[k]<=0;envelope[k]<=0;releasing[k]<=0;end
      end else begin
        if(state!=IDLE) begin
          frame_cycles<=frame_cycles+1;
          if(sample_tick) begin deadline_misses<=deadline_misses+1;error<=E_DEADLINE;end
        end
        if(event_valid && event_ready) begin
          if(kind==1 && value!=0) begin
            chosen=-1;
            // One-shot retrigger chokes the same physical key; gated voices are polyphonic.
            for(int k=0;k<N;k++) if(active_mask[k] && key[k]==note && cfg[k].play_mode==ONE_SHOT) chosen=k;
            for(int k=0;k<N;k++) if(!active_mask[k] && chosen<0) chosen=k;
            if(chosen<0) error<=E_CAPACITY;
            else if(!event_descriptor.valid || event_pad.trim_start>=event_pad.trim_end ||
              event_pad.trim_end>event_descriptor.frames || event_descriptor.frames>event_descriptor.capacity_bytes/2 || event_pad.play_mode>LOOPED ||
              (event_pad.play_mode==LOOPED && (event_pad.loop_start<event_pad.trim_start ||
              event_pad.loop_end>event_pad.trim_end || event_pad.loop_start>=event_pad.loop_end))) error<=E_BOUNDS;
            else begin
              active_mask[chosen]<=1;cfg[chosen]<=event_pad;desc[chosen]<=event_descriptor;
              key[chosen]<=note;velocity[chosen]<=value;pressure[chosen]<=127;
              phase[chosen]<=event_pad.reverse ? {(event_pad.play_mode==LOOPED ? event_pad.loop_end : event_pad.trim_end)-32'd1,16'd0} : {event_pad.trim_start,16'd0};
              increment[chosen]<=pitch_ratio(note,event_pad.root_note);
              envelope[chosen]<=event_pad.attack_inc==0 ? 16'hffff : 0;
              env_state[chosen]<=event_pad.attack_inc==0 ? 1 : 0;
              releasing[chosen]<=0;cache_valid[chosen]<=0;
            end
          end else if(kind==0 || (kind==1 && value==0) || (kind==2 && note==123)) begin
            for(int k=0;k<N;k++) if(active_mask[k] && (key[k]==note || kind==2) && (kind==2 || cfg[k].play_mode!=ONE_SHOT)) releasing[k]<=1;
          end else if(kind==5) begin
            for(int k=0;k<N;k++) if(active_mask[k] && key[k]==note) pressure[k]<=value;
          end
        end
        case(state)
          IDLE: if(sample_tick) begin v<=0;frame_cycles<=0;acc_l<=0;acc_r<=0;state<=SELECT;end
          SELECT: if(!active_mask[v]) begin
            if(v==N-1) state<=FINISH;else v<=v+1;
          end else begin
            work_cfg<=cfg[v];work_desc<=desc[v];work_phase<=phase[v];work_increment<=increment[v];
            work_envelope<=envelope[v];work_velocity<=velocity[v];work_pressure<=pressure[v];
            work_releasing<=releasing[v];work_env_state<=env_state[v];
            index_a<=phase[v][47:16];
            index_b<=phase[v][47:16]+1>=((cfg[v].play_mode==LOOPED) ? cfg[v].loop_end : cfg[v].trim_end) ?
              ((cfg[v].play_mode==LOOPED) ? cfg[v].loop_start : cfg[v].trim_end-1) : phase[v][47:16]+1;
            addr_a<=(desc[v].base_bytes+(phase[v][47:16]<<1)) & 32'hffffffe0;
            state<=A_REQ;
          end
          A_REQ: begin
            if(cache_valid[v] && cache_addr[v]==addr_a) begin a<=$signed(cache[v][index_a[3:0]*16+:16]);state<=B_SELECT;end
            else if(read_ready) state<=A_WAIT;
          end
          A_WAIT: if(response_valid) begin
            if(response_error!=OK) begin error<=response_error;active_mask[v]<=0;state<=MIX;a<=0;b<=0;scaled<=0;end
            else begin
              cache[v]<=response_data;cache_addr[v]<=addr_a;cache_valid[v]<=1;
              a<=$signed(response_data[index_a[3:0]*16+:16]);read_beats<=read_beats+1;state<=B_SELECT;
            end
          end
          B_SELECT: begin addr_b<=(desc[v].base_bytes+(index_b<<1)) & 32'hffffffe0;state<=B_REQ;end
          B_REQ: begin
            if(cache_valid[v] && cache_addr[v]==addr_b) begin b<=$signed(cache[v][index_b[3:0]*16+:16]);state<=MIX;end
            else if(read_ready) state<=B_WAIT;
          end
          B_WAIT: if(response_valid) begin
            if(response_error!=OK) begin error<=response_error;active_mask[v]<=0;a<=0;b<=0;scaled<=0;end
            else begin
              cache[v]<=response_data;cache_addr[v]<=addr_b;cache_valid[v]<=1;
              b<=$signed(response_data[index_b[3:0]*16+:16]);read_beats<=read_beats+1;
            end
            state<=MIX;
          end
          MIX: begin
            interpolated=$signed(a)+((($signed(b)-$signed(a))*$signed({1'b0,work_phase[15:0]}))>>>16);
            scaled<=interpolated;state<=GAIN;
          end
          GAIN:begin scaled<=(64'(scaled)*$signed({1'b0,work_desc.gain_q16}))>>>16;state<=ENV_GAIN;end
          ENV_GAIN:begin scaled<=(64'(scaled)*$signed({1'b0,work_envelope}))>>>16;state<=VOL_GAIN;end
          VOL_GAIN:begin scaled<=(64'(scaled)*$signed({1'b0,work_cfg.volume}))>>>16;state<=VEL_GAIN;end
          VEL_GAIN:begin scaled<=(64'(scaled)*$signed({1'b0,midi_gain(work_velocity)}))>>>16;state<=PRESS_GAIN;end
          PRESS_GAIN:begin scaled<=(64'(scaled)*$signed({1'b0,midi_gain(work_pressure)}))>>>16;state<=PAN_L;end
          PAN_L:begin acc_l<=acc_l+((64'(scaled)*$signed({1'b0,midi_gain(7'(127-work_cfg.pan))}))>>>16);state<=PAN_R;end
          PAN_R:begin acc_r<=acc_r+((64'(scaled)*$signed({1'b0,midi_gain(work_cfg.pan)}))>>>16);state<=ADVANCE;end
          ADVANCE: begin
            next_env=work_envelope;
            if(work_releasing) begin
              if(work_cfg.release_inc==0 || work_envelope<=work_cfg.release_inc) begin next_env=0;active_mask[v]<=0;end
              else next_env=work_envelope-work_cfg.release_inc;
            end else case(work_env_state)
              0: if({1'b0,work_envelope}+work_cfg.attack_inc>=65535) begin next_env=65535;env_state[v]<=1;end
                 else next_env=work_envelope+work_cfg.attack_inc;
              1: if(work_envelope<=work_cfg.sustain || work_cfg.decay_inc>=work_envelope-work_cfg.sustain) begin next_env=work_cfg.sustain;env_state[v]<=2;end
                 else next_env=work_envelope-work_cfg.decay_inc;
              default:begin end
            endcase
            envelope[v]<=next_env;
            lo={work_cfg.loop_start,16'd0};hi={work_cfg.loop_end,16'd0};loop_span=work_cfg.loop_end-work_cfg.loop_start;
            wrap_reverse<=work_cfg.reverse;wrap_anchor<=work_cfg.reverse ? hi : lo;
            if(work_cfg.reverse) begin
              if(work_cfg.play_mode==LOOPED && work_phase<lo+work_increment) begin
                wrap_distance=32'(lo+work_increment-work_phase-1);
                next_phase=hi-1-{32'(wrap_distance[31:16]),wrap_distance[15:0]};
              end else if(work_phase<{work_cfg.trim_start,16'd0}+work_increment) begin
                next_phase={work_cfg.trim_start,16'd0};active_mask[v]<=0;wrap_distance=0;
              end else begin next_phase=work_phase-work_increment;wrap_distance=0;end
            end else begin
              next_phase=work_phase+work_increment;wrap_distance=0;
              if(work_cfg.play_mode==LOOPED && next_phase>=hi) begin
                wrap_distance=32'(next_phase-hi);next_phase=lo+wrap_distance;
              end else if(next_phase>={work_cfg.trim_end,16'd0}) begin
                next_phase={work_cfg.trim_end-32'd1,16'd0};active_mask[v]<=0;
              end
            end
            computed_phase<=next_phase;registered_span<=loop_span;registered_distance<=wrap_distance;
            state<=ADVANCE_COMMIT;
          end
          ADVANCE_COMMIT:begin
            phase[v]<=computed_phase;
            if(work_cfg.play_mode==LOOPED && registered_distance[31:16]>=registered_span) begin
              wrap_numerator<=registered_distance[31:16];wrap_fraction<=registered_distance[15:0];
              wrap_divisor<=registered_span[15:0];wrap_remainder<=0;wrap_bit<=15;state<=WRAP;
            end else if(v==N-1) state<=FINISH;else begin v<=v+1;state<=SELECT;end
          end
          WRAP:begin
            // 16-bit restoring remainder, one bounded subtract per clock.
            trial={wrap_remainder,wrap_numerator[wrap_bit]};
            reduced=16'(trial>=wrap_divisor ? trial-wrap_divisor : trial);
            wrap_remainder<=reduced;
            if(wrap_bit==0) begin
              phase[v]<=wrap_reverse ? wrap_anchor-1-{16'd0,reduced,wrap_fraction} :
                wrap_anchor+{16'd0,reduced,wrap_fraction};
              if(v==N-1) state<=FINISH;else begin v<=v+1;state<=SELECT;end
            end else wrap_bit<=wrap_bit-1'b1;
          end
          FINISH: begin
            pcm_l<=sat16(acc_l);pcm_r<=sat16(acc_r);pcm_valid<=1;state<=IDLE;
            if(frame_cycles+1>frame_cycles_max) frame_cycles_max<=frame_cycles+1;
          end
          default:state<=IDLE;
        endcase
      end
    end
  end
endmodule
