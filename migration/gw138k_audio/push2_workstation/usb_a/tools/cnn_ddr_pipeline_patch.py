"""Bounded full85 shared-DDR bus boundary patch; no raster/effect/CNN changes."""
HDMI='src/video/hdmi_display.v'
ARBITER='src/ae350/gw138k_ddr_arbiter.sv'
PIPELINE='rtl/music/basic_pitch_ddr_arbiter_pipeline.sv'

CLIENT_QUEUES="rtl/music/basic_pitch_ddr_client_queues.sv"

def patch_hdmi(text,buffered_clients=False):
    assert text.count('    input wire [255:0] app_rdata,')==1
    text=text.replace('    input wire [255:0] app_rdata,','    input wire [255:0] app_rdata,\n    output wire [255:0] client_rdata,')
    # All consumer uses follow the BIST declaration; retain the native input.
    start=text.index('    ddr3_bist u_bist (')
    text=text[:start]+text[start:].replace('app_rdata','client_rdata')
    assert text.count('    gw138k_ddr_arbiter u_arbiter')==1
    module='basic_pitch_ddr_client_queues' if buffered_clients else 'basic_pitch_ddr_arbiter_pipeline'
    text=text.replace('    gw138k_ddr_arbiter u_arbiter','    '+module+' u_arbiter',1)
    anchor='.app_response(app_rvalid),.response_fault(arbiter_fault)'
    assert text.count(anchor)==1
    return text.replace(anchor,'.app_response(app_rvalid),.app_response_data(app_rdata),\n        .response_data(client_rdata),.response_fault(arbiter_fault)')

def patch_top(text):
    # Exactly the two native endpoint connections retain app_rdata: the PHY
    # output and new arbiter input. CPU, TF, CNN and P10 consume client_rdata.
    text=text.replace('app_rdata','client_rdata').replace('.client_rdata(','.app_rdata(')
    declaration='    wire [255:0] app_wdata,client_rdata;'
    assert text.count(declaration)==1
    text=text.replace(declaration,'    wire [255:0] app_wdata,app_rdata,client_rdata;')
    start=text.index('    ddr3_platform u_memory (');end=text.index('    );',start)
    block=text[start:end];assert block.count('.app_rdata(client_rdata)')==1
    text=text[:start]+block.replace('.app_rdata(client_rdata)','.app_rdata(app_rdata)')+text[end:]
    start=text.index('    hdmi_display u_video (');end=text.index('    );',start)
    block=text[start:end];assert block.count('.app_rdata(client_rdata)')==1
    text=text[:start]+block.replace('.app_rdata(client_rdata)','.app_rdata(app_rdata),.client_rdata(client_rdata)')+text[end:]
    return text

DELAY='rtl/audio/delay_ddr/serial_delay_effect_ddr.sv'
SYNC_FIFO='rtl/music/basic_pitch_ddr_sync_fifo.sv'

def patch_delay_fifo(text,both=False):
    anchor='  music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) u_write_fifo('
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor.replace('music_async_fifo','basic_pitch_ddr_sync_fifo'))
    if both:
        read=anchor.replace('u_write_fifo','u_read_fifo')
        assert text.count(read)==1
        text=text.replace(read,read.replace('music_async_fifo','basic_pitch_ddr_sync_fifo'))
    return text

TF_DMA='src/storage/tf_audio_ddr_dma.v'

def retime_tf_write_buffer(text):
    """Local data writes plus delayed zeroing in the no-request idle bubble.

    The original write-accept cycle issues no new capture read (write_pending
    is high). Clear one cycle later, before that capture request can return.
    Byte data/valid use only local capture state; command contents stay exact.
    """
    declaration='    reg [255:0] write_buf, read_buf;'
    assert text.count(declaration)==1
    text=text.replace(declaration,declaration+'\n    reg write_clear_pending;')
    lines=text.splitlines()
    clears=[line for line in lines if line.strip()=="write_buf <= 256'd0;"]
    assert len(clears)==4,clears
    text='\n'.join(line for line in lines if line not in clears)+'\n'
    byte='                        write_buf[write_count*8 +: 8] <= fifo_in_rd_data;'
    assert text.count(byte)==1;text=text.replace(byte,'')
    anchor='    always @(posedge clk or negedge rst_n) begin'
    assert text.count(anchor)==1
    data='''    wire epoch_clear=restart_event || (state==S_DONE && capture_finished);
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n)begin write_buf<=0;write_clear_pending<=0;end
        else if(epoch_clear)begin write_buf<=0;write_clear_pending<=0;end
        else begin
            write_clear_pending<=write_accept;
            if(write_clear_pending)write_buf<=0;
            else if(state==S_STREAM && fifo_in_rd_valid && capture_byte_count!=32'hffff_ffff)
                write_buf[write_count*8 +:8]<=fifo_in_rd_data;
        end
    end
'''
    return text.replace(anchor,data+anchor,1)

TF_BUFFER='src/memory/tf_audio_ddr_command_buffer.sv'
TMDS='vendor/sipeed_dvi/dvi_tx_tmds_enc.v'

def retime_tf_buffer_enable(text):
    old="""        end else if(full && out_ready) full<=0;
        else if(!full && in_valid) begin
            full<=1;
            write_q<=in_write;
            address_q<=in_address;
            data_q<=in_data;
        end"""
    new="""        end else begin
            if(full)begin if(out_ready)full<=0;end
            else begin
                full<=in_valid;
                write_q<=in_write;
                address_q<=in_address;
                data_q<=in_data;
            end
        end"""
    assert text.count(old)==1
    return text.replace(old,new)

