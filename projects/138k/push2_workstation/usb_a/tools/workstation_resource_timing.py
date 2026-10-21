"""Bounded structure fixes for the resource candidate's measured setup paths.

Clock periods, waveform tables and feature choices are preserved.
The two synthesized Gray MSB aliases retain their original 10 ns bound.
The APB mailbox reserves one audio cycle for local read-address predecode.
"""
from pathlib import Path
import hashlib
import re
from cnn_ddr_pipeline_patch import pipeline_tf_read_return


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('timing transform anchor drift: ' + old[:100])
    return text.replace(old, new, 1)


def apb(text):
    text=once(text,'logic req_settled, ack_settled;', 'logic req_settled, ack_settled, request_decoded;')
    text=once(text,'assign command_valid=command_reset_n && req_settled!=acknowledge_toggle;',
              'assign command_valid=command_reset_n && request_decoded && req_settled!=acknowledge_toggle;')
    text=once(text,'req_meta<=0; req_sync<=0; req_settled<=0;', 'req_meta<=0; req_sync<=0; req_settled<=0;request_decoded<=0;')
    text=once(text,'if(req_sync!=req_settled) request_local<=request_held;', '''if(req_sync!=req_settled)begin request_local<=request_held;request_decoded<=0;end
            else if(req_settled!=acknowledge_toggle)request_decoded<=1;
            else request_decoded<=0;''')
    return text


def services(text):
    # Only CPU events can stall this service. Other register validity, such as
    # recorder emptiness, must not feed the entire mailbox's clock enable.
    text=once(text,'assign command_ready=!cpu_event_valid || cpu_event_ready;', '''wire malformed_event=command_strobes!=4'hf || command_data[31:18]!=0 ||
        command_data[17:14]>6 || (command_data[17:14]==1 && command_data[6:0]==0) ||
        (command_data[17:14]==6 && command_data[13:7]>1);
    assign command_ready=!command_write || !event_address || malformed_event || cpu_event_ready;''')
    reads=[('184','control_state'),('188','control_pitch'),('18c','control_options'),
           ('190','held_notes[31:0]'),('194','held_notes[63:32]'),('198','held_notes[95:64]'),('19c','held_notes[127:96]'),
           ('1a0','applied_events'),('1a4','pc_health'),('1a8','snap_status'),('1ac','snap_sequence'),('1b0','snap_left'),('1b4','snap_right'),
           ('000',"32'h41313338"),('004',"32'h00010000"),('008',"32'd63"),('014',"{31'd0,snapshot_valid}")]
    reads += [(f'{0x20+4*i:03x}',f"(snapshot_valid ? snapshot[{i}] : 32'd0)") for i in range(9)]
    reads += [('080',"{31'd0,record_enable}"),('084',"{30'd0,record_valid,record_snapshot_valid}"),
              ('08c',"(record_snapshot_valid ? record_snapshot[95:64] : 32'd0)"),
              ('090',"(record_snapshot_valid ? record_snapshot[63:32] : 32'd0)"),
              ('094',"(record_snapshot_valid ? record_snapshot[31:0] : 32'd0)"),
              ('100',"{24'd0,score_address}"),('104','cue_time'),('108','cue_mask'),
              ('110',"{23'd0,score_length}"),('11c',"{30'd0,done_sticky,score_running}"),
              ('124','led_mask'),('128','score_frame'),('12c',"{23'd0,loaded}")]
    declarations=f'    reg [{len(reads)-1}:0] read_select_q;\n'
    declarations+='    always @(posedge clk or negedge reset_n)begin\n        if(!reset_n)read_select_q<=0;\n        else begin\n'
    for i,(addr,value) in enumerate(reads):declarations+=f"            read_select_q[{i}]<=!command_write && command_address==12'h{addr};\n"
    declarations+='        end\n    end\n    wire [31:0] decoded_read_data=\n'
    declarations+=' |\n'.join(f'        ({{32{{read_select_q[{i}]}}}} & {value})' for i,(addr,value) in enumerate(reads))+';\n'
    text=once(text,'    integer i;\n',declarations+'    integer i;\n')
    # Keep original error validation. Remove the wide address/data priority mux
    # from the actual output; the registered one-hot selection drives that word.
    text=once(text,'    always_ff @(posedge clk or negedge reset_n) begin',
              '    always_ff @(posedge clk or negedge reset_n) begin')
    # Rename only the combinational intermediate, leaving port API unchanged.
    start=text.index('    always_comb begin');end=text.index('    always_ff',start)
    block=text[start:end].replace('response_data','unused_read_data')
    text=text[:start]+'    logic [31:0] unused_read_data;\n'+block+text[end:]
    text=once(text,'    integer i;\n', '    assign response_data=decoded_read_data;\n    integer i;\n')
    return services_writes(text)



