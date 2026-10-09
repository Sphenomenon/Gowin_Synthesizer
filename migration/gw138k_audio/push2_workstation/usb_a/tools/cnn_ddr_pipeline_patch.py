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

def predecode_dashboard_background(text):
    """Evaluate pure background coordinate tests on the preceding A edge."""
    import re
    start=text.index("        next_background = 32'h00101b2a;")
    end=text.index('\n    end\n',start)
    block=text[start:end];conditions=[];result='';cursor=0
    for match in list(re.finditer(r'\bif\s*\(',block)):
        if match.start()<cursor:continue
        pos=match.end();depth=1
        while depth:
            assert pos<len(block),'unbalanced background condition'
            if block[pos]=='(':depth+=1
            elif block[pos]==')':depth-=1
            pos+=1
        expr=block[match.end():pos-1];names=set(re.findall(r'\b[A-Za-z_]\w*\b',expr))
        if names & {'a_x','a_y'} and names <= {'a_x','a_y','d'}:
            result+=block[cursor:match.start()]+f'if(background_coordinate_q[{len(conditions)}])'
            conditions.append(expr);cursor=pos
    result+=block[cursor:];assert len(conditions)>=20,len(conditions)
    text=text[:start]+result+text[end:]
    sequential='''    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)background_coordinate_q<=0;
        else if(enable)begin
'''
    for i,expr in enumerate(conditions):
        expr=re.sub(r'\ba_x\b','pixel_x_q',expr);expr=re.sub(r'\ba_y\b','pixel_y_q',expr)
        sequential+=f'            background_coordinate_q[{i}]<=({expr});\n'
    sequential+='        end\n    end\n'
    declarations=f'    reg [{len(conditions)-1}:0] background_coordinate_q;\n'
    return text.replace('    reg a_effect_hit',declarations+'    reg a_effect_hit',1).replace('endmodule',sequential+'endmodule')