def retime_tf_capture_limit(text):
    declaration='    reg capture_overflow;'
    assert text.count(declaration)==1
    text=text.replace(declaration,declaration+'\n    reg capture_limit_hit;')
    anchor='    wire epoch_clear='
    assert text.count(anchor)==1
    text=text.replace(anchor,"""    // The saturating byte count changes only at a capture acceptance. Predict
    // its terminal value on the same edge, so the wide buffer never decodes
    // the 32-bit count in its per-byte write-enable cones.
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)capture_limit_hit<=0;
        else if(restart_event || (state==S_DONE && capture_finished))capture_limit_hit<=0;
        else if(state==S_STREAM && fifo_in_rd_valid && capture_byte_count==32'hffff_fffe)
            capture_limit_hit<=1;
    end
"""+anchor)
    return text.replace("state==S_STREAM && fifo_in_rd_valid && capture_byte_count!=32'hffff_ffff",
                        'state==S_STREAM && fifo_in_rd_valid && !capture_limit_hit')

def retime_display_enable(text):
    anchor='    wire display_enabled=bist_done && !bist_failed && !fetch_fault && !arbiter_fault;'
    assert text.count(anchor)==1
    return text.replace(anchor,"""    reg display_enabled;
    always @(posedge memory_clk or negedge ui_rst_n)begin
        if(!ui_rst_n)display_enabled<=0;
        else display_enabled<=bist_done && !bist_failed && !fetch_fault && !arbiter_fault;
    end""")

def retime_tmds_statistics(text):
    assert text.count('data_reg<=0;input_ones<=0;den_reg<=0;ctrl_reg<=0;')==1
    assert text.count('data_reg<=data;input_ones<=count_ones(data);den_reg<=den;ctrl_reg<=ctrl;')==1
    text=text.replace('data_reg<=0;input_ones<=0;den_reg<=0;ctrl_reg<=0;',
                      'data_reg<=0;den_reg<=0;ctrl_reg<=0;')
    text=text.replace('data_reg<=data;input_ones<=count_ones(data);den_reg<=den;ctrl_reg<=ctrl;',
                      'data_reg<=data;den_reg<=den;ctrl_reg<=ctrl;')
    anchor='    always @(posedge clock) begin'
    assert text.count(anchor)==1
    # Statistics are masked by den_reg/den_stats during reset pipeline drain.
    return text.replace(anchor,'    always @(posedge clock) input_ones<=count_ones(data);\n'+anchor)

DASHBOARD='src/video/feedback_dashboard.v'
RENDERER='src/video/feedback_renderer.v'

def predecode_dashboard(text):
    """One enabled predecode stage; same pixel content after one extra enable."""
    import re
    header_end=text.index('    localparam [255:0] TITLE')
    header=text[:header_end];body=text[header_end:]
    inputs=[]
    for declaration in re.findall(r'input wire\s+([^\n]+)',header):
        width=re.search(r'\[[^]]+\]',declaration)
        width=width[0] if width else ''
        for name in declaration.replace(width,'').strip().strip(',').split(','):
            name=name.strip()
            if name not in ('clk','reset_n','enable','frame_start'):inputs.append((width,name))
    assert len(inputs)==23,len(inputs)
    # Frame animation and frame-gain freeze consume the original raw inputs;
    # they must not move one cycle relative to frame_start.
    preserves=[]
    patterns=[r'    always @\(posedge clk or negedge reset_n\) begin.*?\n    end\n',
              r'    always @\* begin\n        computed_wave_gain=.*?\n    end\n',
              r'    always @\(posedge clk or negedge reset_n\)\n        if\(!reset_n\)wave_gain.*?: 0;\n']
    for pattern in patterns:
        match=re.search(pattern,body,re.S);assert match,pattern
        preserves.append(match[0]);body=body[:match.start()]+f'    // PRESERVED_RAW_{len(preserves)-1}\n'+body[match.end():]
    # Pure coordinate predicates are inexpensive in stage0 and no longer
    # travel through all text priority muxes before reaching stageA.
    start=body.index('    always @* begin\n        text_line = 0;');end=body.index('    always @* begin\n        next_character',start)
    block=body[start:end];conditions=[]
    def condition(match):
        expr=match[1]
        names=set(re.findall(r'\b[A-Za-z_]\w*\b',expr))
        if ('pixel_x' in names or 'pixel_y' in names) and names <= {'pixel_x','pixel_y','d','h'}:
            index=len(conditions);conditions.append(expr)
            return 'if (coordinate_predicate_q['+str(index)+'])'
        return match[0]
    block=re.sub(r'if\s*\(([^()]*)\)',condition,block)
    assert len(conditions)>30,len(conditions)
    body=body[:start]+block+body[end:]
    # Every remaining input is carried with the same enable; animated local
    # state is carried too so frame boundaries cannot skew label/card data.
    extras=[('[2:0]','visible_mask'),('[1:0]','front_effect'),('[10:0]','effect_x0'),('[10:0]','effect_x1'),('[10:0]','effect_x2'),('[2:0]','wave_gain')]
    carried=inputs+extras
    for width,name in carried:body=re.sub(r'\b'+name+r'\b',name+'_q',body)
    for index,original in enumerate(preserves):body=body.replace(f'    // PRESERVED_RAW_{index}\n',original)
    # Destination is animation control too and uses the current raw frame mask.
    start=body.index('    function [10:0] destination(');end=body.index('    endfunction',start)
    raw=body[start:end].replace('effect_mask_q','effect_mask').replace('effect_order_q','effect_order')
    body=body[:start]+raw+body[end:]
    declarations='\n'.join('    reg '+width+' '+name+'_q;' for width,name in carried)+'\n'
    declarations+=f'    reg [{len(conditions)-1}:0] coordinate_predicate_q;\n'
    # Expressions are evaluated from raw coordinates, on the same edge as the
    # raw payload capture. Both hold during every renderer DDR stall.
    sequential='    always @(posedge clk or negedge reset_n)begin\n        if(!reset_n)begin\n'
    sequential+=''.join('            '+name+'_q<=0;\n' for _,name in carried)
    sequential+='            coordinate_predicate_q<=0;\n        end else if(enable)begin\n'
    sequential+=''.join('            '+name+'_q<='+name+';\n' for _,name in carried)
    sequential+=''.join(f'            coordinate_predicate_q[{i}]<=({expr});\n' for i,expr in enumerate(conditions))
    sequential+='        end\n    end\n'
    # Declarations of animated state were renamed along with consumers;
    # restore those declarations (raw blocks assign them).
    for width,name in extras:
        body=body.replace('reg '+width+' '+name+'_q;', 'reg '+width+' '+name+';')
    body=body.replace('reg [10:0] effect_x0_q, effect_x1_q, effect_x2_q;', 'reg [10:0] effect_x0, effect_x1, effect_x2;')
    body=body.replace('reg [2:0] wave_gain_q,computed_wave_gain;', 'reg [2:0] wave_gain,computed_wave_gain;')
    return header+declarations+body.replace('endmodule',sequential+'endmodule')