def services_writes(text):
    text=once(text,
        'assign cpu_event_valid=command_valid && command_write && event_address && !response_error;',
        'assign cpu_event_valid=command_valid && command_write && event_address && !(command_strobes!=4\'hf || command_data[31:18]!=0 || command_data[17:14]>6 || (command_data[17:14]==1 && command_data[6:0]==0) || (command_data[17:14]==6 && command_data[13:7]>1));')
    rules=[("12'h1a8",'1\'b1'),("12'h1ac",'1\'b1'),("12'h1b0",'1\'b1'),("12'h1b4",'1\'b1'),
      ('SNAPSHOT','command_data==1'),('REC_ENABLE','command_data<=1'),
      ('REC_POP','command_data==1 && record_valid && !record_snapshot_valid'),
      ('REC_RELEASE','command_data==1 && record_snapshot_valid'),
      ('SCORE_ADDR','command_data<=255 && !score_running'),
      ('SCORE_TIME','!score_running'),('SCORE_MASK','!score_running'),
      ('SCORE_COMMIT',"command_data==1 && !score_running && loaded!=256 && {1'b0,score_address}==loaded && (loaded==0 || cue_time>=previous_time)"),
      ('SCORE_LENGTH','command_data!=0 && command_data<=256 && !score_running'),
      ('SCORE_START','command_data==1 && !score_running && score_length!=0 && score_length<=loaded'),
      ('SCORE_STOP','command_data==1'),('SCORE_CLEAR','command_data==1 && !score_running')]
    indices={address:i for i,(address,_) in enumerate(rules)}
    declarations=f'    reg [{len(rules)-1}:0] write_select_q;\n'
    declarations+='    always @(posedge clk or negedge reset_n)begin\n        if(!reset_n)write_select_q<=0;\n        else begin\n'
    for i,(address,_) in enumerate(rules):
        declarations+=f'            write_select_q[{i}]<=command_write && command_address=={address};\n'
    declarations+='        end\n    end\n'
    for i,(_,condition) in enumerate(rules):
        declarations+=f"    wire write_allow_{i}=command_valid && command_strobes==4'hf && write_select_q[{i}] && ({condition});\n"
    text=once(text,'    wire event_address=',declarations+'    wire event_address=')
    for name,address in [('record_ready','REC_POP'),('score_write','SCORE_COMMIT')]:
        text=once(text,f'assign {name}=legal_write && command_address=={address};',f'assign {name}=write_allow_{indices[address]};')
    for name,address in [('score_start','SCORE_START'),('score_stop','SCORE_STOP')]:
        text=once(text,f'(legal_write && command_address=={address})',f'write_allow_{indices[address]}')
    start=text.index('            if(legal_write) case(command_address)')
    end=text.index('            endcase',start)+len('            endcase')
    block=text[start:end]
    entries=list(re.finditer(r"^                (12'h[0-9a-f]+|[A-Z_]+|default):",block,re.M))
    actions=[]
    for i,entry in enumerate(entries):
        address=entry.group(1)
        if address=='default':continue
        tail=entries[i+1].start() if i+1<len(entries) else block.index('            endcase')
        body=block[entry.end():tail].strip()
        actions.append(f'            if(write_allow_{indices[address]})begin {body} end')
    if len(actions)!=len(rules)-1:raise ValueError('service write actions drift')
    return text[:start]+'\n'.join(actions)+text[end:]


def event_fifo(text):
    text=once(text,'    consume_r_gry <= \\$99 ;', '''    if(r_rst)consume_r_gry<=produce_r_gry;
    else if(\\$3 )consume_r_gry<=consume_increment_gray;''')
    anchor="  assign \\$69  = \\$4 [6:0] ^ { 1'h0, \\$4 [6:1] };"
    text=once(text,anchor,'''  wire [6:0] consume_increment=consume_r_bin+7'd1;
  wire [6:0] consume_increment_gray=(consume_increment>>1)^consume_increment;
'''+anchor)
    return text


def diagnostics(text):
    text=once(text,'    reg [31:0] pixel_frame_count;', '    reg [31:0] pixel_frame_count;\n    reg frame_tick_q,frame_low_carry;')
    text=once(text,'            pixel_frame_count <= 0;', '            pixel_frame_count <= 0;frame_tick_q<=0;frame_low_carry<=0;')
    text=once(text,'            if (vblank_start) begin', '''            frame_tick_q<=vblank_start;
            frame_low_carry<=&pixel_frame_count[15:0];
            if (frame_tick_q) begin''')
    text=once(text,'                if (&pixel_frame_count[15:0])', '                if (frame_low_carry)')
    return text



def dashboard(text):
    # Four target positions are constants. Compute each movement before the
    # live effect-order selection, removing metadata decode from arithmetic.
    declarations = ''
    for effect in range(3):
        terms = []
        remaining = f'effect_mask[{effect}]'
        for slot, target in enumerate((64, 400, 736)):
            select = f'dash_select_{effect}_{slot}'
            test = f'effect_order[{slot*2+1}:{slot*2}]==2\'d{effect}'
            declarations += f'    wire {select}=({remaining}) && ({test});\n'
            remaining += f' && !({test})'
            terms.append(f'({{11{{{select}}}}} & slide(effect_x{effect},11\'d{target}))')
        declarations += f'    wire dash_select_{effect}_3=!effect_mask[{effect}] || ({remaining});\n'
        terms.append(f'({{11{{dash_select_{effect}_3}}}} & slide(effect_x{effect},11\'d1120))')
        declarations += f'    wire [10:0] dash_next_{effect}=' + ' | '.join(terms) + ';\n'
        text=once(text,f'slide(effect_x{effect},destination({effect}))', f'dash_next_{effect}')
    anchor='    always @(posedge clk or negedge reset_n) begin\n        if (!reset_n) begin\n            effect_x0'
    text=once(text, anchor, declarations + anchor)
    return dashboard_labels(text)




def dashboard_labels(text):
    text=once(text,'text_line=effect_name(effect_id);text_y=888;text_enable=1;',
              'text_y=888;text_enable=1;')
    text=once(text,'text_line=visible_mask[effect_id] ? "ON                              " : "OFF                             ";','')
    text=once(text,'    reg a_effect_hit,a_effect_edge,a_effect_on;',
        '    reg a_effect_hit,a_effect_edge,a_effect_on;\n    reg a_effect_label,a_effect_status;')
    text=once(text,'a_effect_hit<=0; a_effect_edge<=0; a_effect_on<=0; a_effect_id<=0;',
        'a_effect_hit<=0; a_effect_edge<=0; a_effect_on<=0; a_effect_id<=0;a_effect_label<=0;a_effect_status<=0;')
    text=once(text,'            a_effect_hit<=effect_hit; a_effect_id<=effect_id;',"""            a_effect_hit<=effect_hit; a_effect_id<=effect_id;
            a_effect_label<=effect_hit && effect_relative>=16 && effect_relative<272 && pixel_y>=888 && pixel_y<904;
            a_effect_status<=effect_hit && effect_relative>=16 && effect_relative<272 && pixel_y>=920 && pixel_y<936;""")
    text=once(text,'    always @* begin\n        next_character =',"""    wire [255:0] effect_label_word=effect_name(a_effect_id);
    wire [255:0] effect_status_word=a_effect_on ? "ON                              " : "OFF                             ";
    always @* begin
        next_character =""")
    text=once(text,'        next_hex_digit =',"""        if(a_effect_label)next_character=effect_label_word[255-a_text_index*8 -:8];
        if(a_effect_status)next_character=effect_status_word[255-a_text_index*8 -:8];
        next_hex_digit =""")
    old='    wire [2:0] font_row = large_text ? relative_text_y[4:2] : relative_text_y[3:1];'
    new="""    // Every enabled label has a fixed vertical origin. Compute the row
    // from raster bands directly, independent of horizontal/card hit priority.
    wire font_origin8=(pixel_y>=168 && pixel_y<184) ||
        (pixel_y>=840 && pixel_y<856) || (pixel_y>=888 && pixel_y<904) ||
        (pixel_y>=920 && pixel_y<936) || (pixel_y>=968 && pixel_y<984) ||
        (ENABLE_ANALYSIS && ((pixel_y>=200 && pixel_y<216) ||
          (pixel_x>=8 && pixel_x<56 && ((pixel_y>=568 && pixel_y<584) ||
           (pixel_y>=632 && pixel_y<648) || (pixel_y>=696 && pixel_y<712) ||
           (pixel_y>=760 && pixel_y<776)))));
    wire [3:0] font_origin=font_origin8 ? 4'd8 :
        (ENABLE_ANALYSIS && pixel_x<1104 && pixel_y>=804 && pixel_y<820 ? 4'd4 : 4'd0);
    wire [3:0] font_small_relative=pixel_y[3:0]-font_origin;
    wire [2:0] font_row=title_large ? pixel_y[4:2]^3'd4 : font_small_relative[3:1];"""
    text=once(text,old,new)
    text=once(text,'    wire [4:0] text_index =', '    wire title_large=pixel_y>=48 && pixel_y<80 && pixel_x>=64 && pixel_x<1088;\n    wire [4:0] text_index =')
    text=once(text,'text_index = large_text ?', 'text_index = title_large ?')
    return once(text,'font_column = large_text ?', 'font_column = title_large ?')