def align_renderer_predecode(text):
    assert text.count('reg [4:0] valid_pipe, last_pipe;')==1
    text=text.replace('reg [4:0] valid_pipe, last_pipe;','reg [5:0] valid_pipe, last_pipe;')
    text=text.replace('c_x, c_y, output_x, output_y;', 'c_x, c_y, d_x, d_y, output_x, output_y;')
    text=text.replace('last_pipe[4]','last_pipe[5]').replace('valid_pipe[4]','valid_pipe[5]')
    text=text.replace('valid_pipe[3:0]','valid_pipe[4:0]').replace('last_pipe[3:0]','last_pipe[4:0]')
    assert text.count('output_x <= c_x; output_y <= c_y;')==1
    text=text.replace('output_x <= c_x; output_y <= c_y;', 'd_x <= c_x; d_y <= c_y;\n                output_x <= d_x; output_y <= d_y;')
    anchor='c_x <= 0; c_y <= 0;'
    assert text.count(anchor)==1
    return text.replace(anchor,anchor+' d_x <= 0; d_y <= 0;')

DELAY_DMA='rtl/audio/delay_ddr/delay_ddr_dma.sv'

def parallel_delay_rptr(text):
    anchor='  localparam integer DEPTH='
    assert text.count(anchor)==1
    helper="""  // Parallel byte-group increment: exactly (rptr+4) modulo2^32,
  // including low-bit input values and UINT32 wrap, with no serial32bit carry.
  function automatic [31:0] increment_four(input [31:0] value);
    increment_four[7:0]=value[7:0]+8'd4;
    increment_four[15:8]=value[15:8]+{7'd0,&value[7:2]};
    increment_four[23:16]=value[23:16]+{7'd0,&value[15:2]};
    increment_four[31:24]=value[31:24]+{7'd0,&value[23:2]};
  endfunction
"""
    text=text.replace(anchor,helper+anchor)
    assert text.count('rptr<=rptr+4;')==1
    return text.replace('rptr<=rptr+4;','rptr<=increment_four(rptr);')

def power_two_tf_ring(text):
    anchor="""            if (offset + 32'd32 >= AUDIO_TOTAL_BYTES)
                advance_ring = offset + 32'd32 - AUDIO_TOTAL_BYTES;
            else
                advance_ring = offset + 32'd32;"""
    assert text.count(anchor)==1
    new="""            if(AUDIO_TOTAL_BYTES!=0 &&
                (AUDIO_TOTAL_BYTES & (AUDIO_TOTAL_BYTES-1'b1))==0)
                advance_ring=(offset+32'd32)&(AUDIO_TOTAL_BYTES-1'b1);
            else if (offset + 32'd32 >= AUDIO_TOTAL_BYTES)
                advance_ring = offset + 32'd32 - AUDIO_TOTAL_BYTES;
            else
                advance_ring = offset + 32'd32;"""
    return text.replace(anchor,new)