def event_dispatch(text):
    # dispatch already requires idle engines and no sample request. Within that
    # domain mode_ready means only allocated==0; both note endpoints are ready
    # (a full Note On is consumed and rejected at the workstation as before).
    text=once(text,
        'assign dispatch=!usb_lifecycle && !pending && !sample_ce_i && !load_busy && !mix_busy && !vec_busy && !mode_valid;',
        'assign dispatch=!usb_lifecycle && !pending && !sample_ce_i && !load_busy && !mix_busy && !vec_busy && !(mode_pending && allocated==0);')
    return once(text,
        'event_ready=dispatch && ((kind==1 && full) || (scope_enable ? vec_event_ready : core_event_ready));',
        'event_ready=dispatch;')



def voice_count(text):
    old="""  always @* begin
    active_voice_count_o = '0;
    active_mask_o = '0;"""
    declarations=''
    for level in range(1,6):
        count=32>>level
        declarations+=f'  wire [{level}:0] active_count_{level}[0:{count-1}];\n'
        for j in range(count):
            a=f'active_mask_o[{j*2}]' if level==1 else f'active_count_{level-1}[{j*2}]'
            b=f'active_mask_o[{j*2+1}]' if level==1 else f'active_count_{level-1}[{j*2+1}]'
            declarations+=f"  assign active_count_{level}[{j}]={{1'b0,{a}}}+{{1'b0,{b}}};\n"
    declarations+='  assign active_voice_count_o=active_count_5[0];\n'
    text=once(text,old,declarations+"  always @* begin\n    active_mask_o = '0;")
    return once(text,"        active_voice_count_o = active_voice_count_o + 6'd1;\n",'')



def lifecycle(text):
    text=once(text,'gw138k_three_event_arbiter queue(', 'gw138k_elastic_event_arbiter queue(')
    text=once(text,'.clk(clk),.reset_n(reset_n),', '.clk(clk),.reset_n(reset_n),.clear(cancel),')
    return text+"""
// Two complete event words. Input readiness is independent of output ready;
// direct lifecycle cancellation purges both old words atomically.
module gw138k_elastic_event_arbiter(
 input wire clk,reset_n,clear,g1_valid,pc_valid,cpu_valid,
 input wire [17:0]g1_data,pc_data,cpu_data,
 output wire g1_ready,pc_ready,cpu_ready,
 output wire event_valid,output wire [17:0]event_data,input wire event_ready);
 reg [1:0]first,selected,count;
 reg head,tail;reg [17:0]data[0:1];
 wire room=count<2;
 wire push=room && (g1_valid || pc_valid || cpu_valid);
 wire pop=event_valid && event_ready;
 always @*begin
  selected=0;
  case(first)
   0:if(g1_valid)selected=0;else if(pc_valid)selected=1;else selected=2;
   1:if(pc_valid)selected=1;else if(cpu_valid)selected=2;else selected=0;
   default:if(cpu_valid)selected=2;else if(g1_valid)selected=0;else selected=1;
  endcase
 end
 assign g1_ready=room && selected==0;
 assign pc_ready=room && selected==1;
 assign cpu_ready=room && selected==2;
 assign event_valid=count!=0;
 assign event_data=data[head];
 always @(posedge clk or negedge reset_n)begin
  if(!reset_n)begin count<=0;head<=0;tail<=0;first<=0;data[0]<=0;data[1]<=0;end
  else if(clear)begin count<=0;head<=0;tail<=0;end
  else begin
   case({push,pop})2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:count<=count;endcase
   if(pop)head<=!head;
   if(push)begin
    data[tail]<=selected==0?g1_data:selected==1?pc_data:cpu_data;tail<=!tail;
    first<=selected==2?0:selected+1'b1;
   end
  end
 end
endmodule
"""