def predecode_dashboard_text_coordinates(text):
    """Move text-relative arithmetic and animated-card hit into stage0.

    This refines the existing one-enable predecode stage without adding latency.
    All text anchors are constants; only bits used by character/row/column are
    retained. The original text priority and animated-front-card priority stay
    in their original order.
    """
    import re
    start=text.index('    wire [10:0] effect_rel0=')
    end=text.index('    reg a_effect_hit',start)
    old=text[start:end]
    raw=old
    for name in ['effect_x0','effect_x1','effect_x2','pixel_x','pixel_y','front_effect']:
        raw=re.sub(r'\b'+name+'_q'+r'\b',name,raw)
    for name in ['effect_rel0','effect_rel1','effect_rel2','effect_band','hit0','hit1','hit2','effect_hit','effect_id','effect_relative']:
        raw=re.sub(r'\b'+name+r'\b',name+'_pre',raw)
    replacement=raw+'''    reg effect_hit;
    reg [1:0] effect_id;
    reg [10:0] effect_relative;
    reg [9:0] effect_text_x;
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin
            effect_hit<=0;effect_id<=0;effect_relative<=0;effect_text_x<=0;
        end else if(enable)begin
            effect_hit<=effect_hit_pre;effect_id<=effect_id_pre;
            effect_relative<=effect_relative_pre;
            effect_text_x<=effect_relative_pre-11'd16;
        end
    end
'''
    text=text[:start]+replacement+text[end:]
    anchor='    wire [10:0] relative_text_x = effect_hit ? effect_relative-11\'d16 : pixel_x_q-text_x;'
    assert text.count(anchor)==1
    text=text.replace(anchor,"    reg [9:0] static_relative_text_x;\n    wire [9:0] relative_text_x = effect_hit ? effect_text_x : static_relative_text_x;")
    anchor='    wire [10:0] relative_text_y = pixel_y_q - text_y;'
    assert text.count(anchor)==1
    text=text.replace(anchor,'    reg [4:0] relative_text_y;')
    start=text.index('    always @* begin\n        text_line =')
    end=text.index('    always @* begin\n        next_character',start)
    block=text[start:end]
    declarations='';reset='';updates=''
    for axis,width,destination in [('x',10,'static_relative_text_x'),('y',5,'relative_text_y')]:
        values=sorted({int(v) for v in re.findall(r'text_'+axis+r'\s*=\s*(\d+)\s*;',block)})
        assert len(values)>15,values
        for value in values:
            name=f'text_{axis}_relative_{value}_q'
            declarations+=f'    reg [{width-1}:0] {name};\n'
            reset+=f'            {name}<=0;\n'
            updates+=f"            {name}<=pixel_{axis}-11'd{value};\n"
        block=re.sub(r'text_'+axis+r'\s*=\s*(\d+)\s*;',
            lambda m:m[0]+f' {destination}=text_{axis}_relative_{m[1]}_q;',block)
    text=text[:start]+block+text[end:]
    sequential='''    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin
'''+reset+'''        end else if(enable)begin
'''+updates+'''        end
    end
'''
    return text.replace('    reg a_effect_hit',declarations+'    reg a_effect_hit',1).replace('endmodule',sequential+'endmodule')

def parallel_dashboard_cards(text):
    """Same animation and hit priority, move late selects behind parallel math."""
    helper='''    // Destination is one of four constants. Evaluate their next positions
    // in parallel so frame metadata selects only the completed result.
    function [10:0] slide_destinations(input [10:0] position,input [1:0] id);
        reg [10:0] parked,first,second,third;
        begin
            parked=slide(position,11'd1120);
            first=slide(position,11'd64);
            second=slide(position,11'd400);
            third=slide(position,11'd736);
            if(!effect_mask[id])slide_destinations=parked;
            else if(effect_order[1:0]==id)slide_destinations=first;
            else if(effect_order[3:2]==id)slide_destinations=second;
            else if(effect_order[5:4]==id)slide_destinations=third;
            else slide_destinations=parked;
        end
    endfunction
    // (x-position-16) mod2^10 through a three-input carry-save front
    // and one final carry chain; the geometry select follows the arithmetic.
    function [9:0] card_text_relative(input [10:0] x,input [10:0] position);
        reg [9:0] a,b,c,sum,carry;
        begin
            a=x[9:0];b=~position[9:0];c=10'h3f1;
            sum=a^b^c;carry=((a&b)|(a&c)|(b&c))<<1;
            card_text_relative=sum+carry;
        end
    endfunction
'''
    anchor='    always @(posedge clk or negedge reset_n) begin'
    assert text.count(anchor)>=1
    text=text.replace(anchor,helper+anchor,1)
    for i in range(3):
        old=f'effect_x{i}<=slide(effect_x{i},destination({i}));'
        assert text.count(old)==1
        text=text.replace(old,f'effect_x{i}<=slide_destinations(effect_x{i},2\'d{i});')
    anchor='    reg effect_relative_pre;'
    # The original register declaration has a width.
    anchor='    reg [10:0] effect_relative_pre;';assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'''
    wire [9:0] effect_text0_pre=card_text_relative(pixel_x,effect_x0);
    wire [9:0] effect_text1_pre=card_text_relative(pixel_x,effect_x1);
    wire [9:0] effect_text2_pre=card_text_relative(pixel_x,effect_x2);
    reg [9:0] effect_text_pre;
''')
    start=text.index('    always @* begin\n        effect_hit_pre=');end=text.index('    reg effect_hit;',start)
    block=text[start:end]
    for i in range(3):
        old=f'effect_relative_pre=effect_rel{i}_pre;';assert old in block
        block=block.replace(old,old+f' effect_text_pre=effect_text{i}_pre;')
    text=text[:start]+block+text[end:]
    old="effect_text_x<=effect_relative_pre-11'd16;";assert text.count(old)==1
    return text.replace(old,'effect_text_x<=effect_text_pre;')

def lut_tmds_popcount(text):
    """Exact8-bit population count with parallel4-bit LUT truth tables."""
    import re
    match=re.search(r'    function \[3:0\] count_ones;.*?    endfunction',text,re.S)
    assert match
    lookup='''    function [2:0] nibble_ones(input [3:0] bits_in);
        begin
            case(bits_in)
'''
    lookup+=''.join(f"                4'd{i}:nibble_ones=3'd{i.bit_count()};\n" for i in range(16))
    lookup+='''                default:nibble_ones=3'bxxx;
            endcase
        end
    endfunction
    function [3:0] count_ones;
        input [7:0] bits_in;
        begin
            count_ones={1'b0,nibble_ones(bits_in[3:0])}+{1'b0,nibble_ones(bits_in[7:4])};
        end
    endfunction'''
    return text[:match.start()]+lookup+text[match.end():]

def predecode_dashboard_background(text,complete=False):
    """Evaluate pure background coordinate tests on the preceding A edge."""
    import re
    start=text.index("        next_background = 32'h00101b2a;")
    end=text.index('\n    end\n',start)
    block=text[start:end];conditions=[];result='';cursor=0
    aliases=['a_image_x','a_image_y','full_distance_x','full_distance_y','distance_x','distance_y','diamond_distance']
    coordinate_wires=''
    if complete:
        begin=text.index('    wire [10:0] a_image_x=');stop=text.index('    wire spectrum_l_ink=',begin)
        coordinate_wires=text[begin:stop]
        for name in aliases:coordinate_wires=re.sub(r'\b'+name+r'\b','background_'+name+'_pre',coordinate_wires)
        coordinate_wires=re.sub(r'\ba_x\b','pixel_x_q',coordinate_wires)
        coordinate_wires=re.sub(r'\ba_y\b','pixel_y_q',coordinate_wires)
        anchor='next_background=a_y<128 ?';assert block.count(anchor)==1
        block=block.replace(anchor,'next_background=background_coordinate_q[0] ?')
        conditions.append('a_y<128')
    for match in list(re.finditer(r'\bif\s*\(',block)):
        if match.start()<cursor:continue
        pos=match.end();depth=1
        while depth:
            assert pos<len(block),'unbalanced background condition'
            if block[pos]=='(':depth+=1
            elif block[pos]==')':depth-=1
            pos+=1
        expr=block[match.end():pos-1]
        identifiers=re.sub(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+",'',expr) if complete else expr
        names=set(re.findall(r'\b[A-Za-z_]\w*\b',identifiers))
        allowed={'a_x','a_y','d'} | (set(aliases) if complete else set())
        coordinates={'a_x','a_y'} | (set(aliases) if complete else set())
        if names & coordinates and names <= allowed:
            result+=block[cursor:match.start()]+f'if(background_coordinate_q[{len(conditions)}])'
            conditions.append(expr);cursor=pos
    result+=block[cursor:];assert len(conditions)>=20,len(conditions)
    text=text[:start]+result+text[end:]
    sequential="""    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)background_coordinate_q<=0;
        else if(enable)begin
"""
    for i,expr in enumerate(conditions):
        expr=re.sub(r'\ba_x\b','pixel_x_q',expr);expr=re.sub(r'\ba_y\b','pixel_y_q',expr)
        if complete:
            for name in aliases:expr=re.sub(r'\b'+name+r'\b','background_'+name+'_pre',expr)
        sequential+=f'            background_coordinate_q[{i}]<=({expr});\n'
    sequential+='        end\n    end\n'
    declarations=coordinate_wires+f'    reg [{len(conditions)-1}:0] background_coordinate_q;\n'
    return text.replace('    reg a_effect_hit',declarations+'    reg a_effect_hit',1).replace('endmodule',sequential+'endmodule')

def register_arbiter_tag_flags(text):
    """Predict tag full/empty on original count edge, no transaction latency."""
    anchor='    reg [TAG_BITS:0] count;';assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'\n    reg tag_full,tag_empty;')
    assert text.count('wire read_room=count<DEPTH;')==1
    text=text.replace('wire read_room=count<DEPTH;','wire read_room=!tag_full;')
    text=text.replace('wire pop=app_response && count!=0;','wire pop=app_response && !tag_empty;')
    text=text.replace('if(app_response && count==0)response_fault<=1;', 'if(app_response && tag_empty)response_fault<=1;')
    anchor='            read_pointer<=0;write_pointer<=0;count<=0;';assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'tag_full<=0;tag_empty<=1;')
    anchor="                2'b10:count<=count+1'b1;\n                2'b01:count<=count-1'b1;";assert text.count(anchor)==1
    text=text.replace(anchor,"""                2'b10:begin
                    count<=count+1'b1;tag_full<=count==DEPTH-1;tag_empty<=0;
                end
                2'b01:begin
                    count<=count-1'b1;tag_full<=0;tag_empty<=count==1;
                end""")
    return text

MODEL_MEMORY_READY_BLOCK='''    // Calibration is a same-memory-clock level. Local capture reduces the
    // high-fanout PHY level to a short client enable. Global memory reset
    // clears it asynchronously; boot waits for CPU/BIST/UI before any model.
    reg model_memory_ready;
    always @(posedge memory_clk or negedge memory_reset_n)begin
        if(!memory_reset_n)model_memory_ready<=0;
        else model_memory_ready<=memory_calibrated;
    end
'''

def retime_model_memory_ready(text):
    anchor='    wire ddr_rsp_valid,ddr_rsp_fifo_valid,ddr_rsp_fifo_ready;'
    assert text.count(anchor)==1
    assert text.count('req_valid_i(ddr_cmd_valid && memory_calibrated &&')==1
    return text.replace(anchor,MODEL_MEMORY_READY_BLOCK+anchor).replace(
        'req_valid_i(ddr_cmd_valid && memory_calibrated &&',
        'req_valid_i(ddr_cmd_valid && model_memory_ready &&')

def predecode_dashboard_wave_heights(text):
    """Shift/clamp in the existing predecode stage; A receives identical heights."""
    import re
    a=text.index('    wire [4:0] wave_shift=');b=text.index('    wire signed [11:0] sample_extended',a)
    block=text[a:b]
    assert 'wave_gain_q' in block and 'wave_sample_q' in block
    raw=block
    for name in ['wave_gain','wave_sample','wave_previous']:
        raw=re.sub(r'\b'+name+'_q'+r'\b',name,raw)
    for name in ['wave_shift','scaled_sample','scaled_previous','sample_height','previous_height']:
        raw=re.sub(r'\b'+name+r'\b',name+'_pre',raw)
    sequential='''    reg signed [9:0] sample_height,previous_height;
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin sample_height<=0;previous_height<=0;end
        else if(enable)begin
            sample_height<=sample_height_pre;previous_height<=previous_height_pre;
        end
    end
'''
    return text[:a]+raw+sequential+text[b:]