def tf_dma(text):
    text=pipeline_tf_read_return(text)
    old="""        if(!rst_n)begin write_buf<=0;write_clear_pending<=0;end
        else if(epoch_clear)begin write_buf<=0;write_clear_pending<=0;end
        else begin
            write_clear_pending<=write_accept;
            if(write_clear_pending)write_buf<=0;
            else if(state==S_STREAM && fifo_in_rd_valid && !capture_limit_hit)
                write_buf[write_count*8 +:8]<=fifo_in_rd_data;
        end"""
    new="""        if(!rst_n)begin write_buf<=0;write_clear_pending<=0;end
        else begin
            write_clear_pending<=epoch_clear || write_accept;
            if(write_clear_pending)write_buf<=0;
            else if(state==S_STREAM && fifo_in_rd_valid && !capture_limit_hit)
                write_buf[write_count*8 +:8]<=fifo_in_rd_data;
        end"""
    text=once(text,old,new)
    text=once(text,'if (!write_pending && !in_read_wait && !fifo_in_empty &&',
                'if (!write_clear_pending && !write_pending && !in_read_wait && !fifo_in_empty &&')
    # The counter candidate is only consumed after a request. While no request
    # is outstanding it can sample every clock; acceptance no longer drives
    # the clock enable of all 32 payload bits. Holds through zero-cycle return.
    text=once(text,'    reg [31:0] read_total_pending;',
        '    reg [31:0] read_total_pending;\n    always @(posedge clk)if(!read_pending)read_total_pending<=read_total_after_accept;')
    return once(text,'                    read_total_pending <= read_total_after_accept;\n','')


def scanout_request(text):
    text=once(text,'    reg request_toggle, ack_toggle;',
        '    reg request_toggle, ack_toggle;\n    reg fetch_line_q;')
    text=once(text,'request_toggle<=0; held_request<=0;',
        'request_toggle<=0; held_request<=0;fetch_line_q<=0;')
    text=once(text,'ack_meta<=ack_toggle; ack_sync<=ack_meta;',
        'ack_meta<=ack_toggle; ack_sync<=ack_meta;\n            fetch_line_q<=pixel_x==WIDTH-2 && pixel_y<HEIGHT-2;')
    return once(text,'pixel_x==WIDTH-1 && pixel_y<HEIGHT-2 && ack_sync==request_toggle',
        'fetch_line_q && ack_sync==request_toggle')


def raster(text):
    text=once(text,'    reg [10:0] vertical;', '    reg [10:0] vertical;\n    reg vblank_q;')
    text=once(text,"            vertical <= 11'd0;", "            vertical <= 11'd0;vblank_q<=0;")
    text=once(text,"        end else if (horizontal == 12'd2199) begin", """        end else begin
            vblank_q<=horizontal==12'd2199 && vertical==11'd1079;
            if (horizontal == 12'd2199) begin""")
    text=once(text,"        end else horizontal <= horizontal + 1'b1;", "        end else horizontal <= horizontal + 1'b1;\n        end")
    return once(text,"assign vblank_start = (horizontal == 0) && (vertical == 11'd1080);",'assign vblank_start = vblank_q;')



def slot_payload(text):
    # Occupancy owns reset and acceptance. Payload may sample while invalid;
    # after reset the first accepted request overwrites it before full asserts.
    # Keep reset off the 256-bit payload clock-enable cone.
    return once(text,'        if(request_ready && request_valid)begin',
                '        if(!full && request_valid)begin')


def gray_write_aliases(text):
    from workstation_timing_constraints import gray_write_alias_constraints
    block = gray_write_alias_constraints()
    if block.strip() in text:
        raise ValueError('Gray alias constraints already applied')
    return text + block


def apply(stage, native_composition=False):
    transforms={
        'constraints/tang_mega_138k.sdc':gray_write_aliases,
        'src/migration/gw138k_apb_cdc.sv':apb,
        'src/ae350/gw138k_controlled_services.sv':services,
        'src/usb_host/gw138k_usb_event_fifo.v':event_fifo,
        'src/video/video_runtime_diagnostics.v':diagnostics,
        'src/video/feedback_dashboard.v':dashboard,
        'src/ae350/gw138k_event_workstation.sv':event_dispatch,
        'legacy/rtl/audio/unified_oscillator_engine.sv':voice_count,
        'src/storage/tf_audio_ddr_dma.v':tf_dma,
        'src/usb_a/gw138k_usb_lifecycle_merge.sv':lifecycle,
        'src/video/video_ddr_scanout.v':scanout_request,
        'src/video/video_timing_1080p.v':raster,
        'rtl/timing/basic_pitch_ddr_client_queues.sv':slot_payload,
    }
    if native_composition:
        del transforms['src/ae350/gw138k_event_workstation.sv']
    evidence={}
    for name,transform in transforms.items():
        p=stage/name;old=p.read_bytes();new=transform(old.decode()).encode();p.write_bytes(new)
        evidence[name]=dict(before=hashlib.sha256(old).hexdigest(),after=hashlib.sha256(new).hexdigest(),transform=transform.__name__)
    return evidence