def narrow_feature_read_slot(text):
    """Use only three slot bits after existing 0..4/6/2 validity checks.

    Address/data/valid and their cycles are identical for all input bit
    patterns. MAC arithmetic and the shared cache/DDR interfaces are untouched.
    """
    a=text.index('            always_comb begin\n                feature_read_valid = 1\'b0;')
    b=text.index('            always_ff @(posedge clk_i) begin',a)
    block=text[a:b]
    assert block.count('$unsigned(feature_read_rel)')==3
    for bound in (3,5,7):
        assert f'(feature_read_rel < {bound})' in block
    block=block.replace('$unsigned(feature_read_rel)','$unsigned(feature_read_rel[2:0])')
    return text[:a]+block+text[b:]


PIXEL_SKID='src/video/feedback_pixel_skid.v'

def patch_hdmi_pixel_skid(text):
    """Registered two-beat raster ready, deferred done after drain, same stream."""
    anchor='    ddr_frame_writer u_writer ('
    assert text.count(anchor)==1
    block_start=text.index(anchor);block_end=text.index('    );',block_start)
    block=text[block_start:block_end]
    for before,after in [('renderer_done(renderer_done)','renderer_done(writer_pixel_done)'),
                         ('pixel_valid(pixel_valid)','pixel_valid(writer_pixel_valid)'),
                         ('pixel_ready(pixel_ready)','pixel_ready(writer_pixel_ready)'),
                         ('pixel_data(pixel_data)','pixel_data(writer_pixel_data)')]:
        assert block.count(before)==1;block=block.replace(before,after)
    text=text[:block_start]+block+text[block_end:]
    return text.replace(anchor,"""    wire writer_pixel_valid,writer_pixel_ready,writer_pixel_done;
    wire [63:0] writer_pixel_data;
    feedback_pixel_skid u_pixel_skid (
        .clk(memory_clk),.rst_n(ui_rst_n),.source_valid(pixel_valid),
        .source_ready(pixel_ready),.source_data(pixel_data),.source_done(renderer_done),
        .sink_valid(writer_pixel_valid),.sink_ready(writer_pixel_ready),
        .sink_data(writer_pixel_data),.sink_done(writer_pixel_done));
"""+anchor,1)


TF_BYTE_COUNT_HELPER="""    function [31:0] add_byte_count;
        input [31:0] value;
        input [5:0] increment;
        reg [8:0] low_sum;
        reg carry8,carry16,carry24;
        reg [7:0] b1,b2,b3;
        begin
            low_sum={1'b0,value[7:0]}+{3'd0,increment};
            carry8=low_sum[8];
            carry16=carry8 && value[15:8]==8'hff;
            carry24=carry8 && value[23:8]==16'hffff;
            b1=value[15:8]+carry8;
            b2=value[23:16]+carry16;
            b3=value[31:24]+carry24;
            add_byte_count={b3,b2,b1,low_sum[7:0]};
        end
    endfunction
"""

def parallel_tf_byte_counters(text):
    """Exact32-bit modulo sums, independent byte carries; no control latency."""
    substitutions=[("capture_byte_count + 32'd1","add_byte_count(capture_byte_count,6'd1)"),
        ("write_total_bytes + {26'd0, pending_bytes}",'add_byte_count(write_total_bytes,pending_bytes)'),
        ("read_total_bytes +\n                                        {26'd0, read_response_bytes}",'add_byte_count(read_total_bytes,read_response_bytes)')]
    for old,new in substitutions:
        assert text.count(old)==1,(old,text.count(old));text=text.replace(old,new)
    anchor='    function [31:0] advance_ring;';assert text.count(anchor)==1
    return text.replace(anchor,TF_BYTE_COUNT_HELPER+anchor,1)


def predecode_dashboard_dynamic_ink(text):
    """A-edge ink predicates replace identical combinational B-edge predicates."""
    import re
    declarations="    wire signed [11:0] background_y_pre=$signed({1'b0,pixel_y_q});\n"
    for name in ['sample_top','sample_bottom','previous_top','previous_bottom']:
        expressions=re.findall(r'\ba_'+name+r'\s*<=\s*(.*?);',text,re.S)
        assert len(expressions)==2,(name,expressions)
        declarations+=f'    wire signed [11:0] background_{name}_pre='+expressions[-1]+';\n'
    wires="""    wire [10:0] background_peak_x_pre=pixel_x_q-11'd1248;
    wire background_trace_pre=
        ((background_y_pre>=background_sample_top_pre && background_y_pre<=background_previous_bottom_pre) ||
         (background_y_pre>=background_previous_top_pre && background_y_pre<=background_sample_bottom_pre));
    wire background_spectrum_l_pre=spectrum_left_q!=0 && pixel_y_q>=11'd792-{3'd0,spectrum_left_q};
    wire background_spectrum_r_pre=spectrum_right_q!=0 && pixel_y_q>=11'd792-{3'd0,spectrum_right_q};
    reg background_trace_q,background_spectrum_l_q,background_spectrum_r_q;
    reg background_peak_l_q,background_peak_r_q;
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin
            background_trace_q<=1; background_spectrum_l_q<=0; background_spectrum_r_q<=0;
            background_peak_l_q<=0;background_peak_r_q<=0;
        end else if(enable)begin
            background_trace_q<=background_trace_pre;
            background_spectrum_l_q<=background_spectrum_l_pre;
            background_spectrum_r_q<=background_spectrum_r_pre;
            background_peak_l_q<=background_peak_x_pre<peak_left_q[15:6];
            background_peak_r_q<=background_peak_x_pre<peak_right_q[15:6];
        end
    end
"""
    start=text.index("        next_background = 32'h00101b2a;")
    end=text.index('\n    end\n',start)
    block=text[start:end]
    for old,new in [('trace_ink','background_trace_q'),('spectrum_l_ink','background_spectrum_l_q'),
                    ('spectrum_r_ink','background_spectrum_r_q')]:
        assert old in block;block=re.sub(r'\b'+old+r'\b',new,block)
    for old,new in [("a_x-11'd1248<a_left_width",'background_peak_l_q'),
                    ("a_x-11'd1248<a_right_width",'background_peak_r_q')]:
        assert block.count(old)==1;block=block.replace(old,new)
    text=text[:start]+block+text[end:]
    anchor='    reg a_effect_hit';assert text.count(anchor)==1
    return text.replace(anchor,declarations+wires+anchor,1)


BIST='src/memory/ddr3_bist.v'

def retime_bist_expected_pattern(text):
    """Expected pattern in the existing request wait beat; same BIST cycles."""
    old='    wire mismatch = (rsp_data != test_pattern(address, inverted));'
    assert text.count(old)==1
    return text.replace(old,"""    // address/inverted are stable through READ_REQUEST before READ_RESPONSE;
    // the expected value is current before the earliest accepted response.
    reg [255:0] expected_pattern_q;
    always @(posedge clk)expected_pattern_q<=test_pattern(address,inverted);
    wire mismatch = (rsp_data != expected_pattern_q);
""",1)


def retime_tf_read_total(text):
    """Precompute exact post-read count at request; retain zero-cycle response."""
    anchor='    wire emit_byte =';assert text.count(anchor)==1
    helper="""    // Partial final beat consumes exactly all committed bytes. The full
    // beat advances32; avoid feeding available-byte subtraction into addition.
    wire [31:0] read_total_after_accept=(eof_finalized && available_bytes<32) ?
        write_total_bytes : add_byte_count(read_total_bytes,6'd32);
    reg [31:0] read_total_pending;
"""
    text=text.replace(anchor,helper+anchor,1)
    anchor='                    read_pending_bytes <= read_chunk_bytes;';assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'\n                    read_total_pending <= read_total_after_accept;',1)
    anchor='read_total_bytes <= add_byte_count(read_total_bytes,read_response_bytes);';assert text.count(anchor)==1
    text=text.replace(anchor,'read_total_bytes <= read_accept ? read_total_after_accept : read_total_pending;',1)
    return text


def parallel_renderer_spectrum_address(text):
    """Resolve both candidate spectrum addresses before final advance select."""
    old="""    wire [10:0] next_x=advance ? (issue_x==WIDTH-2 ? 11'd0 : issue_x+11'd2) : issue_x;
    wire [10:0] spectrum_offset=next_x-11'd64;
    wire [8:0] spectrum_column=next_x>=64 && next_x<1088 ? spectrum_offset[9:1] : 9'd0;
"""
    assert text.count(old)==1
    new="""    wire [10:0] spectrum_next_x=issue_x==WIDTH-2 ? 11'd0 : issue_x+11'd2;
    wire [10:0] spectrum_offset_current=issue_x-11'd64;
    wire [10:0] spectrum_offset_next=spectrum_next_x-11'd64;
    wire [8:0] spectrum_column_current=issue_x>=64 && issue_x<1088 ? spectrum_offset_current[9:1] : 9'd0;
    wire [8:0] spectrum_column_next=spectrum_next_x>=64 && spectrum_next_x<1088 ? spectrum_offset_next[9:1] : 9'd0;
    wire [8:0] spectrum_column=advance ? spectrum_column_next : spectrum_column_current;
"""
    return text.replace(old,new,1)


def shallow_dashboard_card_select(text):
    """Resolve original front-card priority once, then mask parallel payloads."""
    start=text.index('    always @* begin\n        effect_hit_pre=hit0_pre')
    end=text.index('    reg effect_hit;',start)
    original=text[start:end]
    assert original.count('if(front_effect==')==3
    replacement="""    wire card_front0=front_effect==0 && hit0_pre;
    wire card_front1=front_effect==1 && hit1_pre;
    wire card_pick2=hit2_pre && !card_front0 && !card_front1;
    wire card_pick1=hit1_pre && !card_front0 && (!hit2_pre || card_front1);
    wire card_pick0=!card_pick1 && !card_pick2;
    always @* begin
        effect_hit_pre=hit0_pre || hit1_pre || hit2_pre;
        effect_id_pre={card_pick2,card_pick1};
        effect_relative_pre=({11{card_pick0}} & effect_rel0_pre) |
                            ({11{card_pick1}} & effect_rel1_pre) |
                            ({11{card_pick2}} & effect_rel2_pre);
        effect_text_pre=({10{card_pick0}} & effect_text0_pre) |
                        ({10{card_pick1}} & effect_text1_pre) |
                        ({10{card_pick2}} & effect_text2_pre);
    end
"""
    return text[:start]+replacement+text[end:]


def fast_tf_read_availability(text):
    """Exact unsigned modulo32-bit delta<32 from grouped count comparisons."""
    anchor='    wire read_has_full_beat = (available_bytes >= 32\'d32);'
    assert text.count(anchor)==1
    replacement="""    wire [31:0] read_plus32=add_byte_count(read_total_bytes,6'd32);
    wire available_lt32=(write_total_bytes[4:0]>=read_total_bytes[4:0] &&
                        write_total_bytes[31:5]==read_total_bytes[31:5]) ||
                       (write_total_bytes[4:0]<read_total_bytes[4:0] &&
                        write_total_bytes[31:5]==read_plus32[31:5]);
    wire read_has_full_beat = !available_lt32;"""
    text=text.replace(anchor,replacement,1)
    anchor='wire read_has_partial_beat = eof_finalized && (available_bytes != 0);'
    assert text.count(anchor)==1
    text=text.replace(anchor,'wire read_has_partial_beat = eof_finalized && (write_total_bytes != read_total_bytes);',1)
    for old,new in [('(eof_finalized && available_bytes < 32\'d32)','(eof_finalized && available_lt32)'),
                    ('(eof_finalized && available_bytes<32)','(eof_finalized && available_lt32)')]:
        assert text.count(old)==1
        text=text.replace(old,new,1)
    return text


def quiet_shared_analysis_column(text):
    """Shared rendering reads local analysis only via the snapshot exporter."""
    old='    wire [8:0] read_column=exporting ? shared_read_addr[8:0] : spectrum_column;'
    assert text.count(old)==1
    new="""    // In shared-render mode the snapshot writer owns analysis readback.
    // The raster consumes the coherent external cache, never local FFT RAM.
    wire [8:0] read_column=(SHARED_RENDER!=0) ? shared_read_addr[8:0] :
        (exporting ? shared_read_addr[8:0] : spectrum_column);"""
    return text.replace(old,new,1)


def pipeline_bist_compare(text):
    """Capture eight32-bit lane comparisons at response, account next cycle."""
    old="""    localparam [1:0] WRITE = 2'd0, READ_REQUEST = 2'd1,
                     READ_RESPONSE = 2'd2, FINISHED = 2'd3;"""
    new="""    localparam [2:0] WRITE = 3'd0, READ_REQUEST = 3'd1,
                     READ_RESPONSE = 3'd2, FINISHED = 3'd3, READ_CHECK = 3'd4;"""
    assert text.count(old)==1;text=text.replace(old,new,1)
    assert text.count('    reg [1:0] state;')==1
    text=text.replace('    reg [1:0] state;','    reg [2:0] state;',1)
    old='    wire mismatch = (rsp_data != expected_pattern_q);'
    assert text.count(old)==1
    new="""    reg [7:0] mismatch_lanes_q;
    genvar check_lane;
    generate for(check_lane=0;check_lane<8;check_lane=check_lane+1)begin : g_compare
        always @(posedge clk)
            mismatch_lanes_q[check_lane]<=rsp_data[check_lane*32+:32] !=
                expected_pattern_q[check_lane*32+:32];
    end endgenerate
    wire mismatch = |mismatch_lanes_q;"""
    text=text.replace(old,new,1)
    old='            if (request_accepted || response_accepted) begin'
    assert text.count(old)==1
    text=text.replace(old,'            if (request_accepted || response_accepted || state==READ_CHECK) begin',1)
    old='                    READ_RESPONSE: begin\n                        if (mismatch) begin'
    assert text.count(old)==1
    text=text.replace(old,'                    READ_RESPONSE: state<=READ_CHECK;\n                    READ_CHECK: begin\n                        if (mismatch) begin',1)
    return text


def mask_tf_write_epoch(text):
    """Keep byte validity32-bit; wide payload RAM/registers need no epoch clear."""
    old='    reg [255:0] write_buf, read_buf;'
    assert text.count(old)==1
    text=text.replace(old,"""    reg [255:0] read_buf,write_storage;
    wire [255:0] write_buf;
    reg [31:0] write_byte_valid;
    genvar valid_byte;
    generate for(valid_byte=0;valid_byte<32;valid_byte=valid_byte+1)begin : g_valid_byte
        assign write_buf[valid_byte*8+:8]=write_byte_valid[valid_byte] ?
            write_storage[valid_byte*8+:8] : 8'd0;
    end endgenerate""",1)
    old="""    always @(posedge clk or negedge rst_n) begin
        if(!rst_n)begin write_buf<=0;write_clear_pending<=0;end
        else if(epoch_clear)begin write_buf<=0;write_clear_pending<=0;end
        else begin
            write_clear_pending<=write_accept;
            if(write_clear_pending)write_buf<=0;
            else if(state==S_STREAM && fifo_in_rd_valid && !capture_limit_hit)
                write_buf[write_count*8 +:8]<=fifo_in_rd_data;
        end
    end
"""
    assert text.count(old)==1
    new="""    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin write_byte_valid<=0;write_clear_pending<=0;end
        else if(epoch_clear)begin write_byte_valid<=0;write_clear_pending<=0;end
        else begin
            write_clear_pending<=write_accept;
            if(write_clear_pending)write_byte_valid<=0;
            else if(state==S_STREAM && fifo_in_rd_valid && !capture_limit_hit)
                write_byte_valid[write_count]<=1;
        end
    end
    always @(posedge clk)begin
        if(!epoch_clear && !write_clear_pending &&
           state==S_STREAM && fifo_in_rd_valid && !capture_limit_hit)
            write_storage[write_count*8+:8]<=fifo_in_rd_data;
    end
"""
    return text.replace(old,new,1)


def registered_tf_read_response(text):
    """Specialize only audited buffered-client build to registered read returns."""
    substitutions=[
        ('wire read_response = app_rvalid && (read_pending || read_accept);',
         'wire read_response = app_rvalid && read_pending;'),
        ('wire [5:0] read_response_bytes = read_accept ? read_chunk_bytes :\n                                                   read_pending_bytes;',
         'wire [5:0] read_response_bytes = read_pending_bytes;'),
        ('read_total_bytes <= read_accept ? read_total_after_accept : read_total_pending;',
         'read_total_bytes <= read_total_pending;')]
    for old,new in substitutions:
        assert text.count(old)==1,old
        text=text.replace(old,new,1)
    return text
